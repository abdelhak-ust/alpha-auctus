"""Ingestion stage schemas (plans/ingestion.md §11.1).

Two clearly separated groups:

1. **API shapes** — mirror `client/src/types.ts` field-for-field. Python attributes are
   snake_case; JSON is camelCase via `alias_generator=to_camel` (FastAPI serializes response
   models by alias). Optional TS fields (`error?`, `duplicate?`, `citation?`) are `None` by
   default — routes should use `response_model_exclude_none=True` so they are omitted rather
   than sent as `null`.
2. **Internal LLM extraction shapes** — what the pipeline's `generate_json(...)` calls return.
   Never sent to the client; plain snake_case.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# ---------------------------------------------------------------------------------------------
# 1. API shapes (JSON = client/src/types.ts)
# ---------------------------------------------------------------------------------------------

IngestionStatus = Literal["pending", "parsed", "extracted", "consolidated", "done", "failed"]

FeatureLifecycle = Literal[
    "extracted",
    "consolidated",
    "conflicted",
    "classified",
    "assessing",
    "awaiting_answers",
    "answered",
    "dev_ready",
    "overridden",
    "stale",
    "in_breakdown",
    "needs_review",
    "broken_down",
]

VerdictType = Literal["net-new", "duplicate", "conflict", "impact", "checking"]
Priority = Literal["P0", "P1", "P2", "P3"]


class CamelModel(BaseModel):
    """Base for API shapes: snake_case in Python, camelCase on the wire; accepts either.

    No `from_attributes`: routes build these explicitly from ORM rows (`id=str(doc.doc_id)`,
    …) per ingestion.md §11.3, so a column/field name mismatch fails loudly.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class IngestDocument(CamelModel):
    """TS `IngestDocument`."""

    id: str
    project_id: str
    filename: str
    status: IngestionStatus
    error: str | None = None
    duplicate: bool | None = None
    feature_count: int = 0
    uploaded_at: datetime


class SourceRef(CamelModel):
    """TS `SourceRef` / contract §5 `source_ref`.

    Stored in `feature_versions.source_refs` as snake_case dicts; `SourceRef.model_validate(d)`
    reads them directly (populate_by_name) and `model_dump(by_alias=True)` emits camelCase.
    Extra stored keys (e.g. a fragment `confidence`) are ignored.
    """

    doc_id: str
    doc_type: str
    chunk_id: str
    section: str
    char_start: int
    char_end: int
    snippet: str


class RegistryFeature(CamelModel):
    """TS `RegistryFeature` — a feature joined with its current version."""

    id: str
    project_id: str
    name: str
    description: str
    version_no: int
    lifecycle_state: FeatureLifecycle
    source_refs: list[SourceRef]
    updated_at: datetime


class Candidate(CamelModel):
    """TS `Candidate` (existing type; for feature conflicts `type` stays within its union)."""

    id: str
    type: Literal["item", "decision"]
    title: str
    reason: str
    confidence: float


class Citation(CamelModel):
    """TS `VerdictDetail.citation` (inline object type in types.ts)."""

    id: str
    type: Literal["item", "decision", "source"]
    title: str
    snippet: str


class VerdictDetail(CamelModel):
    """TS `VerdictDetail`."""

    type: VerdictType
    confidence: float
    message: str
    candidates: list[Candidate]
    citation: Citation | None = None


class IngestItem(CamelModel):
    """TS `IngestItem` — one review-queue row (a `review_items` row rendered for the UI)."""

    id: str
    title: str
    description: str
    area: str
    priority: Priority
    source_id: str
    source_snippet: str
    verdict: VerdictDetail


class ResolveRequest(CamelModel):
    """Body of `POST /projects/{projectId}/review-queue/{itemId}/resolve`."""

    action: Literal["approve", "dismiss"]


class ResolveResponse(CamelModel):
    ok: Literal[True] = True


class ErrorDetail(CamelModel):
    """ui_ux_design.md §7 problem + cause + fix. Sent as `{"detail": ErrorDetail}`."""

    problem: str
    cause: str
    fix: str


class ErrorResponse(CamelModel):
    detail: ErrorDetail


# ---------------------------------------------------------------------------------------------
# 2. Internal LLM extraction shapes (pipeline only — never returned by the API)
# ---------------------------------------------------------------------------------------------


class ExtractedFragment(BaseModel):
    """One feature mention found in a chunk (ingestion.md §5 step 4)."""

    feature_name: str
    description: str
    status: Literal["new", "continuation", "update"]
    # Name (or feature_id, for registry-aware extraction) of the feature this continues.
    references_feature: str | None = None
    # Where in the chunk the evidence sits — offsets relative to the chunk text.
    section: str = ""
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    snippet: str
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractionResult(BaseModel):
    """Wrapper so one `generate_json` call returns all fragments for a chunk."""

    fragments: list[ExtractedFragment] = Field(default_factory=list)


class ExtractedRelation(BaseModel):
    """A feature-to-feature relation noticed during consolidation (-> feature_relations)."""

    target_feature_name: str
    relation_type: Literal["depends_on", "extends", "conflicts_with"]
    confidence: float = Field(ge=0.0, le=1.0)


class ConsolidatedFeature(BaseModel):
    """One merged feature from a fragment group (ingestion.md §5 step 5)."""

    name: str
    description: str
    # Indexes into the fragment group that were merged — keeps source_refs traceable.
    fragment_indices: list[int] = Field(default_factory=list)
    # In-document contradictions; non-empty -> lifecycle_state = conflicted.
    contradictions: list[str] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class MatchCandidate(BaseModel):
    """A ranked existing-registry candidate for a fragment (ingestion.md §6 step 3-4)."""

    feature_id: str
    name: str
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class MatchVerdict(BaseModel):
    """Registry-aware classification of a fragment (ingestion.md §6 step 4).

    `candidates` are ranked best-first; `matched_feature_id` is the top one for
    update/conflict/duplicate and None for new. Low confidence never auto-resolves — the
    pipeline routes it to review (CLAUDE.md "never silently miss, never cry wolf").
    """

    outcome: Literal["new", "update", "conflict", "duplicate"]
    matched_feature_id: str | None = None
    candidates: list[MatchCandidate] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""


class SweepMention(BaseModel):
    """High-recall completeness-sweep hit (ingestion.md §5 step 6)."""

    name: str
    snippet: str
    chunk_ordinal: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class SweepResult(BaseModel):
    mentions: list[SweepMention] = Field(default_factory=list)
