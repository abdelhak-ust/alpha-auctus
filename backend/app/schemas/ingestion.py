"""Pydantic schemas mirroring client/src/types.ts field-for-field (nexus-backend-standards'
"API contract" rule) — `IngestItem`, `VerdictDetail`, `Candidate` — plus the request/response
shapes `client/server.ts` already serves today, so the proxy swap in plans/ingestion.md's
"Placement" is a drop-in.

JSON on the wire is camelCase (sourceId, sourceSnippet); Python stays snake_case internally.

Known cosmetic issue: pydantic (through at least 2.12/2.13) emits an
`UnsupportedFieldAttributeWarning` for `SomeAliasedModel | None` fields (e.g.
`VerdictDetailOut.citation`, `ResolveResponse.item`) when FastAPI introspects them for its
response schema. Verified harmless — request/response alias serialization is correct (see
tests/test_ingest_routes.py's camelCase assertions); this is a pydantic-internals quirk, not a
bug in these models. Not chased further; revisit if a pydantic upgrade resolves it.
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# --- VerdictDetail (client/src/types.ts) -------------------------------------------------


class CandidateOut(CamelModel):
    id: str
    type: str  # 'item' | 'decision'
    title: str
    reason: str
    confidence: int


class CitationOut(CamelModel):
    id: str
    type: str  # 'item' | 'decision' | 'source'
    title: str
    snippet: str


class VerdictDetailOut(CamelModel):
    type: str  # 'net-new' | 'duplicate' | 'conflict' | 'impact' | 'checking'
    confidence: int
    message: str
    candidates: list[CandidateOut] = []
    citation: CitationOut | None = None


# --- IngestItem (client/src/types.ts) ----------------------------------------------------


class IngestItemOut(CamelModel):
    id: str
    title: str
    description: str
    area: str
    priority: str  # P0-P3
    source_id: str
    source_snippet: str
    verdict: VerdictDetailOut


# --- Request/response shapes matching client/server.ts today -----------------------------


class UploadTextRequest(CamelModel):
    file_name: str = ""
    file_content: str = ""
    project_id: str


class UploadResponse(CamelModel):
    success: bool = True
    count: int
    items: list[IngestItemOut]


class ResolveRequest(CamelModel):
    id: str
    action: str  # 'approve' | 'dismiss'
    project_id: str


class ResolvedCandidateOut(CamelModel):
    """What Node needs back on approve to build its own frontend-visible `Item`
    (client/server.ts's `/api/ingest/resolve` approve branch) — Node still owns `items`."""

    title: str
    description: str
    area: str
    priority: str
    source_snippet: str


class ResolveResponse(CamelModel):
    success: bool = True
    item: ResolvedCandidateOut | None = None


class SourceStatusResponse(CamelModel):
    id: str
    status: str  # WebSource['status']: synced | syncing | error | needs_auth
    detail: str | None = None


# --- Internal (not on the wire) -----------------------------------------------------------


class ChunkSpan(BaseModel):
    """One chunk with its exact character offsets into the parsed source text."""

    text: str
    char_start: int
    char_end: int


class ExtractedItem(BaseModel):
    title: str
    description: str = ""
    entity_tags: list[str] = []
    priority: str = "P2"
    snippet: str  # verbatim substring of its source chunk — enforced by extract.py


class ExtractedDecision(BaseModel):
    statement: str
    polarity: str = "affirm"  # affirm | negate
    affected_entities: list[str] = []
    snippet: str  # verbatim substring of its source chunk — enforced by extract.py


class ExtractionResult(BaseModel):
    items: list[ExtractedItem] = []
    decisions: list[ExtractedDecision] = []
