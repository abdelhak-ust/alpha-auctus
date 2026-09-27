"""The Gemini/Vertex adapter (app.ai): graceful failure when unconfigured, structured output
validation, batched embeddings with per-text fallback, and 429/5xx retry. No network — the
genai client is replaced by a fake via `get_client`.
"""

from types import SimpleNamespace

import pytest
from google.genai import errors
from pydantic import BaseModel

from app import ai
from app.ai import vertex
from app.config import get_settings


class Answer(BaseModel):
    name: str
    score: float


@pytest.fixture
def unconfigured(monkeypatch):
    """Force GCP_PROJECT_ID empty regardless of the local .env."""
    monkeypatch.setenv("GCP_PROJECT_ID", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("EMBEDDING_DIM", "4")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


class FakeModels:
    def __init__(self, *, generate=None, embed=None):
        self._generate = generate or []
        self._embed = embed
        self.generate_calls: list[dict] = []
        self.embed_calls: list[dict] = []

    async def generate_content(self, **kwargs):
        self.generate_calls.append(kwargs)
        item = self._generate.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def embed_content(self, **kwargs):
        self.embed_calls.append(kwargs)
        return self._embed(kwargs)


def _install(monkeypatch, models: FakeModels):
    fake = SimpleNamespace(aio=SimpleNamespace(models=models))
    monkeypatch.setattr(vertex, "get_client", lambda: fake)
    monkeypatch.setattr(vertex.asyncio, "sleep", _no_sleep)


async def _no_sleep(_s):
    return None


def _api_error(code: int) -> errors.APIError:
    cls = errors.ClientError if code < 500 else errors.ServerError
    return cls(code, {"error": {"code": code, "message": "boom", "status": "X"}})


def _embedding_response(n: int, dim: int = 4):
    return SimpleNamespace(
        embeddings=[SimpleNamespace(values=[float(i)] * dim) for i in range(n)]
    )


# --- unconfigured -------------------------------------------------------------------------


def test_get_client_without_project_raises_actionable_error(unconfigured):
    with pytest.raises(ai.VertexNotConfigured, match="GCP_PROJECT_ID"):
        ai.get_client()


async def test_embed_texts_without_project_raises_actionable_error(unconfigured):
    with pytest.raises(ai.VertexNotConfigured, match="GCP_PROJECT_ID"):
        await ai.embed_texts(["hello"], task_type="RETRIEVAL_DOCUMENT")


async def test_generate_json_without_project_raises_actionable_error(unconfigured):
    with pytest.raises(ai.VertexNotConfigured, match="gcloud auth"):
        await ai.generate_json("hi", Answer)


# --- generate_json ------------------------------------------------------------------------


async def test_generate_json_returns_validated_model(settings, monkeypatch):
    models = FakeModels(generate=[SimpleNamespace(parsed=None, text='{"name":"a","score":0.5}')])
    _install(monkeypatch, models)

    out = await ai.generate_json("prompt", Answer, system="sys")

    assert out == Answer(name="a", score=0.5)
    call = models.generate_calls[0]
    assert call["model"] == settings.gemini_model
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].response_schema is Answer
    assert call["config"].system_instruction == "sys"


async def test_generate_json_prefers_sdk_parsed_instance(settings, monkeypatch):
    parsed = Answer(name="p", score=1)
    _install(monkeypatch, FakeModels(generate=[SimpleNamespace(parsed=parsed, text="ignored")]))
    assert await ai.generate_json("prompt", Answer) is parsed


async def test_generate_json_invalid_reply_raises(settings, monkeypatch):
    _install(monkeypatch, FakeModels(generate=[SimpleNamespace(parsed=None, text='{"x":1}')]))
    with pytest.raises(ai.AIResponseInvalid, match="Answer"):
        await ai.generate_json("prompt", Answer)


async def test_generate_json_retries_429_and_5xx(settings, monkeypatch):
    ok = SimpleNamespace(parsed=None, text='{"name":"a","score":1}')
    models = FakeModels(generate=[_api_error(429), _api_error(503), ok])
    _install(monkeypatch, models)

    assert (await ai.generate_json("prompt", Answer)).name == "a"
    assert len(models.generate_calls) == 3


async def test_generate_json_does_not_retry_client_errors(settings, monkeypatch):
    models = FakeModels(generate=[_api_error(403)])
    _install(monkeypatch, models)
    with pytest.raises(errors.ClientError):
        await ai.generate_json("prompt", Answer)
    assert len(models.generate_calls) == 1


# --- embed_texts --------------------------------------------------------------------------


async def test_embed_texts_batches_and_passes_task_type_and_dim(settings, monkeypatch):
    models = FakeModels(embed=lambda kw: _embedding_response(len(kw["contents"])))
    _install(monkeypatch, models)
    monkeypatch.setattr(vertex, "EMBED_BATCH_SIZE", 2)

    vectors = await ai.embed_texts(["a", "b", "c"], task_type="RETRIEVAL_QUERY")

    assert len(vectors) == 3 and all(len(v) == 4 for v in vectors)
    assert [len(c["contents"]) for c in models.embed_calls] == [2, 1]
    cfg = models.embed_calls[0]["config"]
    assert cfg.task_type == "RETRIEVAL_QUERY"
    assert cfg.output_dimensionality == 4
    assert models.embed_calls[0]["model"] == settings.gemini_embedding_model


async def test_embed_texts_falls_back_to_one_per_call_when_batch_rejected(settings, monkeypatch):
    def embed(kw):
        if len(kw["contents"]) > 1:
            raise _api_error(400)
        return _embedding_response(1)

    models = FakeModels(embed=embed)
    _install(monkeypatch, models)

    vectors = await ai.embed_texts(["a", "b", "c"], task_type="RETRIEVAL_DOCUMENT")

    assert len(vectors) == 3
    assert [len(c["contents"]) for c in models.embed_calls] == [3, 1, 1, 1]


async def test_embed_texts_empty_input_makes_no_call(settings, monkeypatch):
    models = FakeModels(embed=lambda kw: pytest.fail("should not be called"))
    _install(monkeypatch, models)
    assert await ai.embed_texts([], task_type="RETRIEVAL_DOCUMENT") == []


async def test_embed_texts_rejects_wrong_dimension(settings, monkeypatch):
    _install(monkeypatch, FakeModels(embed=lambda kw: _embedding_response(1, dim=3)))
    with pytest.raises(ValueError, match="EMBEDDING_DIM"):
        await ai.embed_texts(["a"], task_type="RETRIEVAL_DOCUMENT")
