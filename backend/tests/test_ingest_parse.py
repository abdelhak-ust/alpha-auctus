"""parse.py's dispatch logic + the PDF/text paths that don't need a live Vertex AI call.
Image parsing (needs a real model call) is covered once GCP_PROJECT_ID is configured — see
plans/ingestion.md's PDF/image verification bullet."""

import io

import pytest
from pypdf import PdfWriter

from app.ingest.parse import UnsupportedSourceType, parse_to_text


async def test_text_mime_types_decode_directly():
    for mime in ("text/plain", "text/markdown", "text/csv", ""):
        result = await parse_to_text(b"Some plain content here.", mime, "note.txt")
        assert result == "Some plain content here."


async def test_pdf_parses_without_crashing_on_a_real_minimal_pdf():
    buf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(buf)

    result = await parse_to_text(buf.getvalue(), "application/pdf", "blank.pdf")

    assert isinstance(result, str)  # a blank page has no text — just must not crash


async def test_unsupported_mime_type_raises_with_actionable_message():
    with pytest.raises(UnsupportedSourceType, match="video/mp4"):
        await parse_to_text(b"...", "video/mp4", "call.mp4")
