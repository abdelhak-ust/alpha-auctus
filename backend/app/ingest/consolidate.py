"""Consolidation pass (plans/ingestion.md §5 step 5) — the precision half of "find ≠ merge".

1. Group this document's located fragments: same (normalized / near-equal) name, an explicit
   `references_feature` continuation, or the same referenced registry feature id.
2. One LLM call per multi-fragment group merges them into one description and *lists* any
   in-document contradictions (never resolves them — a contradiction makes the feature
   `conflicted`). Single-fragment groups need no merge call.
3. A group with a contradiction is split for review (§11.3): the contradicting fragment (the
   non-first fragment that best matches the listed contradiction) becomes the *incoming*
   version; the rest form v1, the current version.
4. Citations are never generated here: a consolidated feature's `source_refs` are exactly the
   located refs of the fragments it merged, so every feature has ≥ 1 real citation.
"""

from __future__ import annotations

import uuid

from app.ingest.cite import name_tokens, names_match
from app.ingest.llm import call_llm
from app.ingest.prompts import consolidation_prompt
from app.schemas.ingestion import ConsolidatedFeature


def _as_uuid(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


def group_fragments(fragments: list[dict]) -> list[list[int]]:
    """Union-find over fragment indexes. Returns groups in first-appearance order."""
    parent = list(range(len(fragments)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    for i, a in enumerate(fragments):
        a_reg = _as_uuid(a.get("references_feature"))
        a_ref = a.get("references_feature") if a_reg is None else None
        for j in range(i):
            b = fragments[j]
            b_reg = _as_uuid(b.get("references_feature"))
            if (
                names_match(a["feature_name"], b["feature_name"])
                or (a_ref and names_match(a_ref, b["feature_name"]))
                or (b.get("references_feature") and b_reg is None
                    and names_match(b["references_feature"], a["feature_name"]))
                or (a_reg and a_reg == b_reg)
            ):
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(len(fragments)):
        groups.setdefault(find(i), []).append(i)
    return sorted(groups.values(), key=lambda g: g[0])


def dedupe_refs(refs: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for ref in refs:
        key = (ref["doc_id"], ref["char_start"], ref["char_end"])
        if key not in seen:
            seen.add(key)
            out.append(ref)
    return out


def _feature_dict(
    consolidated: ConsolidatedFeature, members: list[dict], *, key: str
) -> dict:
    registry_hint = next(
        (h for h in (_as_uuid(m.get("references_feature")) for m in members) if h), None
    )
    return {
        "key": key,
        "name": consolidated.name,
        "description": consolidated.description,
        "source_refs": dedupe_refs([m["source_ref"] for m in members]),
        "contradictions": list(consolidated.contradictions),
        "relations": [r.model_dump() for r in consolidated.relations],
        "confidence": consolidated.confidence,
        "registry_hint": registry_hint,
        "fragment_count": len(members),
    }


def _contradicting_index(members: list[dict], contradictions: list[str]) -> int:
    """Which (non-first) member states the contradicting claim — best token overlap with the
    contradiction text; ties go to the later statement."""
    target = name_tokens(" ".join(contradictions))
    best, best_score = len(members) - 1, -1.0
    for n in range(1, len(members)):
        tokens = name_tokens(f"{members[n]['description']} {members[n]['snippet']}")
        score = len(tokens & target) / (len(tokens | target) or 1)
        if score >= best_score:
            best, best_score = n, score
    return best


def _unpaired_contradiction_flag(merged: ConsolidatedFeature, members: list[dict],
                                 kept: list[int]) -> dict:
    """A contradiction the merge reported but that can't be split into a v1/v2 pair (only one
    fragment kept). Never dropped: it becomes a sweep flag citing the contradicting fragment —
    the best-matching fragment outside the kept one (the kept one if the group has no other)."""
    target = name_tokens(" ".join(merged.contradictions))
    pool = [n for n in range(len(members)) if n not in kept] or list(kept)

    def score(n: int) -> float:
        tokens = name_tokens(f"{members[n]['description']} {members[n]['snippet']}")
        return len(tokens & target) / (len(tokens | target) or 1)

    idx = max(pool, key=score)
    return {
        "feature_name": merged.name,
        "description": "; ".join(merged.contradictions),
        "reason": "unpaired_contradiction",
        "confidence": float(merged.confidence),
        "source_ref": members[idx]["source_ref"],
    }


def _split_contradiction(feature: dict, members: list[dict]) -> dict:
    idx = _contradicting_index(members, feature["contradictions"])
    base = [m for n, m in enumerate(members) if n != idx]
    descriptions: list[str] = []
    for m in base:
        if m["description"] not in descriptions:
            descriptions.append(m["description"])
    return {
        **feature,
        "description": " ".join(descriptions),
        "source_refs": dedupe_refs([m["source_ref"] for m in base]),
        "incoming": {
            "description": members[idx]["description"],
            "source_refs": [members[idx]["source_ref"]],
        },
    }


def _single(fragment: dict) -> ConsolidatedFeature:
    return ConsolidatedFeature(
        name=fragment["feature_name"],
        description=fragment["description"],
        fragment_indices=[0],
        confidence=fragment["confidence"],
    )


async def consolidate(fragments: list[dict]) -> list[dict]:
    """Merge located fragments into consolidated feature dicts (each with ≥ 1 source_ref)."""
    features: list[dict] = []
    for group in group_fragments(fragments):
        members = [fragments[i] for i in group]
        if len(members) == 1:
            features.append(_feature_dict(_single(members[0]), members, key=f"g{group[0]}"))
            continue

        prompt = consolidation_prompt(
            name_hint=members[0]["feature_name"],
            fragments=[
                {"index": n, "name": m["feature_name"], "description": m["description"],
                 "evidence": m["snippet"]}
                for n, m in enumerate(members)
            ],
        )
        merged = await call_llm(prompt, ConsolidatedFeature)
        kept = sorted({i for i in merged.fragment_indices if 0 <= i < len(members)})
        if not kept:
            kept = list(range(len(members)))
        kept_members = [members[i] for i in kept]
        feature = _feature_dict(merged, kept_members, key=f"g{group[0]}")
        if feature["contradictions"] and len(kept_members) > 1:
            feature = _split_contradiction(feature, kept_members)
        elif feature["contradictions"]:
            # Picked up by the sweep node and written as a review item.
            feature["contradiction_flags"] = [
                _unpaired_contradiction_flag(merged, members, kept)]
        features.append(feature)
        # Fragments the merge rejected as "a different feature" are kept as their own
        # features rather than dropped (never silently miss).
        for n, member in enumerate(members):
            if n not in kept:
                features.append(
                    _feature_dict(_single(member), [member], key=f"g{group[0]}r{n}")
                )
    return features
