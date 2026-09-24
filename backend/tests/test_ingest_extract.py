"""extract.py's hallucination guard: any candidate whose snippet isn't a literal substring of
its source chunk must be dropped, not kept or corrected (plans/ingestion.md step 4 — a
concrete enforcement of "cite or stay silent"). Uses a fake Claude client so this runs without
a live Vertex AI call.
"""

from types import SimpleNamespace

import app.ingest.extract as extract_module
from app.ingest.extract import extract_from_chunk


class _FakeMessages:
    def __init__(self, tool_input: dict):
        self._tool_input = tool_input

    async def create(self, **_kwargs):
        block = SimpleNamespace(type="tool_use", input=self._tool_input)
        return SimpleNamespace(content=[block])


class _FakeClient:
    def __init__(self, tool_input: dict):
        self.messages = _FakeMessages(tool_input)


def _patch_client(monkeypatch, tool_input: dict):
    monkeypatch.setattr(extract_module, "get_client", lambda: _FakeClient(tool_input))


CHUNK = "We will use the customer's IdP for SSO instead of building our own credential store."


async def test_valid_verbatim_snippet_is_kept(monkeypatch):
    _patch_client(
        monkeypatch,
        {
            "items": [],
            "decisions": [
                {
                    "statement": "We will not build our own SSO",
                    "polarity": "negate",
                    "affected_entities": ["auth"],
                    "snippet": CHUNK,
                }
            ],
        },
    )

    result = await extract_from_chunk(CHUNK)

    assert len(result.decisions) == 1
    assert result.decisions[0].statement == "We will not build our own SSO"


async def test_hallucinated_snippet_is_dropped_not_kept(monkeypatch):
    """The exact failure mode the guard exists for: a plausible-sounding but fabricated
    quote that doesn't actually appear in the source."""
    _patch_client(
        monkeypatch,
        {
            "items": [
                {
                    "title": "Add SSO",
                    "description": "Build SSO support",
                    "snippet": "This sentence was never in the source chunk at all.",
                }
            ],
            "decisions": [],
        },
    )

    result = await extract_from_chunk(CHUNK)

    assert result.items == []  # dropped, not kept, not "fixed"


async def test_missing_title_or_snippet_is_dropped(monkeypatch):
    _patch_client(monkeypatch, {"items": [{"title": "", "snippet": CHUNK}]})

    result = await extract_from_chunk(CHUNK)

    assert result.items == []


async def test_empty_chunk_short_circuits_without_calling_claude(monkeypatch):
    called = False

    def _fail_if_called():
        nonlocal called
        called = True
        raise AssertionError("get_client() should not be called for empty/whitespace input")

    monkeypatch.setattr(extract_module, "get_client", _fail_if_called)

    result = await extract_from_chunk("   \n  ")

    assert not called
    assert result.items == []
    assert result.decisions == []
