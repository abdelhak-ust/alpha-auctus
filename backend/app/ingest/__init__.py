"""Ingestion pipeline — stage 1 of the feature pipeline (plans/ingestion.md, phase P6).

Documents (PDF, DOCX, Markdown, TXT) → a deduplicated, versioned, cited Feature Registry, via
the LangGraph `ingest` graph (graph.py):

    parse.py        Docling → canonical text + section tree
    chunk.py        section-boundary chunks with overlap and exact char offsets
    extract.py      per-chunk extraction with rolling state (+ registry candidates)
    consolidate.py  fragment groups → one feature each (find ≠ merge)
    sweep.py        high-recall completeness sweep → sweep_flag review items
    match.py        registry retrieval + NEW / UPDATE / CONFLICT / DUPLICATE classification
    store.py        Postgres rows + Qdrant upserts, one transaction
    cite.py         quote → verified `source_ref` (cite or stay silent)
    prompts.py      LLM prompt text;  llm.py  the `app.ai` seam
    jobs.py         arq job `ingest_document(ctx, document_id)`

`ingest_document` is resolved lazily so importing a leaf module (e.g. parse) doesn't pull in
LangGraph, Qdrant and the AI adapter.
"""

from typing import Any

__all__ = ["ingest_document"]


def __getattr__(name: str) -> Any:
    if name == "ingest_document":
        from app.ingest.jobs import ingest_document

        return ingest_document
    raise AttributeError(name)
