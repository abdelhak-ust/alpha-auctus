"""Convert an uploaded file to Markdown (plans/mvp-v0.md). Deterministic — no LLM.

.md is passed through. .pdf / .docx go through Docling's `export_to_markdown()`.
Callers on the event loop run this in a worker thread (`anyio.to_thread.run_sync`).
"""

from __future__ import annotations

import io
from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".md", ".markdown"}


class UnsupportedDocumentType(ValueError):
    """The file isn't one of the MVP types (PDF, DOCX, Markdown)."""

    def __init__(self, filename: str):
        super().__init__(
            f"Can't parse '{filename}': only PDF, DOCX and Markdown are supported. "
            "Convert the file to one of those formats and re-upload."
        )


class EmptyDocument(ValueError):
    """Conversion produced no text (e.g. a scanned PDF with no text layer)."""

    def __init__(self, filename: str):
        super().__init__(
            f"No text could be extracted from '{filename}'. It may be a scanned image without a "
            "text layer. Upload a text-based PDF, DOCX or Markdown file."
        )


def _docling_markdown(raw: bytes, filename: str) -> str:
    """Run Docling and export the document as Markdown."""
    from docling.datamodel.base_models import DocumentStream, InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pdf_options = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.DOCX, InputFormat.MD],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options)},
    )
    result = converter.convert(DocumentStream(name=filename, stream=io.BytesIO(raw)))
    return result.document.export_to_markdown() or ""


def convert_to_markdown(raw: bytes, filename: str) -> str:
    """File bytes → Markdown string. Synchronous and CPU-heavy."""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentType(filename)
    if ext in {".md", ".markdown"}:
        text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    else:
        text = _docling_markdown(raw, filename)
    if not text.strip():
        raise EmptyDocument(filename)
    return text
