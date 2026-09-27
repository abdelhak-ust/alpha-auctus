"""parse.py — Docling → canonical text + section tree (plans/ingestion.md §5 step 2)."""

from pathlib import Path

import pytest

from app.ingest.parse import (
    Block,
    EmptyDocument,
    UnsupportedDocumentType,
    build_parsed,
    parse_document,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_build_parsed_sections_and_offsets():
    parsed = build_parsed([
        Block("text", "Preamble line."),
        Block("heading", "Spec", level=1, page=1),
        Block("heading", "Auth", level=2, page=1),
        Block("text", "Users sign in with SSO.", page=1),
        Block("heading", "Export", level=2, page=2),
        Block("list", "- CSV export", page=2),
        Block("text", "   "),  # blank blocks are dropped
    ])
    assert [s.path for s in parsed.sections] == [
        [], ["Spec"], ["Spec", "Auth"], ["Spec", "Export"],
    ]
    for section in parsed.sections:
        assert 0 <= section.char_start < section.char_end <= len(parsed.text)
    auth = parsed.sections[2]
    assert parsed.text[auth.char_start:auth.char_end] == "Auth\n\nUsers sign in with SSO."
    assert (parsed.sections[3].page_start, parsed.sections[3].page_end) == (2, 2)
    assert parsed.sections[2].title == "Auth"


def test_parsed_round_trips_through_dict():
    parsed = build_parsed([Block("heading", "A", level=1), Block("text", "body text")])
    assert type(parsed).from_dict(parsed.to_dict()) == parsed


def test_txt_is_split_on_blank_lines():
    parsed = parse_document(_read("notes.txt"), "notes.txt")
    assert parsed.text.startswith("Kickoff meeting notes\n\nAdmins can export")
    assert len(parsed.sections) == 1 and parsed.sections[0].path == []


def test_markdown_via_docling_keeps_heading_tree():
    parsed = parse_document(_read("spec_a.md"), "spec_a.md")
    paths = [s.path[-1] for s in parsed.sections if s.path]
    assert "1.1 Single sign-on" in paths and "2.1 Audit log export" in paths
    sso = next(s for s in parsed.sections if s.path and s.path[-1] == "1.1 Single sign-on")
    assert sso.path[-2] == "1. Authentication"
    assert "Users sign in with SSO through Okta." in parsed.text[sso.char_start:sso.char_end]


def test_docx_via_docling():
    parsed = parse_document(_read("spec.docx"), "spec.docx")
    assert "Users sign in with SSO through Okta." in parsed.text
    assert [s.path[-1] for s in parsed.sections if s.path][-2:] == ["Authentication", "Reporting"]


def test_pdf_items_walk_with_pages(monkeypatch):
    """PDF layout models need a network download, so the converter is faked with a real
    DoclingDocument — this exercises our item walk (titles, headers, furniture, pages)."""
    from docling_core.types.doc import BoundingBox, DocItemLabel, DoclingDocument, ProvenanceItem

    def prov(page: int) -> ProvenanceItem:
        return ProvenanceItem(page_no=page, bbox=BoundingBox(l=0, t=0, r=1, b=1), charspan=(0, 1))

    doc = DoclingDocument(name="two_page")
    doc.add_title("Acme Portal Spec", prov=prov(1))
    doc.add_heading("1. Authentication", level=1, prov=prov(1))
    doc.add_text(DocItemLabel.TEXT, "Users sign in with SSO through Okta.", prov=prov(1))
    doc.add_text(DocItemLabel.PAGE_FOOTER, "Page 1", prov=prov(1))
    doc.add_heading("2. Administration", level=1, prov=prov(2))
    doc.add_text(DocItemLabel.TEXT, "Admins can export the audit log as CSV.", prov=prov(2))

    class FakeConverter:
        def __init__(self, *args, **kwargs):
            pass

        def convert(self, source):
            assert source.name == "two_page.pdf"
            return type("Result", (), {"document": doc})()

    monkeypatch.setattr("docling.document_converter.DocumentConverter", FakeConverter)
    parsed = parse_document(_read("two_page.pdf"), "two_page.pdf")
    assert "Page 1" not in parsed.text
    admin = next(s for s in parsed.sections if s.path and s.path[-1] == "2. Administration")
    assert admin.path == ["Acme Portal Spec", "2. Administration"]
    assert (admin.page_start, admin.page_end) == (2, 2)
    assert parsed.text[admin.char_start:admin.char_end].endswith("audit log as CSV.")


def _docling_models_available() -> bool:
    return (Path.home() / ".cache" / "docling" / "models").exists() or (
        Path.home() / ".cache" / "huggingface" / "hub"
    ).exists()


@pytest.mark.skipif(not _docling_models_available(),
                    reason="Docling PDF layout models not downloaded "
                           "(`poetry run docling-tools models download`)")
def test_pdf_real_docling_two_pages():
    parsed = parse_document(_read("two_page.pdf"), "two_page.pdf")
    assert "Users sign in with SSO through Okta." in parsed.text
    assert max((s.page_end or 0) for s in parsed.sections) == 2


def test_unsupported_type_is_rejected_with_fix():
    with pytest.raises(UnsupportedDocumentType, match="PDF, DOCX, Markdown and TXT"):
        parse_document(b"a,b\n1,2", "data.csv")


def test_empty_document_raises():
    with pytest.raises(EmptyDocument):
        parse_document(b"\n\n   \n", "empty.txt")
