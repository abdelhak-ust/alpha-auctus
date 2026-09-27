"""The LangGraph `ingest` graph (plans/ingestion.md §5–§6, contract §6).

    START → prepare ─┬─ already done ─────────────────────────────▶ END
                     ├─ stored, hand-off pending ──▶ handoff ──────▶ END
                     └─▶ parse → chunk → retrieve → extract ⟲ (one chunk per step)
                         → consolidate → sweep → match → store → handoff → END

- Deterministic steps (parse, chunk, store, handoff) are plain nodes; LLM steps are extract
  (recall), consolidate (precision), sweep (recall) and match (registry classification).
- `extract` runs one chunk per super-step, so the checkpointer (thread id
  `ingest:<document_id>`) can resume a failed job from the chunk it stopped on.
- `documents.ingestion_status` walks pending → parsed → extracted → consolidated → done.
  Every node writes an `audit_events` row. `store` is one transaction (Postgres rows, then
  Qdrant upserts, then status `consolidated`, then commit), so a re-run never double-writes.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

import anyio
from langgraph.graph import END, START, StateGraph
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import graph as graph_infra
from app import queue
from app.config import get_settings
from app.ingest.chunk import ChunkSpec, chunk_document
from app.ingest.consolidate import consolidate
from app.ingest.extract import extract_chunk, update_rolling_summary
from app.ingest.match import classify_features, retrieve_for_chunks
from app.ingest.parse import ParsedDocument, parse_document
from app.ingest.store import HANDOFF_STATES, apply_outcomes, upsert_vectors, write_chunks
from app.ingest.sweep import reconcile, sweep_chunk
from app.models import Chunk, Document, Feature, FeatureVersion

GRAPH_NAME = "ingest"
NODES = ("prepare", "parse", "chunk", "retrieve", "extract", "consolidate", "sweep", "match",
         "store", "handoff")

SessionFactory = Callable[[], Any]  # () -> async context manager yielding an AsyncSession


class IngestState(TypedDict, total=False):
    document_id: str
    project_id: str
    filename: str
    doc_type: str
    route: str  # prepare's decision: "run" | "handoff" | "skip"
    parsed: dict
    chunks: list[dict]
    registry_candidates: dict[str, list[dict]]  # str(ordinal) -> candidates
    cursor: int
    rolling_summary: list[dict]
    fragments: list[dict]
    unlocated: list[dict]
    features: list[dict]
    sweep_flags: list[dict]
    zero_feature_chunks: list[int]
    classified: list[dict]
    touched: list[dict]
    handed_off: list[str]


def thread_config(document_id: str) -> dict:
    return {"configurable": {"thread_id": f"ingest:{document_id}"}, "recursion_limit": 10_000}


def resolve_blob_path(blob_path: str) -> Path:
    """§11.3: blobs live at `Path(settings.blob_dir) / doc.blob_path`."""
    return Path(get_settings().blob_dir) / blob_path


def build_ingest_graph(
    checkpointer: Any = None, *, session_factory: SessionFactory | None = None
) -> Any:
    """The compiled `ingest` graph. The job passes `await app.graph.get_checkpointer()`;
    tests pass `InMemorySaver()`. `session_factory` defaults to the app's session factory."""
    if session_factory is None:
        from app.db.session import async_session_factory

        session_factory = async_session_factory

    async def audit(session: AsyncSession, state: IngestState, node: str, type_: str,
                    detail: dict, feature_id: uuid.UUID | None = None) -> None:
        await graph_infra.record_audit(
            session, project_id=state["project_id"], feature_id=feature_id, graph=GRAPH_NAME,
            node=node, type=type_, detail={"document_id": state["document_id"], **detail},
        )

    async def set_status(session: AsyncSession, document_id: str, status: str) -> Document:
        doc = await session.get(Document, uuid.UUID(document_id))
        if doc is None:
            raise LookupError(f"document {document_id} not found")
        doc.ingestion_status = status
        doc.error = None
        if status == "done":
            doc.ingested_at = datetime.now(UTC)
        return doc

    def chunks_of(state: IngestState) -> list[ChunkSpec]:
        return [ChunkSpec.from_dict(c) for c in state.get("chunks", [])]

    # ---- nodes ---------------------------------------------------------------------------

    async def prepare(state: IngestState) -> dict:
        document_id = state["document_id"]
        async with session_factory() as session:
            doc = await session.get(Document, uuid.UUID(document_id))
            if doc is None:
                raise LookupError(f"document {document_id} not found")
            status = doc.ingestion_status
            # Chunk rows are written in the same transaction as the outcomes, so their
            # presence means `store` committed — only the hand-off may still be pending.
            stored = status == "consolidated" or (
                await session.scalar(select(Chunk.chunk_id).where(Chunk.doc_id == doc.doc_id)
                                     .limit(1))
            ) is not None
            route = "skip" if status == "done" else ("handoff" if stored else "run")
            update = {
                "project_id": doc.project_id, "filename": doc.filename,
                "doc_type": doc.doc_type, "route": route,
                # Reset per-run state: a finished thread re-invoked keeps its old channels.
                "cursor": 0, "rolling_summary": [], "fragments": [], "unlocated": [],
                "features": [], "sweep_flags": [], "zero_feature_chunks": [],
                "classified": [], "touched": [], "handed_off": [], "registry_candidates": {},
            }
            await audit(session, {**state, **update}, "prepare", "node_completed",
                        {"status": status, "route": route})
            await session.commit()
        return update

    async def parse(state: IngestState) -> dict:
        async with session_factory() as session:
            doc = await session.get(Document, uuid.UUID(state["document_id"]))
            if doc is None or not doc.blob_path:
                raise FileNotFoundError(
                    f"Stored file for document {state['document_id']} is missing"
                )
            path = resolve_blob_path(doc.blob_path)
        raw = await anyio.Path(path).read_bytes()
        parsed = await anyio.to_thread.run_sync(parse_document, raw, state["filename"])
        async with session_factory() as session:
            await set_status(session, state["document_id"], "parsed")
            await audit(session, state, "parse", "node_completed",
                        {"chars": len(parsed.text), "sections": len(parsed.sections)})
            await session.commit()
        return {"parsed": parsed.to_dict()}

    async def chunk(state: IngestState) -> dict:
        chunks = chunk_document(ParsedDocument.from_dict(state["parsed"]),
                                document_id=state["document_id"])
        async with session_factory() as session:
            await audit(session, state, "chunk", "node_completed", {"chunks": len(chunks)})
            await session.commit()
        return {"chunks": [c.to_dict() for c in chunks]}

    async def retrieve(state: IngestState) -> dict:
        """Incremental mode only when the project already has registry features."""
        async with session_factory() as session:
            existing = await session.scalar(
                select(func.count()).select_from(Feature)
                .where(Feature.project_id == state["project_id"])
            )
            candidates: dict[str, list[dict]] = {}
            if existing:
                by_ordinal = await retrieve_for_chunks(state["project_id"], chunks_of(state))
                candidates = {str(k): v for k, v in by_ordinal.items()}
            await audit(session, state, "retrieve", "node_completed",
                        {"mode": "incremental" if existing else "initial",
                         "chunks_with_candidates": sum(1 for v in candidates.values() if v)})
            await session.commit()
        return {"registry_candidates": candidates}

    async def extract(state: IngestState) -> dict:
        chunks = chunks_of(state)
        cursor = state.get("cursor", 0)
        if cursor >= len(chunks):
            return {}
        current = chunks[cursor]
        located, unlocated = await extract_chunk(
            current, document_id=state["document_id"], doc_type=state["doc_type"],
            rolling_summary=state.get("rolling_summary", []),
            registry_candidates=state.get("registry_candidates", {}).get(str(current.ordinal),
                                                                         []),
        )
        async with session_factory() as session:
            await audit(session, state, "extract", "node_completed",
                        {"chunk_ordinal": current.ordinal, "fragments": len(located),
                         "unlocated": len(unlocated)})
            await session.commit()
        return {
            "cursor": cursor + 1,
            "fragments": state.get("fragments", []) + located,
            "unlocated": state.get("unlocated", []) + unlocated,
            "rolling_summary": update_rolling_summary(state.get("rolling_summary", []),
                                                      located),
        }

    async def consolidate_node(state: IngestState) -> dict:
        async with session_factory() as session:
            await set_status(session, state["document_id"], "extracted")
            await session.commit()
        features = await consolidate(state.get("fragments", []))
        async with session_factory() as session:
            await audit(session, state, "consolidate", "node_completed",
                        {"fragments": len(state.get("fragments", [])),
                         "features": len(features),
                         "with_contradictions": sum(1 for f in features
                                                    if f["contradictions"])})
            await session.commit()
        return {"features": features}

    async def sweep(state: IngestState) -> dict:
        chunks = chunks_of(state)
        sweeps = {c.ordinal: await sweep_chunk(c) for c in chunks}
        flags, zero = reconcile(
            chunks=chunks, sweeps=sweeps, features=state.get("features", []),
            fragments=state.get("fragments", []), unlocated=state.get("unlocated", []),
            document_id=state["document_id"], doc_type=state["doc_type"],
        )
        # Contradictions consolidation couldn't pair into v1/v2 — never silently dropped.
        flags = [flag for f in state.get("features", [])
                 for flag in f.get("contradiction_flags", [])] + flags
        async with session_factory() as session:
            await audit(session, state, "sweep", "node_completed",
                        {"flags": len(flags), "zero_feature_chunks": zero})
            await session.commit()
        return {"sweep_flags": flags, "zero_feature_chunks": zero}

    async def match(state: IngestState) -> dict:
        async with session_factory() as session:
            classified = await classify_features(session, state["project_id"],
                                                 state.get("features", []))
            outcomes: dict[str, int] = {}
            for item in classified:
                outcomes[item["outcome"]] = outcomes.get(item["outcome"], 0) + 1
            await audit(session, state, "match", "node_completed", {"outcomes": outcomes})
            await session.commit()
        return {"classified": classified}

    async def store(state: IngestState) -> dict:
        chunks = chunks_of(state)
        async with session_factory() as session:
            await write_chunks(session, project_id=state["project_id"],
                               document_id=state["document_id"], chunks=chunks)
            touched = await apply_outcomes(
                session, project_id=state["project_id"], document_id=state["document_id"],
                classified=state.get("classified", []),
                sweep_flags=state.get("sweep_flags", []),
            )
            await upsert_vectors(session, project_id=state["project_id"],
                                 document_id=state["document_id"], chunks=chunks,
                                 touched=touched)
            await set_status(session, state["document_id"], "consolidated")
            await audit(session, state, "store", "node_completed",
                        {"touched": len(touched), "chunks": len(chunks),
                         "sweep_flags": len(state.get("sweep_flags", []))})
            await session.commit()
        return {"touched": [
            {"feature_id": str(t["feature_id"]), "outcome": t["outcome"],
             "lifecycle_state": t["lifecycle_state"]} for t in touched
        ]}

    async def handoff(state: IngestState) -> dict:
        """contract §3: every feature this document left `consolidated` or `stale` gets a
        readiness run; `conflicted` ones wait for a human. Recomputed from Postgres so a
        re-run after a crash between store and hand-off still hands off."""
        created_from = f"ingest:{state['document_id']}"
        async with session_factory() as session:
            rows = await session.execute(
                select(Feature.feature_id, FeatureVersion.version_no)
                .join(FeatureVersion, FeatureVersion.version_id == Feature.current_version_id)
                .where(Feature.project_id == state["project_id"],
                       FeatureVersion.created_from == created_from,
                       Feature.lifecycle_state.in_(HANDOFF_STATES))
            )
            handoffs = [(str(fid), version_no) for fid, version_no in rows.all()]
            feature_ids = [fid for fid, _ in handoffs]
            for fid, version_no in handoffs:
                # arq de-duplicates on _job_id: a repeated hand-off for the same version
                # (e.g. a crash between enqueue and commit) doesn't queue a second run.
                await queue.enqueue("readiness_run", feature_id=fid,
                                    project_id=state["project_id"],
                                    _job_id=f"readiness_run:{fid}:v{version_no}")
            await set_status(session, state["document_id"], "done")
            await audit(session, state, "handoff", "node_completed",
                        {"readiness_enqueued": feature_ids})
            await session.commit()
        return {"handed_off": feature_ids}

    # ---- edges ---------------------------------------------------------------------------

    def after_prepare(state: IngestState) -> str:
        return {"skip": END, "handoff": "handoff"}.get(state.get("route", "run"), "parse")

    def after_extract(state: IngestState) -> str:
        return "extract" if state.get("cursor", 0) < len(state.get("chunks", [])) \
            else "consolidate"

    builder = StateGraph(IngestState)
    builder.add_node("prepare", prepare)
    builder.add_node("parse", parse)
    builder.add_node("chunk", chunk)
    builder.add_node("retrieve", retrieve)
    builder.add_node("extract", extract)
    builder.add_node("consolidate", consolidate_node)
    builder.add_node("sweep", sweep)
    builder.add_node("match", match)
    builder.add_node("store", store)
    builder.add_node("handoff", handoff)

    builder.add_edge(START, "prepare")
    builder.add_conditional_edges("prepare", after_prepare, ["parse", "handoff", END])
    builder.add_edge("parse", "chunk")
    builder.add_edge("chunk", "retrieve")
    builder.add_edge("retrieve", "extract")
    builder.add_conditional_edges("extract", after_extract, ["extract", "consolidate"])
    builder.add_edge("consolidate", "sweep")
    builder.add_edge("sweep", "match")
    builder.add_edge("match", "store")
    builder.add_edge("store", "handoff")
    builder.add_edge("handoff", END)
    return builder.compile(checkpointer=checkpointer)
