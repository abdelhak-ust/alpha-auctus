"""Parse (plans/ingestion.md §5 step 2): a file → a structured, section-aware document.

"Structure before text" (§2): PDF, DOCX and Markdown go through **Docling**, which gives us
headings, tables, list items and reading order; plain TXT is split natively on blank lines
(Docling has no plain-text backend, and a .txt has no structure to recover anyway).

The output is one canonical `text` string plus a section tree over it. Every char offset the
rest of the pipeline stores — chunk `char_start`/`char_end`, `source_ref` offsets (contract §5)
— indexes into exactly this string, so it is built deterministically here and nowhere else.
"""

from __future__ import annotations

import io
from dataclasses import asdict, dataclass, field
from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".md", ".markdown", ".txt"}

# Separator placed between consecutive blocks in the canonical text.
BLOCK_SEPARATOR = "\n\n"


class UnsupportedDocumentType(ValueError):
    """The file isn't one of the v1 types (PDF, DOCX, Markdown, TXT — §9)."""

    def __init__(self, filename: str):
        super().__init__(
            f"Can't parse '{filename}': only PDF, DOCX, Markdown and TXT are supported in v1 "
            "(plans/ingestion.md §9). Convert the file to one of those formats and re-upload."
        )


class EmptyDocument(ValueError):
    """Parsing produced no text at all (e.g. a scanned PDF with no text layer)."""

    def __init__(self, filename: str):
        super().__init__(
            f"No text could be extracted from '{filename}'. It may be a scanned image without a "
            "text layer (OCR is off in v1). Upload a text-based PDF, DOCX, Markdown or TXT file."
        )


@dataclass
class Block:
    """One reading-order unit coming out of the parser."""

    kind: str  # "heading" | "text" | "list" | "table"
    text: str
    level: int = 0  # heading depth (1 = top); 0 for non-headings
    page: int | None = None


@dataclass
class Section:
    """A heading-delimited span of the canonical text. `path` is the heading trail."""

    path: list[str]
    char_start: int
    char_end: int
    page_start: int | None = None
    page_end: int | None = None

    @property
    def title(self) -> str:
        return self.path[-1] if self.path else ""


@dataclass
class ParsedDocument:
    text: str
    sections: list[Section] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ParsedDocument:
        return cls(text=data["text"], sections=[Section(**s) for s in data["sections"]])


def build_parsed(blocks: list[Block]) -> ParsedDocument:
    """Join blocks into the canonical text and derive the section tree over it.

    A heading opens a new section (its path = the enclosing headings + itself) that runs
    until the next heading. Text before the first heading forms a section with an empty path.
    """
    parts: list[str] = []
    cursor = 0
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []  # (level, title)
    current: Section | None = None

    for block in blocks:
        text = block.text.strip()
        if not text:
            continue
        if parts:
            parts.append(BLOCK_SEPARATOR)
            cursor += len(BLOCK_SEPARATOR)
        start = cursor
        parts.append(text)
        cursor += len(text)

        if block.kind == "heading":
            level = max(block.level, 1)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, text))
            current = Section(
                path=[t for _, t in stack],
                char_start=start,
                char_end=cursor,
                page_start=block.page,
                page_end=block.page,
            )
            sections.append(current)
            continue

        if current is None:
            current = Section(
                path=[], char_start=start, char_end=cursor, page_start=block.page,
                page_end=block.page,
            )
            sections.append(current)
        current.char_end = cursor
        if block.page is not None:
            current.page_start = current.page_start or block.page
            current.page_end = block.page

    return ParsedDocument(text="".join(parts), sections=sections)


def _txt_blocks(raw: bytes) -> list[Block]:
    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    return [Block(kind="text", text=p) for p in text.split("\n\n") if p.strip()]


def _docling_blocks(raw: bytes, filename: str) -> list[Block]:
    """Run Docling and flatten its document into reading-order blocks."""
    # Imported lazily: Docling is heavy (torch, layout models) and only needed for parsing.
    from docling.datamodel.base_models import DocumentStream, InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling_core.types.doc import DocItemLabel, SectionHeaderItem, TableItem

    pdf_options = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.DOCX, InputFormat.MD],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options)},
    )
    result = converter.convert(DocumentStream(name=filename, stream=io.BytesIO(raw)))
    doc = result.document

    skip = {DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER, DocItemLabel.PICTURE}
    blocks: list[Block] = []
    for item, _depth in doc.iterate_items():
        label = getattr(item, "label", None)
        if label in skip:
            continue
        prov = getattr(item, "prov", None) or []
        page = prov[0].page_no if prov else None
        if label == DocItemLabel.TITLE:
            blocks.append(Block(kind="heading", text=item.text, level=1, page=page))
        elif isinstance(item, SectionHeaderItem):
            # Docling maps a Markdown "#" to TITLE and "##" to a level-1 section header, so a
            # section header sits one level below the title.
            blocks.append(Block(kind="heading", text=item.text, level=item.level + 1, page=page))
        elif isinstance(item, TableItem):
            blocks.append(Block(kind="table", text=item.export_to_markdown(doc=doc), page=page))
        elif label == DocItemLabel.LIST_ITEM:
            blocks.append(Block(kind="list", text=f"- {item.text}", page=page))
        elif getattr(item, "text", None):
            blocks.append(Block(kind="text", text=item.text, page=page))
    return blocks


def parse_document(raw: bytes, filename: str) -> ParsedDocument:
    """Parse a v1 document into canonical text + sections. Synchronous and CPU-heavy —
    callers on the event loop run it in a worker thread (`anyio.to_thread.run_sync`)."""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentType(filename)
    blocks = _txt_blocks(raw) if ext == ".txt" else _docling_blocks(raw, filename)
    parsed = build_parsed(blocks)
    if not parsed.text.strip():
        raise EmptyDocument(filename)
    return parsed
