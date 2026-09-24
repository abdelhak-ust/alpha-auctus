"""Ingestion pipeline: connectors -> parse -> chunk -> extract -> embed.

Docs/PDF/CSV, meeting transcripts, images, email, Jira (read-only), Sheets,
GitHub repo scan. Every extracted candidate item is routed through engine/
before it lands, per architecture.md ("ingestion is dedup/conflict-checked,
not a dumb import"). Phase P6 in the plan.
"""
