"""MVP v0 schemas (plans/mvp-v0.md).

Two groups:

1. **API shapes** — mirror `client/src/types.ts` field-for-field. Python is snake_case; JSON
   is camelCase via `alias_generator=to_camel`. Optional TS fields are omitted when None
   (`response_model_exclude_none=True` on the routes).
2. **LLM shapes** — what the agents return. Plain snake_case; never sent to the client.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

# ---------------------------------------------------------------------------------------------
# 1. API shapes (JSON = client/src/types.ts)
# ---------------------------------------------------------------------------------------------

DocumentStatus = Literal[
    "uploaded", "converting", "extracting", "analysing", "ready", "failed"
]
FeatureStatus = Literal[
    "extracted",
    "analysed",
    "needs_clarification",
    "clarified",
    "planning",
    "tasks_ready",
]
FeatureReviewStatus = Literal["pending", "approved", "rejected"]
QuestionStatus = Literal["open", "answered", "skipped"]
TaskStatus = Literal["draft", "approved", "on_board"]
ChatRole = Literal["ai", "pm"]
ChatKind = Literal["progress", "decision", "question", "text"]
Priority = Literal["P0", "P1", "P2", "P3"]
Estimate = Literal["S", "M", "L"]


class CamelModel(BaseModel):
    """Snake_case in Python, camelCase on the wire; accepts either."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ErrorDetail(CamelModel):
    """ui_ux_design.md §7. Sent as `{"detail": ErrorDetail}`."""

    problem: str
    cause: str
    fix: str


class DocumentProgress(CamelModel):
    step: str
    done: int = 0
    total: int = 0


class MvpDocument(CamelModel):
    """TS `MvpDocument`."""

    id: str
    project_id: str
    filename: str
    mime_type: str | None = None
    size_bytes: int | None = None
    status: DocumentStatus
    progress: DocumentProgress | None = None
    error: str | None = None
    duplicate: bool | None = None
    feature_count: int = 0
    uploaded_at: datetime


class SourceQuote(CamelModel):
    """A verbatim quote. `verified` is False when the quote is not in the document."""

    quote: str
    verified: bool
    char_start: int | None = None
    char_end: int | None = None
    origin: Literal["document", "pm"] = "document"


class CitedRequirement(CamelModel):
    text: str
    quote: str | None = None


class CitedCriterion(CamelModel):
    given: str
    when: str
    then: str
    quote: str | None = None


class FeatureQuestionOut(CamelModel):
    """TS `FeatureQuestion`."""

    id: str
    feature_id: str
    question: str
    why: str
    target_field: str
    is_follow_up: bool
    status: QuestionStatus
    answer: str | None = None
    answered_at: datetime | None = None
    ordinal: int


class FeatureDetailsOut(CamelModel):
    """TS `FeatureDetails` — questions live on the feature, not here."""

    description: str = ""
    user_roles: list[str] = Field(default_factory=list)
    functional_requirements: list[CitedRequirement] = Field(default_factory=list)
    acceptance_criteria: list[CitedCriterion] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)


class GeneratedTaskOut(CamelModel):
    """TS `GeneratedTask`."""

    id: str
    feature_id: str
    title: str
    description: str
    area: str
    priority: Priority
    acceptance_criteria: list[CitedCriterion] = Field(default_factory=list)
    estimate: Estimate
    traces_to: list[str] = Field(default_factory=list)
    subtasks: list[str] = Field(default_factory=list)
    definition_of_done: list[str] = Field(default_factory=list)
    review_notes: str | None = None
    status: TaskStatus
    board_item_id: int | None = None
    ordinal: int


class FeatureOut(CamelModel):
    """TS `Feature`."""

    id: str
    project_id: str
    document_id: str
    name: str
    summary: str
    details: FeatureDetailsOut | None = None
    source_quotes: list[SourceQuote] = Field(default_factory=list)
    status: FeatureStatus
    review_status: FeatureReviewStatus = "pending"
    position: int
    questions: list[FeatureQuestionOut] = Field(default_factory=list)
    tasks: list[GeneratedTaskOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class FeaturePatch(CamelModel):
    """PATCH /features/{id} — human review + inline edit. Never generates tasks."""

    review_status: FeatureReviewStatus | None = None
    name: str | None = None
    summary: str | None = None


class ChatMessageOut(CamelModel):
    """TS `ChatMessage`."""

    id: str
    project_id: str
    role: ChatRole
    text: str
    question_id: str | None = None
    feature_id: str | None = None
    kind: ChatKind | None = None
    created_at: datetime


class AgentActivity(CamelModel):
    """TS `AgentActivity` — one audit_events row rendered for the demo panel."""

    id: str
    ts: datetime
    graph: str
    node: str
    agent: str | None = None
    detail: str


class ClarificationNext(CamelModel):
    question_id: str
    feature_id: str
    feature_name: str
    question: str
    why: str


class ClarificationState(CamelModel):
    history: list[ChatMessageOut]
    next: ClarificationNext | None = None
    remaining: int = 0


class ClarificationAnswerRequest(CamelModel):
    question_id: str
    answer: str


class ClarificationSkipRequest(CamelModel):
    question_id: str


class ClarificationSkipRemainingRequest(CamelModel):
    """Human skip of every open question on one feature — never auto-answers."""

    feature_id: str


class WorkflowState(CamelModel):
    """GET /workflow — full chat history including decisions."""

    history: list[ChatMessageOut]


class ClarificationAnswerResponse(CamelModel):
    feature: FeatureOut | None = None
    changes: list[str] = Field(default_factory=list)
    next: ClarificationNext | None = None
    remaining: int = 0


class TaskPatch(CamelModel):
    status: TaskStatus | None = None
    title: str | None = None
    description: str | None = None
    priority: Priority | None = None
    board_item_id: int | None = None
    subtasks: list[str] | None = None
    definition_of_done: list[str] | None = None


class DocumentMarkdown(CamelModel):
    markdown: str


AskCitationType = Literal["item", "decision", "source"]
AskTurnRole = Literal["user", "ai"]


class AskCitation(CamelModel):
    """TS `AskCitation` — chip on a drawer Ask answer."""

    id: str
    type: AskCitationType
    title: str
    snippet: str | None = None


class AskTurn(CamelModel):
    """TS `AskTurn` — one prior line in the drawer thread."""

    role: AskTurnRole
    text: str


class AskItemSnapshot(CamelModel):
    """Board card fields the Node/SQLite store owns — backend does not load the card."""

    title: str
    description: str = ""
    area: str = ""
    priority: Priority | None = None


class AskRequest(CamelModel):
    """POST /projects/{projectId}/ask."""

    query: str
    board_item_id: int
    item: AskItemSnapshot
    history: list[AskTurn] = Field(default_factory=list)


class AskResponse(CamelModel):
    """TS `AskResponse`."""

    answer: str
    citations: list[AskCitation] = Field(default_factory=list)


class MemoryBoardItem(CamelModel):
    """A board card the Node/SQLite store owns — snapshot for Memory Ask."""

    id: str
    title: str
    description: str = ""
    area: str = ""
    status: str = ""

    @field_validator("id", mode="before")
    @classmethod
    def _id_str(cls, value: object) -> str:
        return str(value)


class MemoryAskRequest(CamelModel):
    """POST /projects/{projectId}/memory/ask."""

    query: str
    history: list[AskTurn] = Field(default_factory=list)
    board_items: list[MemoryBoardItem] = Field(default_factory=list)


VerdictType = Literal["net-new", "duplicate", "conflict", "impact", "checking"]
VerdictCandidateType = Literal["item", "decision"]
VerdictCitationType = Literal["item", "decision", "source"]


class VerdictCandidate(CamelModel):
    """TS `Candidate` — ranked match on a verdict."""

    id: str
    type: VerdictCandidateType
    title: str
    reason: str
    confidence: int


class VerdictCitation(CamelModel):
    """Optional cite on TS `VerdictDetail`."""

    id: str
    type: VerdictCitationType
    title: str
    snippet: str


class VerdictDetail(CamelModel):
    """TS `VerdictDetail` — classifier response (never writes the board)."""

    type: VerdictType
    confidence: int
    message: str
    candidates: list[VerdictCandidate] = Field(default_factory=list)
    citation: VerdictCitation | None = None


class VerdictCheckItem(CamelModel):
    """The new or edited board card the client already persisted."""

    id: str
    title: str
    description: str = ""
    area: str = ""

    @field_validator("id", mode="before")
    @classmethod
    def _id_str(cls, value: object) -> str:
        return str(value)


class VerdictBoardItem(CamelModel):
    """Another card on the board — client-owned; exclude `item.id`."""

    id: str
    title: str
    description: str = ""
    area: str = ""
    status: str = ""

    @field_validator("id", mode="before")
    @classmethod
    def _id_str(cls, value: object) -> str:
        return str(value)


class VerdictCheckRequest(CamelModel):
    """POST /projects/{projectId}/verdicts/check."""

    item: VerdictCheckItem
    board_items: list[VerdictBoardItem] = Field(default_factory=list)


ImpactNodeType = Literal["item", "area", "decision", "source"]
ImpactEdgeType = Literal[
    "depends-on", "affects", "duplicate", "contradicts", "supersedes"
]


class ImpactNode(CamelModel):
    """TS `ImpactNode` — one graph node snapshot (no layout)."""

    id: str
    type: ImpactNodeType
    label: str


class ImpactEdge(CamelModel):
    """TS `ImpactEdge` — typed labeled link between two nodes."""

    id: str
    source: str
    target: str
    type: ImpactEdgeType
    label: str | None = None


class ImpactNeighbor(CamelModel):
    """One neighbor of the selected node, plus the connecting edge type."""

    id: str
    type: ImpactNodeType
    label: str
    edge_type: ImpactEdgeType


class ImpactExplainRequest(CamelModel):
    """POST /projects/{projectId}/impact/explain — selected subgraph only."""

    node_id: str
    node: ImpactNode
    neighbors: list[ImpactNeighbor] = Field(default_factory=list)
    verdict_snippet: str | None = None


class ImpactExplainResponse(CamelModel):
    """TS `ImpactExplainResponse` / `ImpactExplain`."""

    headline: str
    text: str
    citations: list[AskCitation] = Field(default_factory=list)


AuthorDocType = Literal["brd", "spec", "tree"]
AuthorTimeFrame = Literal["30", "90", "365"]
AuthorVerdictType = Literal["net-new", "duplicate", "conflict", "impact", "checking"]


class AuthorBoardItem(CamelModel):
    """A board card the Node/SQLite store owns — snapshot for Author."""

    id: str
    title: str
    description: str = ""
    area: str = ""
    status: str = ""
    created_at: str = ""
    verdict_type: AuthorVerdictType | None = None

    @field_validator("id", mode="before")
    @classmethod
    def _id_str(cls, value: object) -> str:
        return str(value)

    @field_validator("created_at", mode="before")
    @classmethod
    def _created_str(cls, value: object) -> str:
        return "" if value is None else str(value)


class AuthorDecision(CamelModel):
    """A SQLite decision the client already has — never invent one."""

    id: str
    title: str
    description: str = ""
    area: str = ""

    @field_validator("id", mode="before")
    @classmethod
    def _id_str(cls, value: object) -> str:
        return str(value)


class AuthorConflict(CamelModel):
    """TS `AuthorConflict` — a scoped board card whose verdict is conflict."""

    id: str
    title: str


class AuthorRequest(CamelModel):
    """POST /projects/{projectId}/author."""

    type: AuthorDocType
    area: str = "all"
    time_frame: AuthorTimeFrame = "30"
    board_items: list[AuthorBoardItem] = Field(default_factory=list)
    decisions: list[AuthorDecision] = Field(default_factory=list)

    @field_validator("time_frame", mode="before")
    @classmethod
    def _time_frame_str(cls, value: object) -> object:
        return str(value) if isinstance(value, int) else value


class AuthorResponse(CamelModel):
    """TS `AuthorResponse`."""

    document: str
    unresolved_conflicts_count: int = 0
    conflicts: list[AuthorConflict] = Field(default_factory=list)
    citations: list[AskCitation] = Field(default_factory=list)


# ---------------------------------------------------------------------------------------------
# 2. LLM shapes (agents only — never returned by the API)
# ---------------------------------------------------------------------------------------------


class ExtractedFeature(BaseModel):
    name: str
    summary: str
    source_quotes: list[str] = Field(default_factory=list)


class ExtractedFeatures(BaseModel):
    features: list[ExtractedFeature] = Field(default_factory=list)


class MergedFeatures(BaseModel):
    features: list[ExtractedFeature] = Field(default_factory=list)


class AnalystQuestion(BaseModel):
    question: str
    why: str
    target_field: str


class CitedReq(BaseModel):
    text: str
    quote: str = ""


class CitedAC(BaseModel):
    given: str
    when: str
    then: str
    quote: str = ""


class FeatureDetails(BaseModel):
    """Analyst structured response (plans/mvp-v0.md Feature Analyst output)."""

    description: str = ""
    user_roles: list[str] = Field(default_factory=list)
    functional_requirements: list[CitedReq] = Field(default_factory=list)
    acceptance_criteria: list[CitedAC] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    questions: list[AnalystQuestion] = Field(default_factory=list)


class PlannedTask(BaseModel):
    title: str
    description: str
    area: str = ""
    priority: Literal["P0", "P1", "P2", "P3"] = "P2"
    acceptance_criteria: list[CitedAC] = Field(default_factory=list)
    estimate: Literal["S", "M", "L"] = "M"
    traces_to: list[str] = Field(default_factory=list)
    subtasks: list[str] = Field(default_factory=list)
    definition_of_done: list[str] = Field(default_factory=list)


class PlannedTasks(BaseModel):
    tasks: list[PlannedTask] = Field(default_factory=list)


class ReviewIssue(BaseModel):
    task_index: int
    problem: str


class ReviewVerdict(BaseModel):
    passed: bool = Field(alias="pass")
    issues: list[ReviewIssue] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class AskLlmCitation(BaseModel):
    id: str
    type: Literal["item", "decision", "source"]
    title: str
    snippet: str = ""


class AskResult(BaseModel):
    """Structured ask-a-task reply — mapped to AskResponse before the wire."""

    answer: str
    citations: list[AskLlmCitation] = Field(default_factory=list)


class VerdictLlmCandidate(BaseModel):
    id: str
    type: Literal["item", "decision"]
    title: str
    reason: str
    confidence: int = 0


class VerdictLlmCitation(BaseModel):
    id: str
    type: Literal["item", "decision", "source"]
    title: str
    snippet: str = ""


class VerdictResult(BaseModel):
    """Structured classifier reply — mapped to VerdictDetail before the wire."""

    type: Literal["net-new", "duplicate", "conflict", "impact"]
    confidence: int = 0
    message: str = ""
    candidates: list[VerdictLlmCandidate] = Field(default_factory=list)
    citation: VerdictLlmCitation | None = None


class ImpactExplainResult(BaseModel):
    """Structured explain reply — mapped to ImpactExplainResponse before the wire."""

    headline: str = ""
    text: str = ""
    citations: list[AskLlmCitation] = Field(default_factory=list)


class AuthorResult(BaseModel):
    """Structured author reply — mapped to AuthorResponse before the wire."""

    document: str = ""
    citations: list[AskLlmCitation] = Field(default_factory=list)


def details_to_api(raw: dict[str, Any] | None) -> FeatureDetailsOut | None:
    """LLM/DB snake_case details → API FeatureDetailsOut (questions live on the feature)."""
    if not raw:
        return None
    return FeatureDetailsOut(
        description=str(raw.get("description") or ""),
        user_roles=list(raw.get("user_roles") or []),
        functional_requirements=[
            CitedRequirement(text=str(r.get("text", "")), quote=r.get("quote") or None)
            for r in (raw.get("functional_requirements") or [])
            if isinstance(r, dict)
        ],
        acceptance_criteria=[
            CitedCriterion(
                given=str(c.get("given", "")),
                when=str(c.get("when", "")),
                then=str(c.get("then", "")),
                quote=c.get("quote") or None,
            )
            for c in (raw.get("acceptance_criteria") or [])
            if isinstance(c, dict)
        ],
        constraints=list(raw.get("constraints") or []),
        dependencies=list(raw.get("dependencies") or []),
        out_of_scope=list(raw.get("out_of_scope") or []),
    )


def quotes_to_api(raw: list[dict[str, Any]] | None) -> list[SourceQuote]:
    out: list[SourceQuote] = []
    for q in raw or []:
        if not isinstance(q, dict):
            continue
        origin = q.get("origin") if q.get("origin") in ("document", "pm") else "document"
        out.append(
            SourceQuote(
                quote=str(q.get("quote") or ""),
                verified=bool(q.get("verified")),
                char_start=q.get("char_start"),
                char_end=q.get("char_end"),
                origin=origin,
            )
        )
    return out
