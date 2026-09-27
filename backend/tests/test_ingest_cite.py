"""Quotes: verified when found (exact or whitespace-normalised), else unverified."""

from app.ingest.cite import locate_quote, verify_quote, verify_quotes

TEXT = "Intro.\n\n1.2 Session timeout\n\nSessions expire after 30 minutes of inactivity. Bye."


def test_exact_quote_is_verified_with_offsets():
    quote = "Sessions expire after 30 minutes of inactivity."
    found = locate_quote(TEXT, f'  "{quote}" ')
    assert found is not None
    start, end = found
    assert TEXT[start:end] == quote
    item = verify_quote(TEXT, quote)
    assert item["verified"] is True
    assert item["char_start"] == start


def test_whitespace_normalised_quote_is_verified():
    quote = "Sessions  expire   after 30 minutes of inactivity."
    found = locate_quote(TEXT, quote)
    assert found is not None
    assert "Sessions expire after 30 minutes" in TEXT[found[0] : found[1]]


def test_hallucinated_quote_is_unverified():
    item = verify_quote(TEXT, "Sessions expire after 8 hours of inactivity.")
    assert item["verified"] is False
    assert "char_start" not in item


def test_too_short_is_unverified():
    assert locate_quote(TEXT, "Bye.") is None


def test_verify_quotes_dedupes():
    q = "Sessions expire after 30 minutes of inactivity."
    out = verify_quotes(TEXT, [q, q, "not in the document at all really"])
    assert len(out) == 2
    assert out[0]["verified"] is True
    assert out[1]["verified"] is False
