"""Provisional placeholder verdict for ingested candidates.

plans/ingestion.md "Conflict-check coupling": every extracted candidate should be routed
through the Conflict & Dedup Engine before landing, but that engine is P5 — not built yet.
This ports today's simple *deterministic* heuristic (`mockAnalysis` in client/server.ts,
lines 443-521) rather than its LLM-based sibling (`performVerdictAnalysis`), since a
provisional placeholder doesn't need a second LLM round-trip per candidate — same keyword
matching, same verdict shape (`VerdictDetailOut`), swapped for the real P5 engine later with
no change to callers.

The current project's items/decisions still live in the Node server's JSON store (nothing has
migrated them yet), so this reads them from Node's existing `/api/state` rather than
duplicating that store here — see app/config.py's `node_server_url`.
"""

import re

import httpx

from app.config import get_settings
from app.schemas.ingestion import CandidateOut, CitationOut, VerdictDetailOut

_SSO = re.compile(r"\bsso\b|single sign|\bcredential|\bpassword\b", re.IGNORECASE)
_SSO_DECISION = re.compile(r"idp|sso|sign-on|sign on|credential", re.IGNORECASE)
_CSV = re.compile(r"\bcsv\b|\bexport\b", re.IGNORECASE)
_CSV_ITEM = re.compile(r"csv|export", re.IGNORECASE)
_IMPACT = re.compile(r"billing|checkout|\bauth\b", re.IGNORECASE)
_IMPACT_ITEM = re.compile(r"auth|billing|checkout", re.IGNORECASE)


async def _fetch_project_state(project_id: str) -> dict:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(
                f"{settings.node_server_url}/api/state", params={"projectId": project_id}
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError:
            # Node server not reachable (e.g. pipeline run standalone/in tests) — degrade to
            # "nothing to check against" rather than failing the whole ingest.
            return {"items": [], "decisions": []}


def _net_new() -> VerdictDetailOut:
    return VerdictDetailOut(
        type="net-new", confidence=100, message="Net-new — nothing like this yet"
    )


def _snippet(record: dict) -> str:
    return (record.get("description") or "")[:180]


def _matched_verdict(
    *, kind: str, confidence: int, message: str, record: dict, record_type: str, reason: str
) -> VerdictDetailOut:
    record_id = str(record["id"])
    title = record["title"]
    return VerdictDetailOut(
        type=kind,
        confidence=confidence,
        message=message.format(id=record_id, title=title),
        candidates=[
            CandidateOut(
                id=record_id, type=record_type, title=title, reason=reason, confidence=confidence
            )
        ],
        citation=CitationOut(
            id=record_id, type=record_type, title=title, snippet=_snippet(record)
        ),
    )


async def provisional_verdict(title: str, description: str, project_id: str) -> VerdictDetailOut:
    """The same keyword heuristic as today's mockAnalysis, ported 1:1 — see module docstring."""
    state = await _fetch_project_state(project_id)
    items: list[dict] = state.get("items", [])
    decisions: list[dict] = state.get("decisions", [])
    blob = f"{title} {description}"

    if _SSO.search(blob):
        dec = next(
            (
                d
                for d in decisions
                if _SSO_DECISION.search(f"{d.get('title', '')} {d.get('description', '')}")
            ),
            None,
        )
        if dec:
            return _matched_verdict(
                kind="conflict",
                confidence=88,
                message="Conflicts with Decision #{id} ({title})",
                record=dec,
                record_type="decision",
                reason="Decision mandates relying on the customer's identity provider "
                "instead of an in-house credential store.",
            )

    if _CSV.search(blob):
        it = next((i for i in items if _CSV_ITEM.search(i.get("title", ""))), None)
        if it:
            return _matched_verdict(
                kind="duplicate",
                confidence=91,
                message="Looks like a duplicate of #{id} ({title})",
                record=it,
                record_type="item",
                reason="Covers the same export flow already captured in this item.",
            )

    if _IMPACT.search(blob):
        it = next(
            (
                i
                for i in items
                if i.get("area") == "auth" or _IMPACT_ITEM.search(i.get("title", ""))
            ),
            None,
        )
        if it:
            return _matched_verdict(
                kind="impact",
                confidence=84,
                message="Touches the same area as #{id} ({title})",
                record=it,
                record_type="item",
                reason="Shares the billing/auth controllers and security configuration.",
            )

    return _net_new()
