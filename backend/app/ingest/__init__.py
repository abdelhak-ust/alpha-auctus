"""Deterministic document handling for MVP v0 (no LLM).

    convert.py   md passthrough; pdf/docx → Docling export_to_markdown()
    split.py     heading-aware chunks with overlap and exact char offsets
    cite.py      locate quotes (exact, then whitespace-normalised)
"""
