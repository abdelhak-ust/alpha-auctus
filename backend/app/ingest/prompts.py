"""Prompt text for the ingest graph's LLM calls (Gemini via `app.ai.generate_json`).

Four distinct calls, kept separate on purpose (plans/ingestion.md §2 "find ≠ merge"):
extraction (recall, per chunk, with rolling state), consolidation (precision, per fragment
group), match classification + merge (registry-aware, per consolidated feature), and the
completeness sweep (high recall, per chunk). Every call asks for verbatim quotes — the pipeline
locates them in the chunk itself and drops anything it can't find (cite or stay silent).
"""

from __future__ import annotations

import json

SYSTEM = (
    "You are the feature-extraction engine of Nexus, a software-delivery platform. You read "
    "product documents (specs, PRDs, BRDs, meeting notes) and identify the product FEATURES "
    "they describe: user-facing or system capabilities that a team would build. You never "
    "invent information: every claim you make must be backed by a verbatim quote copied "
    "character-for-character from the text you were given. If you cannot quote it, omit it."
)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def extraction_prompt(
    *,
    chunk_text: str,
    section: str,
    rolling_summary: list[dict],
    registry_candidates: list[dict],
) -> str:
    registry_block = (
        "Existing registry features that may be related (from earlier documents):\n"
        f"{_json(registry_candidates)}\n"
        "If a mention refers to one of these, set `status` to \"update\" and "
        "`references_feature` to its `feature_id`.\n\n"
        if registry_candidates
        else ""
    )
    return (
        "Extract every feature mentioned in the CHUNK below.\n\n"
        "Features already found earlier in THIS document (name + one line):\n"
        f"{_json(rolling_summary) if rolling_summary else '[] (this is the first chunk)'}\n\n"
        f"{registry_block}"
        "For each feature mention, return a fragment:\n"
        "- feature_name: short canonical name (reuse the exact name from the list above if it "
        "is the same feature).\n"
        "- description: what the text says about it (only what the text says).\n"
        "- status: \"new\" (first mention), \"continuation\" (adds detail to a feature already "
        "found in this document — set references_feature to its name) or \"update\" (refers "
        "to an existing registry feature — set references_feature to its feature_id).\n"
        "- snippet: a VERBATIM quote from the chunk (one or two sentences) that is the "
        "evidence. Copy it exactly; do not paraphrase, fix typos or add ellipses.\n"
        "- char_start / char_end: your best estimate of the snippet's offsets within the "
        "chunk text.\n"
        "- section: the section heading, if known.\n"
        "- confidence: 0..1 that this is really a product feature.\n"
        "Return {\"fragments\": []} if the chunk describes no feature.\n\n"
        f"SECTION: {section or '(none)'}\n"
        f"CHUNK:\n<<<\n{chunk_text}\n>>>"
    )


def consolidation_prompt(*, name_hint: str, fragments: list[dict]) -> str:
    return (
        "The fragments below were extracted from one document and appear to describe the "
        "same feature. Merge them into ONE coherent feature.\n\n"
        f"Name hint: {name_hint}\n"
        "Fragments (index, name, description, verbatim evidence):\n"
        f"{_json(fragments)}\n\n"
        "Return:\n"
        "- name: the best canonical feature name.\n"
        "- description: one coherent description using ONLY information in the fragments.\n"
        "- fragment_indices: indexes of the fragments that really belong to this feature "
        "(omit any that describe a different feature).\n"
        "- contradictions: statements that contradict each other (e.g. two different limits "
        "for the same thing). Do NOT resolve them — list them. Empty if none.\n"
        "- relations: other features this one depends_on / extends / conflicts_with, by name, "
        "only if the fragments state it.\n"
        "- confidence: 0..1."
    )


def match_prompt(*, feature: dict, candidates: list[dict]) -> str:
    return (
        "A feature was just extracted from a NEW document. Compare it with existing registry "
        "features and classify the relationship.\n\n"
        f"NEW FEATURE:\n{_json(feature)}\n\n"
        f"EXISTING CANDIDATES (with similarity scores):\n{_json(candidates)}\n\n"
        "outcome:\n"
        "- \"new\": none of the candidates is the same feature.\n"
        "- \"update\": same feature as a candidate, and the new text ADDS detail without "
        "contradicting it.\n"
        "- \"conflict\": same feature, but the new text CONTRADICTS the existing description "
        "(different values, rules, behaviour).\n"
        "- \"duplicate\": same feature, and the new text adds nothing new.\n"
        "Rank `candidates` best-first with a short reason and confidence each; set "
        "matched_feature_id to the top candidate unless the outcome is \"new\". Set an overall "
        "confidence 0..1 — be honest; low confidence is sent to a human, never auto-applied."
    )


def merge_prompt(*, existing: dict, incoming: dict) -> str:
    return (
        "Merge the new detail into the existing feature description. Keep everything the "
        "existing description says; add only what the incoming text adds. Do not invent.\n\n"
        f"EXISTING:\n{_json(existing)}\n\nINCOMING:\n{_json(incoming)}\n\n"
        "Return name (keep the existing name unless clearly wrong), description (merged), "
        "fragment_indices [], contradictions (anything that contradicts — should be empty "
        "for an update), relations [], confidence."
    )


def sweep_prompt(*, chunk_text: str, section: str) -> str:
    return (
        "Completeness check. List EVERY candidate feature mention in the chunk below — even "
        "partial, vague or passing ones (high recall; false positives are fine, a human will "
        "review them). For each: name, a VERBATIM snippet copied exactly from the chunk, and "
        "confidence 0..1. Return {\"mentions\": []} if there are none.\n\n"
        f"SECTION: {section or '(none)'}\n"
        f"CHUNK:\n<<<\n{chunk_text}\n>>>"
    )
