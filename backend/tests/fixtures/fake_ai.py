"""Deterministic stand-ins for `app.ai.generate_json` / `app.ai.embed_texts` used by the
ingest tests (never the real Vertex AI — plans/ingestion.md §11.1).

- `FakeLLM` answers each ingest prompt type from a small script keyed on sentences in the
  fixture documents (tests/fixtures/spec_a.md, spec_b.md), and records every call.
- `fake_embed` maps text to a topic one-hot (+ a small constant so no vector is zero): same
  topic ⇒ cosine ≈ 1, different topics ⇒ ≈ 0, which makes Qdrant matching predictable.
- `qdrant_memory` swaps `app.vector` onto an in-memory Qdrant client for one test.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import pytest_asyncio
from qdrant_client import AsyncQdrantClient

from app import vector
from app.config import get_settings
from app.schemas.ingestion import (
    ConsolidatedFeature,
    ExtractionResult,
    MatchVerdict,
    SweepResult,
)

# sentence → (feature_name, description, status, references_feature)
FRAGMENTS: dict[str, tuple[str, str, str, str | None]] = {
    "Users sign in with SSO through Okta.": (
        "Single sign-on", "Users sign in with SSO through Okta.", "new", None),
    "The single sign-on flow must also support Azure AD for customers who do not use Okta.": (
        "Single sign-on", "SSO must also support Azure AD.", "continuation", "Single sign-on"),
    "Sessions expire after 30 minutes of inactivity.": (
        "Session timeout", "Sessions expire after 30 minutes of inactivity.", "new", None),
    "Sessions expire after 8 hours of inactivity.": (
        "Session timeout", "Sessions expire after 8 hours of inactivity.", "new", None),
    "Admins can export the audit log as CSV.": (
        "Audit log export", "Admins can export the audit log as CSV.", "new", None),
    "The CSV export also includes the IP address of the actor for every event.": (
        "Audit log export", "The CSV export includes the actor's IP address.", "new", None),
}
# A hallucinated quote: emitted whenever this trigger sentence is in the chunk, but the quote
# itself is not in the document — it must become a sweep flag, never a feature.
HALLUCINATION_TRIGGER = "Password login is not offered for employees."
HALLUCINATED_QUOTE = "Passwords must rotate every 90 days."
UNEXTRACTED_MENTION = ("Mobile app", "We might offer a mobile app someday.")

# Registry classification by incoming feature name (doc B vs doc A's registry).
MATCH_OUTCOMES = {"Audit log export": "update", "Single sign-on": "duplicate",
                  "Session timeout": "conflict"}

TOPICS = {
    0: ("sso", "single sign-on", "okta", "azure"),
    1: ("session",),
    2: ("export", "csv"),
    3: ("mobile",),
}


def _between(prompt: str, start: str, end: str) -> str:
    return prompt.split(start, 1)[1].split(end, 1)[0]


def _chunk_text(prompt: str) -> str:
    return _between(prompt, "CHUNK:\n<<<\n", "\n>>>")


@dataclass
class FakeLLM:
    match_confidence: float = 0.9
    calls: list[tuple[str, str]] = field(default_factory=list)  # (schema name, prompt)

    def count(self, schema: type) -> int:
        return sum(1 for name, _ in self.calls if name == schema.__name__)

    async def __call__(self, prompt: str, schema: type, *, system: str | None = None):
        self.calls.append((schema.__name__, prompt))
        if schema is ExtractionResult:
            return self._extract(prompt)
        if schema is SweepResult:
            return self._sweep(prompt)
        if schema is MatchVerdict:
            return self._match(prompt)
        if schema is ConsolidatedFeature:
            if prompt.startswith("Merge the new detail"):
                return self._merge(prompt)
            return self._consolidate(prompt)
        raise AssertionError(f"unexpected schema {schema}")

    def _extract(self, prompt: str) -> ExtractionResult:
        text = _chunk_text(prompt)
        found = sorted((text.find(s), s) for s in FRAGMENTS if s in text)
        fragments = []
        for _pos, sentence in found:
            name, desc, status, ref = FRAGMENTS[sentence]
            fragments.append({
                "feature_name": name, "description": desc, "status": status,
                "references_feature": ref, "snippet": sentence,
                # deliberately wrong offsets: the pipeline must not trust them
                "char_start": 0, "char_end": 5, "confidence": 0.9,
            })
        if HALLUCINATION_TRIGGER in text:
            fragments.append({
                "feature_name": "Password rotation", "description": "Passwords rotate.",
                "status": "new", "snippet": HALLUCINATED_QUOTE, "char_start": 0,
                "char_end": 10, "confidence": 0.5,
            })
        return ExtractionResult.model_validate({"fragments": fragments})

    def _sweep(self, prompt: str) -> SweepResult:
        text = _chunk_text(prompt)
        mentions = [
            {"name": FRAGMENTS[s][0], "snippet": s, "confidence": 0.8}
            for s in FRAGMENTS if s in text
        ]
        name, sentence = UNEXTRACTED_MENTION
        if sentence in text:
            mentions.append({"name": name, "snippet": sentence, "confidence": 0.4})
        return SweepResult.model_validate({"mentions": mentions})

    def _consolidate(self, prompt: str) -> ConsolidatedFeature:
        fragments = json.loads(
            _between(prompt, "Fragments (index, name, description, verbatim evidence):\n",
                     "\n\nReturn:")
        )
        descriptions = [f["description"] for f in fragments]
        joined = " ".join(descriptions)
        contradictions = (
            ["30 minutes vs 8 hours of inactivity"]
            if "30 minutes" in joined and "8 hours" in joined else []
        )
        return ConsolidatedFeature(
            name=fragments[0]["name"], description=joined,
            fragment_indices=[f["index"] for f in fragments],
            contradictions=contradictions, confidence=0.9,
        )

    def _match(self, prompt: str) -> MatchVerdict:
        feature = json.loads(_between(prompt, "NEW FEATURE:\n", "\n\nEXISTING CANDIDATES"))
        candidates = json.loads(
            _between(prompt, "EXISTING CANDIDATES (with similarity scores):\n", "\n\noutcome:")
        )
        outcome = MATCH_OUTCOMES.get(feature["name"], "new")
        top = candidates[0]
        return MatchVerdict(
            outcome=outcome,
            matched_feature_id=None if outcome == "new" else top["feature_id"],
            candidates=[{"feature_id": c["feature_id"], "name": c["name"],
                         "reason": "same topic", "confidence": 0.9} for c in candidates],
            confidence=self.match_confidence,
            rationale=f"scripted {outcome}",
        )

    def _merge(self, prompt: str) -> ConsolidatedFeature:
        existing = json.loads(_between(prompt, "EXISTING:\n", "\n\nINCOMING:"))
        incoming = json.loads(_between(prompt, "INCOMING:\n", "\n\nReturn"))
        return ConsolidatedFeature(
            name=existing["name"],
            description=f"{existing['description']} {incoming['description']}",
            fragment_indices=[], confidence=0.9,
        )


def topic_vector(text: str) -> list[float]:
    dim = get_settings().embedding_dim
    vec = [0.0] * dim
    lowered = text.lower()
    for idx, words in TOPICS.items():
        if any(re.search(rf"\b{re.escape(w)}", lowered) for w in words):
            vec[idx] = 1.0
    vec[dim - 1] = 0.05
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec]


@dataclass
class FakeEmbedder:
    calls: list[tuple[str, int]] = field(default_factory=list)  # (task_type, batch size)

    async def __call__(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        self.calls.append((task_type, len(texts)))
        return [topic_vector(t) for t in texts]


@dataclass
class FakeQueue:
    calls: list[tuple[str, dict]] = field(default_factory=list)

    async def __call__(self, job_name: str, **kwargs) -> str:
        self.calls.append((job_name, kwargs))
        return f"job-{len(self.calls)}"

    def readiness_feature_ids(self) -> list[str]:
        return [kw["feature_id"] for name, kw in self.calls if name == "readiness_run"]


@pytest_asyncio.fixture
async def qdrant_memory() -> AsyncIterator[AsyncQdrantClient]:
    client = AsyncQdrantClient(location=":memory:")
    vector.set_client(client)
    await vector.ensure_collections()
    try:
        yield client
    finally:
        vector.reset_client()
        await client.close()


def session_factory_for(session):
    """A session factory that always hands out the test's `db_session` (savepoint mode, so
    the pipeline's commits never leak out of the test's outer transaction)."""

    @asynccontextmanager
    async def factory():
        yield session

    return factory
