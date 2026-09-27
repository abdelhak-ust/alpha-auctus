"""Markdown passthrough and type guards for convert.py."""

import pytest

from app.ingest.convert import EmptyDocument, UnsupportedDocumentType, convert_to_markdown


def test_markdown_passthrough():
    raw = b"# Title\n\nHello world.\n"
    assert convert_to_markdown(raw, "spec.md") == "# Title\n\nHello world.\n"


def test_empty_markdown_raises():
    with pytest.raises(EmptyDocument):
        convert_to_markdown(b"   \n", "empty.md")


def test_unsupported_type_raises():
    with pytest.raises(UnsupportedDocumentType):
        convert_to_markdown(b"hello", "notes.txt")
