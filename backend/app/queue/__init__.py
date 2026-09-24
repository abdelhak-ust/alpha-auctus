"""Async background jobs (arq / Redis) — ingestion, classification, validation.

Ingestion (parse/chunk/extract/embed), conflict-check, and requirement
validation are async so slow steps (transcription, large diffs) never block
a request. See architecture.md's ingestion pipeline and P0/P6 in the plan.
"""
