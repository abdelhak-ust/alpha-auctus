"""document_graph: convert → split → extract → merge → analyse → verify → persist."""

from __future__ import annotations

import asyncio
import logging
import operator
from pathlib import Path
from typing import Annotated, Any, TypedDict

import anyio
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.agents.analyst import analyse_feature
from app.agents.extractor import extract_features, merge_features
from app.agents.graphs._persist import (
    audit,
    fail_document,
    persist_analysed_features,
    set_document_progress,
    verify_details,
)
from app.agents.llm import VertexNotConfigured
from app.config import get_settings
from app.db.session import get_session_factory
from app.ingest.cite import verify_quotes
from app.ingest.convert import EmptyDocument, UnsupportedDocumentType, convert_to_markdown
from app.ingest.split import split_markdown
from app.models import Document
from app.schemas.mvp import ExtractedFeature, FeatureDetails

logger = logging.getLogger(__name__)

_analyst_sema: asyncio.Semaphore | None = None
_compiled = None


def _sema() -> asyncio.Semaphore:
    global _analyst_sema
    if _analyst_sema is None:
        _analyst_sema = asyncio.Semaphore(get_settings().agent_concurrency)
    return _analyst_sema


class DocumentState(TypedDict, total=False):
    document_id: str
    project_id: str
    markdown: str
    chunks: list[dict[str, Any]]
    extracted: list[dict[str, Any]]
    features: list[dict[str, Any]]
    analysed: Annotated[list[dict[str, Any]], operator.add]
    ready: list[dict[str, Any]]
    feature: dict[str, Any]


async def _doc(document_id: str) -> Document:
    async with get_session_factory()() as db:
        doc = await db.get(Document, __import__("uuid").UUID(document_id))
        if doc is None:
            raise RuntimeError(f"document {document_id} not found")
        return doc


async def convert_node(state: DocumentState) -> dict[str, Any]:
    settings = get_settings()
    async with get_session_factory()() as db:
        doc = await db.get(Document, __import__("uuid").UUID(state["document_id"]))
        if doc is None:
            raise RuntimeError("document missing")
        await set_document_progress(
            db, doc, status="converting", step="converting", done=0, total=1
        )
        blob = Path(settings.blob_dir) / (doc.blob_path or "")
        raw = await anyio.Path(blob).read_bytes()
        markdown = await anyio.to_thread.run_sync(convert_to_markdown, raw, doc.filename)
        await set_document_progress(
            db, doc, status="extracting", step="extracting", done=0, total=1, markdown=markdown
        )
        await audit(
            db,
            project_id=doc.project_id,
            feature_id=None,
            graph="document",
            node="convert",
            agent="convert",
            detail=f"Converted {doc.filename} to Markdown ({len(markdown)} chars).",
        )
        return {"project_id": doc.project_id, "markdown": markdown}


async def split_node(state: DocumentState) -> dict[str, Any]:
    settings = get_settings()
    chunks = split_markdown(
        state["markdown"],
        max_chars=settings.extract_chunk_chars,
        overlap_chars=settings.chunk_overlap_chars,
    )
    payload = [
        {"ordinal": c.ordinal, "char_start": c.char_start, "char_end": c.char_end, "text": c.text}
        for c in chunks
    ]
    async with get_session_factory()() as db:
        doc = await db.get(Document, __import__("uuid").UUID(state["document_id"]))
        if doc is not None:
            await set_document_progress(
                db, doc, status="extracting", step="extracting", done=0, total=len(payload)
            )
            await audit(
                db,
                project_id=state["project_id"],
                feature_id=None,
                graph="document",
                node="split",
                agent="split",
                detail=f"Split into {len(payload)} chunk(s).",
            )
    return {"chunks": payload, "extracted": []}


async def extract_node(state: DocumentState) -> dict[str, Any]:
    running: list[ExtractedFeature] = []
    chunks = state.get("chunks") or []
    for i, chunk in enumerate(chunks):
        new = await extract_features(chunk["text"], running)
        running.extend(new)
        async with get_session_factory()() as db:
            doc = await db.get(Document, __import__("uuid").UUID(state["document_id"]))
            if doc is not None:
                await set_document_progress(
                    db, doc, step="extracting", done=i + 1, total=len(chunks)
                )
                await audit(
                    db,
                    project_id=state["project_id"],
                    feature_id=None,
                    graph="document",
                    node="extract",
                    agent="Feature Extractor",
                    detail=f"Chunk {i + 1}/{len(chunks)}: +{len(new)} feature(s).",
                )
    return {"extracted": [f.model_dump() for f in running]}


async def merge_node(state: DocumentState) -> dict[str, Any]:
    extracted = [ExtractedFeature.model_validate(f) for f in (state.get("extracted") or [])]
    chunks = state.get("chunks") or []
    if len(chunks) > 1 and extracted:
        merged = await merge_features(extracted)
        async with get_session_factory()() as db:
            await audit(
                db,
                project_id=state["project_id"],
                feature_id=None,
                graph="document",
                node="merge",
                agent="Feature Merger",
                detail=f"Merged {len(extracted)} → {len(merged)} feature(s).",
            )
    else:
        merged = extracted
    async with get_session_factory()() as db:
        doc = await db.get(Document, __import__("uuid").UUID(state["document_id"]))
        if doc is not None:
            await set_document_progress(
                db,
                doc,
                status="analysing",
                step="analysing",
                done=0,
                total=len(merged),
            )
    return {"features": [f.model_dump() for f in merged], "analysed": []}


def fan_out_analysts(state: DocumentState) -> list[Send] | str:
    features = state.get("features") or []
    if not features:
        return "verify_citations"
    return [
        Send(
            "analyse",
            {
                "document_id": state["document_id"],
                "project_id": state["project_id"],
                "markdown": state["markdown"],
                "feature": f,
                "analysed": [],
            },
        )
        for f in features
    ]


async def analyse_node(state: DocumentState) -> dict[str, Any]:
    draft = state["feature"]
    async with _sema():
        details = await analyse_feature(
            name=draft["name"],
            summary=draft.get("summary") or "",
            quotes=list(draft.get("source_quotes") or []),
            markdown=state["markdown"],
        )
    async with get_session_factory()() as db:
        await audit(
            db,
            project_id=state["project_id"],
            feature_id=None,
            graph="document",
            node="analyse",
            agent="Feature Analyst",
            detail=f"Analysed “{draft['name']}” — {len(details.questions)} question(s).",
        )
        doc = await db.get(Document, __import__("uuid").UUID(state["document_id"]))
        if doc is not None:
            prev = dict(doc.progress or {})
            done = int(prev.get("done") or 0) + 1
            await set_document_progress(
                db, doc, step="analysing", done=done, total=int(prev.get("total") or done)
            )
    return {"analysed": [{"draft": draft, "details": details}]}


async def verify_citations_node(state: DocumentState) -> dict[str, Any]:
    markdown = state.get("markdown") or ""
    out: list[dict[str, Any]] = []
    for item in state.get("analysed") or []:
        details: FeatureDetails = item["details"]
        if not isinstance(details, FeatureDetails):
            details = FeatureDetails.model_validate(details)
        verified = verify_details(markdown, details)
        quotes = verify_quotes(markdown, list((item["draft"] or {}).get("source_quotes") or []))
        unverified = sum(1 for q in quotes if not q["verified"])
        draft = dict(item["draft"])
        draft["source_quotes"] = [q["quote"] for q in quotes]
        out.append({"draft": draft, "details": verified})
        async with get_session_factory()() as db:
            await audit(
                db,
                project_id=state["project_id"],
                feature_id=None,
                graph="document",
                node="verify_citations",
                agent="verify_citations",
                detail=f"“{draft.get('name')}”: {unverified} unverified quote(s).",
            )
    return {"ready": out}


async def persist_node(state: DocumentState) -> dict[str, Any]:
    async with get_session_factory()() as db:
        await persist_analysed_features(
            db,
            document_id=state["document_id"],
            project_id=state["project_id"],
            markdown=state.get("markdown") or "",
            analysed=list(state.get("ready") or state.get("analysed") or []),
        )
    return {}


def build_document_graph():
    builder = StateGraph(DocumentState)
    builder.add_node("convert", convert_node)
    builder.add_node("split", split_node)
    builder.add_node("extract", extract_node)
    builder.add_node("merge", merge_node)
    builder.add_node("analyse", analyse_node)
    builder.add_node("verify_citations", verify_citations_node)
    builder.add_node("persist", persist_node)
    builder.add_edge(START, "convert")
    builder.add_edge("convert", "split")
    builder.add_edge("split", "extract")
    builder.add_edge("extract", "merge")
    builder.add_conditional_edges("merge", fan_out_analysts)
    builder.add_edge("analyse", "verify_citations")
    builder.add_edge("verify_citations", "persist")
    builder.add_edge("persist", END)
    return builder


async def get_document_graph():
    global _compiled
    if _compiled is None:
        from app.graph.checkpointer import get_checkpointer

        saver = await get_checkpointer()
        _compiled = build_document_graph().compile(checkpointer=saver)
    return _compiled


def reset_document_graph() -> None:
    """Tests: drop the cached compiled graph."""
    global _compiled
    _compiled = None


async def run_document_graph(document_id: str) -> None:
    """Background runner. Any error marks the document failed with problem/cause/fix."""
    try:
        async with get_session_factory()() as db:
            doc = await db.get(Document, __import__("uuid").UUID(document_id))
            if doc is None:
                return
            project_id = doc.project_id
        graph = await get_document_graph()
        await graph.ainvoke(
            {"document_id": document_id, "project_id": project_id, "analysed": []},
            {"configurable": {"thread_id": f"doc:{document_id}"}},
        )
    except VertexNotConfigured as exc:
        err = exc.as_error()
        await fail_document(document_id, err["problem"], err["cause"], err["fix"])
    except UnsupportedDocumentType as exc:
        await fail_document(
            document_id,
            "This file type is not supported.",
            str(exc),
            "Upload a PDF, DOCX or Markdown file.",
        )
    except EmptyDocument as exc:
        await fail_document(
            document_id,
            "The document has no extractable text.",
            str(exc),
            "Upload a text-based PDF, DOCX or Markdown file.",
        )
    except Exception as exc:
        logger.exception("document_graph failed for %s", document_id)
        await fail_document(
            document_id,
            "Feature extraction failed.",
            f"{type(exc).__name__}: {exc}",
            "Re-upload the file. If it keeps failing, check the backend logs.",
        )
