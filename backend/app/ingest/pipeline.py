"""Orchestrates parse -> chunk -> extract -> embed -> persist -> provisional-verdict for one
uploaded source, and the approve/dismiss half of the review queue.

**Scope decision (refined during implementation, differs from the original plan sketch):**
plans/ingestion.md's "Placement" originally sketched Node as a dumb proxy relaying Python's
response. That's incomplete: Node's JSON store (client/server.ts) is still what the frontend
actually reads via `/api/state` — nothing has migrated `items`/`decisions`/`ingestQueue` to
Postgres yet (no Project/Item/Decision models exist in this backend). A dumb proxy would leave
`/api/state` never seeing the new candidates. So instead: this runs **synchronously within the
request** (matching today's contract exactly — no BackgroundTasks/queue needed for this pass,
consistent with the earlier scoped decision to defer arq/Redis wiring) and returns the full
`IngestItemOut` list in the response; Node merges that list into its own `ingestQueue` after
relaying it. Postgres (Source/Chunk+embeddings/DecisionRecord/IngestCandidate) is the durable,
cited memory; Node's JSON store stays the thing the current frontend renders, kept in sync.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import embed_texts
from app.ingest.chunk import chunk_text
from app.ingest.extract import extract_from_chunk
from app.ingest.parse import parse_to_text
from app.ingest.verdict import provisional_verdict
from app.models import Chunk, DecisionRecord, IngestCandidate, Source
from app.schemas.ingestion import IngestItemOut


async def ingest_source(
    session: AsyncSession,
    *,
    project_id: str,
    filename: str,
    content: bytes,
    mime_type: str,
) -> tuple[Source, list[IngestItemOut]]:
    """Parse, chunk, extract, embed, and persist one source; return the resulting candidates
    already shaped as `IngestItemOut` (the response contract Node relays to the frontend)."""
    source = Source(
        project_id=project_id,
        type="upload",
        name=filename,
        mime_type=mime_type,
        status="syncing",
    )
    session.add(source)
    await session.flush()  # assign source.id

    text = await parse_to_text(content, mime_type, filename)
    spans = chunk_text(text)

    chunk_rows: list[Chunk] = [
        Chunk(
            source_id=source.id,
            seq=seq,
            text=span.text,
            char_start=span.char_start,
            char_end=span.char_end,
        )
        for seq, span in enumerate(spans)
    ]
    if chunk_rows:
        chunk_embeddings = await embed_texts([c.text for c in chunk_rows])
        for row, embedding in zip(chunk_rows, chunk_embeddings, strict=True):
            row.embedding = embedding
            session.add(row)
        await session.flush()  # assign chunk ids before extraction references them

    candidates_out: list[IngestItemOut] = []
    for chunk_row in chunk_rows:
        result = await extract_from_chunk(chunk_row.text)

        for extracted in result.items:
            verdict = await provisional_verdict(extracted.title, extracted.description, project_id)
            candidate = IngestCandidate(
                project_id=project_id,
                title=extracted.title,
                description=extracted.description,
                entity_tags=extracted.entity_tags,
                priority=extracted.priority,
                source_id=source.id,
                chunk_id=chunk_row.id,
                snippet=extracted.snippet,
                status="pending",
                verdict=verdict.model_dump(by_alias=True),
            )
            session.add(candidate)
            await session.flush()  # assign candidate.id
            [embedding] = await embed_texts([f"{extracted.title}\n{extracted.description}"])
            candidate.embedding = embedding

            candidates_out.append(
                IngestItemOut(
                    id=candidate.id,
                    title=candidate.title,
                    description=candidate.description,
                    area=(candidate.entity_tags[0] if candidate.entity_tags else "general"),
                    priority=candidate.priority,
                    source_id=source.id,
                    source_snippet=candidate.snippet,
                    verdict=verdict,
                )
            )

        for extracted_decision in result.decisions:
            [embedding] = await embed_texts([extracted_decision.statement])
            session.add(
                DecisionRecord(
                    project_id=project_id,
                    statement=extracted_decision.statement,
                    polarity=extracted_decision.polarity,
                    affected_entities=extracted_decision.affected_entities,
                    source_id=source.id,
                    chunk_id=chunk_row.id,
                    snippet=extracted_decision.snippet,
                    status="proposed",
                    embedding=embedding,
                )
            )

    source.status = "synced"
    await session.commit()

    return source, candidates_out


async def resolve_candidate(
    session: AsyncSession, *, candidate_id: str, action: str
) -> IngestCandidate | None:
    """Mark a candidate approved/dismissed. Returns the candidate (for Node to build an Item
    from, on approve) or None if it wasn't found."""
    candidate = await session.get(IngestCandidate, candidate_id)
    if candidate is None:
        return None
    candidate.status = "approved" if action == "approve" else "dismissed"
    await session.commit()
    return candidate
