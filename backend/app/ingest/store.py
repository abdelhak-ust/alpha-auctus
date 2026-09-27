"""Embed & store (plans/ingestion.md §5 step 7 / §6 steps 5 + 7, amendments §11.3).

Applies each classified feature's outcome to Postgres inside the caller's transaction:

- NEW       → `features` row + `feature_versions` v1 → `consolidated`. When consolidation
              listed an in-document contradiction: v1 = first statement (current), v2 = the
              contradicting one (incoming, not current), feature `conflicted`, conflict item.
- UPDATE    → new `feature_versions` row (merged description, appended source_refs) becomes
              current; a feature already past `consolidated` goes `stale` (contract §3).
- CONFLICT  → the incoming version is a real `feature_versions` row (version_no = max+1), NOT
              made current and NOT upserted to Qdrant; feature → `conflicted`;
              `review_items(kind=conflict)`. Never auto-resolved (§7).
- DUPLICATE → no new version; the new source_refs are appended to the current version's
              provenance, plus a `provenance_append` audit row.
- REVIEW    → a low-confidence match: nothing applied; a `sweep_flag` instead.

Review payloads are exactly the §11.3 shapes. Qdrant: changed feature points (current
descriptions only) and this document's chunk points are embedded (RETRIEVAL_DOCUMENT, batched)
and upserted by id. Ids are deterministic (feature id = uuid5 of document + consolidation
group; chunk id = uuid5 of document + ordinal), so a re-run overwrites instead of duplicating.

No Docling import here (directly or transitively) — the API imports `reindex_feature`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import graph as graph_infra
from app import vector
from app.ingest.chunk import ChunkSpec
from app.ingest.cite import names_match
from app.ingest.consolidate import dedupe_refs
from app.ingest.llm import embed
from app.models import Chunk, Feature, FeatureRelation, FeatureVersion, ReviewItem

GRAPH = "ingest"
NODE = "store"
_FEATURE_NAMESPACE = uuid.UUID("0f1c7d0e-8a51-4b8e-9f0a-3c2d5e6f7a81")

# Lifecycle states that count as "already past consolidated" (contract §3): an UPDATE there
# sets `stale` so the feature re-enters the readiness graph.
PAST_CONSOLIDATED = {
    "classified", "assessing", "awaiting_answers", "answered", "dev_ready", "overridden",
    "in_breakdown", "needs_review", "broken_down", "stale",
}
HANDOFF_STATES = ("consolidated", "stale")


def feature_id_for(document_id: str, key: str) -> uuid.UUID:
    return uuid.uuid5(_FEATURE_NAMESPACE, f"{document_id}:{key}")


def feature_payload(feature: Feature, version: FeatureVersion | None) -> dict:
    """§11.3 feature point payload."""
    return {
        "project_id": feature.project_id,
        "feature_id": str(feature.feature_id),
        "name": feature.name,
        "lifecycle_state": feature.lifecycle_state,
        "source_refs": list(version.source_refs) if version else [],
        "last_updated": datetime.now(UTC).isoformat(),
    }


def _embed_text(name: str, description: str) -> str:
    return f"{name}\n{description}"


async def reindex_feature(session: AsyncSession, feature_id: uuid.UUID | str) -> None:
    """Re-embed a feature's *current* description (RETRIEVAL_DOCUMENT) and upsert its point.

    Called by the review-queue resolve route after a resolution changes the current version
    or creates a feature. Raises `VertexNotConfigured` / vector errors to the caller."""
    fid = feature_id if isinstance(feature_id, uuid.UUID) else uuid.UUID(str(feature_id))
    feature = await session.get(Feature, fid)
    if feature is None or feature.current_version_id is None:
        return
    version = await session.get(FeatureVersion, feature.current_version_id)
    if version is None:
        return
    [vec] = await embed([_embed_text(feature.name, version.description)], "RETRIEVAL_DOCUMENT")
    await vector.upsert_features(
        [{"id": str(fid), "vector": vec, "payload": feature_payload(feature, version)}]
    )


async def write_chunks(
    session: AsyncSession, *, project_id: str, document_id: str, chunks: list[ChunkSpec]
) -> None:
    """Replace this document's chunk rows (idempotent re-run)."""
    doc_uuid = uuid.UUID(document_id)
    await session.execute(delete(Chunk).where(Chunk.doc_id == doc_uuid))
    for c in chunks:
        session.add(Chunk(
            chunk_id=uuid.UUID(c.chunk_id), doc_id=doc_uuid, project_id=project_id,
            ordinal=c.ordinal, section_path=" > ".join(c.section_path),
            page_start=c.page_start, page_end=c.page_end,
            char_start=c.char_start, char_end=c.char_end, text=c.text,
        ))
    await session.flush()


async def _next_version_no(session: AsyncSession, feature_id: uuid.UUID) -> int:
    current = await session.scalar(
        select(func.max(FeatureVersion.version_no)).where(FeatureVersion.feature_id == feature_id)
    )
    return (current or 0) + 1


async def _audit(session: AsyncSession, project_id: str, feature_id: uuid.UUID | None,
                 type_: str, detail: dict) -> None:
    await graph_infra.record_audit(
        session, project_id=project_id, feature_id=feature_id, graph=GRAPH, node=NODE,
        type=type_, detail=detail,
    )


def _conflict_payload(*, feature_name: str, reason: str, confidence: float,
                      current: FeatureVersion | None, incoming: FeatureVersion) -> dict:
    """§11.3 conflict payload — the API builds the ranked candidates from the two versions."""
    return {
        "feature_name": feature_name,
        "reason": reason,
        "confidence": float(confidence),
        "current_version_id": str(current.version_id) if current else None,
        "incoming_version_id": str(incoming.version_id),
    }


async def _add_version(session: AsyncSession, *, feature_id: uuid.UUID, version_no: int,
                       description: str, source_refs: list[dict],
                       created_from: str) -> FeatureVersion:
    version = FeatureVersion(feature_id=feature_id, version_no=version_no,
                             description=description, source_refs=source_refs,
                             created_from=created_from)
    session.add(version)
    await session.flush()
    return version


async def apply_outcomes(
    session: AsyncSession,
    *,
    project_id: str,
    document_id: str,
    classified: list[dict],
    sweep_flags: list[dict],
) -> list[dict]:
    """Write every outcome. Returns every feature this document touched:
    [{feature_id, outcome, lifecycle_state, reembed, chunk_ids}] — `reembed` marks the points
    that must be refreshed, `chunk_ids` the chunks of this document it is cited from."""
    created_from = f"ingest:{document_id}"
    doc_uuid = uuid.UUID(document_id)
    touched: list[dict] = []
    name_to_id: dict[str, uuid.UUID] = {}

    def touch(fid: uuid.UUID, outcome: str, state: str, reembed: bool,
              cited: list[dict]) -> None:
        touched.append({"feature_id": fid, "outcome": outcome, "lifecycle_state": state,
                        "reembed": reembed,
                        "chunk_ids": sorted({r["chunk_id"] for r in cited
                                             if r.get("doc_id") == document_id})})

    for item in classified:
        outcome = item["outcome"]
        refs = item["source_refs"]

        if outcome == "review":
            flag = {
                "feature_name": item["name"],
                "description": item["description"],
                "reason": "low_confidence_match",
                "confidence": float(item.get("match_confidence", 0.0)),
                "source_ref": refs[0],
            }
            session.add(ReviewItem(project_id=project_id, kind="sweep_flag", feature_id=None,
                                   document_id=doc_uuid, payload=flag))
            await _audit(session, project_id, None, "sweep_flag",
                         {"reason": flag["reason"], "feature_name": item["name"],
                          "candidates": item.get("candidates", [])})
            continue

        if outcome == "new":
            fid = feature_id_for(document_id, item["key"])
            name_to_id[item["name"]] = fid
            if await session.get(Feature, fid) is not None:
                continue  # re-run after a partial write: already stored
            incoming = item.get("incoming")
            state = "conflicted" if incoming else "consolidated"
            feature = Feature(feature_id=fid, project_id=project_id, name=item["name"],
                              lifecycle_state=state)
            session.add(feature)
            await session.flush()
            v1 = await _add_version(session, feature_id=fid, version_no=1,
                                    description=item["description"], source_refs=refs,
                                    created_from=created_from)
            feature.current_version_id = v1.version_id
            if incoming:
                v2 = await _add_version(session, feature_id=fid, version_no=2,
                                        description=incoming["description"],
                                        source_refs=incoming["source_refs"],
                                        created_from=created_from)
                session.add(ReviewItem(
                    project_id=project_id, kind="conflict", feature_id=fid, document_id=doc_uuid,
                    payload=_conflict_payload(
                        feature_name=item["name"], reason="in_document_contradiction",
                        confidence=item.get("confidence", 0.0), current=v1, incoming=v2),
                ))
            touch(fid, "new", state, True,
                  refs + (incoming["source_refs"] if incoming else []))
            await _audit(session, project_id, fid, "feature_created",
                         {"state": state, "version_no": 1, "source_refs": len(refs)})
            continue

        fid = uuid.UUID(item["matched_feature_id"])
        feature = await session.get(Feature, fid)
        if feature is None:
            continue
        name_to_id[item["name"]] = fid
        current = (await session.get(FeatureVersion, feature.current_version_id)
                   if feature.current_version_id else None)

        if outcome in ("update", "duplicate") and item.get("incoming"):
            outcome = "conflict"  # the incoming text contradicts itself — a human decides
        # A feature already blocked on a human is never merged into — the incoming text
        # becomes another proposed version under review instead.
        if outcome == "update" and feature.lifecycle_state == "conflicted":
            outcome = "conflict"

        if outcome == "duplicate":
            if current is not None:
                current.source_refs = dedupe_refs(list(current.source_refs) + refs)
            touch(fid, "duplicate", feature.lifecycle_state, False, refs)
            await _audit(session, project_id, fid, "provenance_append",
                         {"added_source_refs": len(refs), "document_id": document_id})
            continue

        version_no = await _next_version_no(session, fid)
        if outcome == "update":
            merged_refs = dedupe_refs((list(current.source_refs) if current else []) + refs)
            version = await _add_version(session, feature_id=fid, version_no=version_no,
                                         description=item["merged_description"],
                                         source_refs=merged_refs, created_from=created_from)
            previous_state = feature.lifecycle_state
            feature.current_version_id = version.version_id
            feature.lifecycle_state = (
                "stale" if previous_state in PAST_CONSOLIDATED else "consolidated"
            )
            touch(fid, "update", feature.lifecycle_state, True, refs)
            await _audit(session, project_id, fid, "feature_updated",
                         {"version_no": version_no, "from_state": previous_state,
                          "to_state": feature.lifecycle_state})
            continue

        # CONFLICT: keep both versions, block the feature, queue a human decision.
        incoming = await _add_version(session, feature_id=fid, version_no=version_no,
                                      description=item["description"], source_refs=refs,
                                      created_from=created_from)
        previous_state = feature.lifecycle_state
        feature.lifecycle_state = "conflicted"
        session.add(ReviewItem(
            project_id=project_id, kind="conflict", feature_id=fid, document_id=doc_uuid,
            payload=_conflict_payload(
                feature_name=feature.name, reason="registry_conflict",
                confidence=item.get("match_confidence", 0.0), current=current,
                incoming=incoming),
        ))
        # Point refreshed only for its lifecycle_state; the vector stays the current version.
        touch(fid, "conflict", "conflicted", True, refs)
        await _audit(session, project_id, fid, "conflict_flagged",
                     {"incoming_version_no": version_no, "from_state": previous_state,
                      "candidates": item.get("candidates", []),
                      "rationale": item.get("rationale", "")})

    for flag in sweep_flags:
        session.add(ReviewItem(project_id=project_id, kind="sweep_flag", feature_id=None,
                               document_id=doc_uuid, payload=flag))
        await _audit(session, project_id, None, "sweep_flag",
                     {"reason": flag["reason"], "feature_name": flag["feature_name"]})

    await _write_relations(session, project_id, classified, name_to_id)
    await session.flush()
    return touched


async def _write_relations(session: AsyncSession, project_id: str, classified: list[dict],
                           name_to_id: dict[str, uuid.UUID]) -> None:
    if not any(item.get("relations") for item in classified):
        return
    registry = (await session.execute(
        select(Feature.feature_id, Feature.name).where(Feature.project_id == project_id)
    )).all()
    for item in classified:
        source = name_to_id.get(item["name"])
        if source is None:
            continue
        for rel in item.get("relations") or []:
            target = next((fid for n, fid in name_to_id.items()
                           if names_match(n, rel["target_feature_name"])), None)
            if target is None:
                target = next((fid for fid, n in registry
                               if names_match(n, rel["target_feature_name"])), None)
            if target is None or target == source:
                continue
            await session.merge(FeatureRelation(feature_id_a=source, feature_id_b=target,
                                                relation_type=rel["relation_type"]))


async def upsert_vectors(
    session: AsyncSession, *, project_id: str, document_id: str, chunks: list[ChunkSpec],
    touched: list[dict],
) -> None:
    """Embed (RETRIEVAL_DOCUMENT, batched) and upsert only the changed feature points — always
    from each feature's *current* version — plus this document's chunk points."""
    changed: list[tuple[Feature, FeatureVersion | None]] = []
    for t in touched:
        if not t["reembed"]:
            continue
        feature = await session.get(Feature, t["feature_id"])
        if feature is None:
            continue
        version = (await session.get(FeatureVersion, feature.current_version_id)
                   if feature.current_version_id else None)
        changed.append((feature, version))

    if changed:
        vecs = await embed(
            [_embed_text(f.name, v.description if v else "") for f, v in changed],
            "RETRIEVAL_DOCUMENT",
        )
        await vector.upsert_features([
            {"id": str(f.feature_id), "vector": vec, "payload": feature_payload(f, v)}
            for (f, v), vec in zip(changed, vecs, strict=True)
        ])

    if chunks:
        feature_ids_by_chunk: dict[str, set[str]] = {}
        for t in touched:
            for chunk_id in t["chunk_ids"]:
                feature_ids_by_chunk.setdefault(chunk_id, set()).add(str(t["feature_id"]))
        vecs = await embed([c.text for c in chunks], "RETRIEVAL_DOCUMENT")
        await vector.upsert_chunks([
            {"id": c.chunk_id, "vector": vec,
             "payload": {"project_id": project_id, "doc_id": document_id,
                         "chunk_id": c.chunk_id,
                         "feature_ids": sorted(feature_ids_by_chunk.get(c.chunk_id, set())),
                         "section": c.section, "char_start": c.char_start,
                         "char_end": c.char_end, "text": c.text}}
            for c, vec in zip(chunks, vecs, strict=True)
        ])
