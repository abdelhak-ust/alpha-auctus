"""Shared DB helpers for the three graphs (status, audit, feature writes)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session_factory
from app.graph.audit import record_audit
from app.ingest.cite import verify_quote, verify_quotes
from app.models import Document, Feature, FeatureQuestion, Task
from app.schemas.mvp import FeatureDetails


def error_json(problem: str, cause: str, fix: str) -> str:
    return json.dumps({"problem": problem, "cause": cause, "fix": fix})


def session():
    return get_session_factory()()


async def load_document(db: AsyncSession, document_id: str) -> Document | None:
    return await db.get(Document, uuid.UUID(document_id))


async def set_document_progress(
    db: AsyncSession,
    doc: Document,
    *,
    status: str | None = None,
    step: str | None = None,
    done: int | None = None,
    total: int | None = None,
    markdown: str | None = None,
    error: str | None = None,
) -> None:
    if status is not None:
        doc.status = status
    if markdown is not None:
        doc.markdown = markdown
    if error is not None:
        doc.error = error
    if step is not None or done is not None or total is not None:
        prev = dict(doc.progress or {})
        if step is not None:
            prev["step"] = step
        if done is not None:
            prev["done"] = done
        if total is not None:
            prev["total"] = total
        doc.progress = prev
    await db.commit()


async def fail_document(document_id: str, problem: str, cause: str, fix: str) -> None:
    async with get_session_factory()() as db:
        doc = await load_document(db, document_id)
        if doc is None:
            return
        doc.status = "failed"
        doc.error = error_json(problem, cause, fix)
        await db.commit()


async def audit(
    db: AsyncSession,
    *,
    project_id: str,
    feature_id: uuid.UUID | str | None,
    graph: str,
    node: str,
    agent: str,
    detail: str,
) -> None:
    await record_audit(
        db,
        project_id=project_id,
        feature_id=feature_id,
        graph=graph,
        node=node,
        type="agent_step",
        detail={"agent": agent, "detail": detail},
    )
    await db.commit()


def details_to_json(details: FeatureDetails) -> dict[str, Any]:
    data = details.model_dump()
    data.pop("questions", None)
    return data


def verify_details(markdown: str, details: FeatureDetails) -> FeatureDetails:
    """Mark requirement / AC quotes verified or unverified against the document."""
    reqs = []
    for r in details.functional_requirements:
        if r.quote:
            found = verify_quote(markdown, r.quote)
            quote = found["quote"] if found["verified"] else r.quote
            reqs.append(r.model_copy(update={"quote": quote}))
        else:
            reqs.append(r)
    acs = []
    for c in details.acceptance_criteria:
        if c.quote:
            found = verify_quote(markdown, c.quote)
            quote = found["quote"] if found["verified"] else c.quote
            acs.append(c.model_copy(update={"quote": quote}))
        else:
            acs.append(c)
    return details.model_copy(update={"functional_requirements": reqs, "acceptance_criteria": acs})


def quote_verified_flag(markdown: str, quote: str | None) -> bool:
    if not quote:
        return False
    return bool(verify_quote(markdown, quote)["verified"])


async def persist_analysed_features(
    db: AsyncSession,
    *,
    document_id: str,
    project_id: str,
    markdown: str,
    analysed: list[dict[str, Any]],
) -> None:
    """Replace this document's features with the analysed set (re-run of a failed/retry doc)."""
    doc = await load_document(db, document_id)
    if doc is None:
        return
    existing = (
        await db.execute(select(Feature).where(Feature.document_id == doc.id))
    ).scalars().all()
    for feat in existing:
        await db.delete(feat)
    await db.flush()

    for i, item in enumerate(analysed):
        draft = item["draft"]
        details: FeatureDetails = item["details"]
        quotes = verify_quotes(markdown, list(draft.get("source_quotes") or []))
        # Also lift quotes from details so unverified ones surface on the card.
        for r in details.functional_requirements:
            if r.quote:
                q = verify_quote(markdown, r.quote)
                if q["quote"] and q["quote"] not in {x["quote"] for x in quotes}:
                    quotes.append(q)
        feature = Feature(
            project_id=project_id,
            document_id=doc.id,
            name=str(draft.get("name") or "Untitled"),
            summary=str(draft.get("summary") or ""),
            details=details_to_json(details),
            source_quotes=quotes,
            status="needs_clarification" if details.questions else "analysed",
            position=i,
        )
        db.add(feature)
        await db.flush()
        for ord_, q in enumerate(details.questions):
            db.add(
                FeatureQuestion(
                    project_id=project_id,
                    feature_id=feature.id,
                    question=q.question,
                    why=q.why,
                    target_field=q.target_field,
                    is_follow_up=False,
                    status="open",
                    ordinal=ord_,
                )
            )
        await audit(
            db,
            project_id=project_id,
            feature_id=feature.id,
            graph="document",
            node="persist",
            agent="persist",
            detail=f"Saved feature “{feature.name}” with {len(details.questions)} question(s).",
        )
    doc.status = "ready"
    doc.progress = {"step": "ready", "done": len(analysed), "total": len(analysed)}
    doc.error = None
    await db.commit()


def apply_field_update(details: dict[str, Any], field: str, value: str) -> dict[str, Any]:
    """Apply a Clarifier field write. Values are cited as PM answers by the caller."""
    out = dict(details)
    key = field.strip().replace(" ", "_").lower()
    aliases = {
        "description": "description",
        "user_roles": "user_roles",
        "user_role": "user_roles",
        "functional_requirements": "functional_requirements",
        "functional_requirement": "functional_requirements",
        "acceptance_criteria": "acceptance_criteria",
        "acceptance_criterion": "acceptance_criteria",
        "constraints": "constraints",
        "constraint": "constraints",
        "dependencies": "dependencies",
        "dependency": "dependencies",
        "out_of_scope": "out_of_scope",
    }
    mapped = aliases.get(key, key)
    if mapped == "description":
        out["description"] = value
    elif mapped in {"user_roles", "constraints", "dependencies", "out_of_scope"}:
        cur = list(out.get(mapped) or [])
        if value not in cur:
            cur.append(value)
        out[mapped] = cur
    elif mapped == "functional_requirements":
        cur = list(out.get(mapped) or [])
        cur.append({"text": value, "quote": value})
        out[mapped] = cur
    elif mapped == "acceptance_criteria":
        cur = list(out.get(mapped) or [])
        cur.append(
            {
                "given": "the feature is implemented",
                "when": "a user exercises it",
                "then": value,
                "quote": value,
            }
        )
        out[mapped] = cur
    else:
        # Unknown field — store on description so the write is not dropped.
        prev = str(out.get("description") or "")
        out["description"] = f"{prev}\n{value}".strip() if prev else value
    return out


async def load_feature(db: AsyncSession, feature_id: str) -> Feature | None:
    stmt = (
        select(Feature)
        .options(
            selectinload(Feature.questions),
            selectinload(Feature.tasks),
            selectinload(Feature.document),
        )
        .where(Feature.id == uuid.UUID(feature_id))
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def persist_task_drafts(
    db: AsyncSession,
    *,
    feature: Feature,
    drafts: list[Any],
    review_notes: str | None,
) -> None:
    """Replace draft/approved tasks; keep `on_board` rows."""
    existing = (
        await db.execute(select(Task).where(Task.feature_id == feature.id))
    ).scalars().all()
    kept = [t for t in existing if t.status == "on_board"]
    for t in existing:
        if t.status != "on_board":
            await db.delete(t)
    await db.flush()
    start = len(kept)
    for i, draft in enumerate(drafts):
        ac = [
            {"given": c.given, "when": c.when, "then": c.then}
            for c in (draft.acceptance_criteria or [])
        ]
        db.add(
            Task(
                project_id=feature.project_id,
                feature_id=feature.id,
                title=draft.title,
                description=draft.description,
                area=draft.area or "",
                priority=draft.priority if draft.priority in {"P0", "P1", "P2", "P3"} else "P2",
                acceptance_criteria=ac,
                estimate=draft.estimate if draft.estimate in {"S", "M", "L"} else "M",
                traces_to=list(draft.traces_to or []),
                subtasks=list(getattr(draft, "subtasks", None) or []),
                definition_of_done=list(getattr(draft, "definition_of_done", None) or []),
                review_notes=review_notes,
                status="draft",
                ordinal=start + i,
            )
        )
    feature.status = "tasks_ready"
    feature.updated_at = datetime.now(UTC)
    await db.commit()
