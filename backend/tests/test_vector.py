"""app.vector against Qdrant's in-memory mode — no running Qdrant needed."""

import uuid

import pytest
from qdrant_client import AsyncQdrantClient

from app import vector
from app.config import get_settings

pytestmark = pytest.mark.filterwarnings("ignore:Payload indexes have no effect")


@pytest.fixture(autouse=True)
async def memory_qdrant(monkeypatch):
    monkeypatch.setenv("EMBEDDING_DIM", "3")
    get_settings.cache_clear()
    client = AsyncQdrantClient(location=":memory:")
    vector.set_client(client)
    await vector.ensure_collections()
    yield client
    vector.reset_client()
    await client.close()
    get_settings.cache_clear()


def _feature(project_id: str, vec: list[float], name: str = "f") -> dict:
    fid = str(uuid.uuid4())
    return {
        "id": fid,
        "vector": vec,
        "payload": {
            "project_id": project_id, "feature_id": fid, "name": name,
            "lifecycle_state": "consolidated", "source_refs": [], "last_updated": "now",
        },
    }


def _chunk(project_id: str, doc_id: str, feature_ids: list[str], start: int) -> dict:
    cid = str(uuid.uuid4())
    return {
        "id": cid,
        "vector": [1.0, 0.0, 0.0],
        "payload": {
            "project_id": project_id, "doc_id": doc_id, "chunk_id": cid,
            "feature_ids": feature_ids, "section": "Intro", "char_start": start,
            "char_end": start + 10, "text": "hello",
        },
    }


async def test_ensure_collections_is_idempotent(memory_qdrant):
    await vector.ensure_collections()
    names = {c.name for c in (await memory_qdrant.get_collections()).collections}
    assert {vector.FEATURES, vector.CHUNKS} <= names
    info = await memory_qdrant.get_collection(vector.FEATURES)
    assert info.config.params.vectors.size == 3


async def test_search_features_filters_by_project_and_threshold():
    close = _feature("p1", [1.0, 0.0, 0.0], "close")
    far = _feature("p1", [0.0, 1.0, 0.0], "far")
    other_project = _feature("p2", [1.0, 0.0, 0.0], "other")
    await vector.upsert_features([close, far, other_project])

    hits = await vector.search_features("p1", [1.0, 0.05, 0.0], top_k=5, threshold=0.8)

    assert [h.feature_id for h in hits] == [close["id"]]
    assert isinstance(hits[0], vector.ScoredFeature)
    assert hits[0].score > 0.99
    assert hits[0].payload["name"] == "close"


async def test_search_features_defaults_from_settings_and_positional_args():
    a = _feature("p1", [1.0, 0.0, 0.0])
    await vector.upsert_features([a])
    assert [h.feature_id for h in await vector.search_features("p1", [1.0, 0.0, 0.0])] == [a["id"]]
    assert await vector.search_features("p1", [0.0, 0.0, 1.0], 5, 0.8) == []


async def test_upsert_features_is_an_upsert_by_id():
    f = _feature("p1", [1.0, 0.0, 0.0], "v1")
    await vector.upsert_features([f])
    f["payload"]["name"] = "v2"
    await vector.upsert_features([f])
    hits = await vector.search_features("p1", [1.0, 0.0, 0.0], top_k=5, threshold=0.0)
    assert len(hits) == 1 and hits[0].payload["name"] == "v2"


async def test_upsert_requires_project_id():
    bad = _feature("p1", [1.0, 0.0, 0.0])
    del bad["payload"]["project_id"]
    with pytest.raises(ValueError, match="project_id"):
        await vector.upsert_features([bad])


async def test_get_chunks_filters_by_project_feature_and_doc():
    f1, f2 = str(uuid.uuid4()), str(uuid.uuid4())
    d1, d2 = str(uuid.uuid4()), str(uuid.uuid4())
    await vector.upsert_chunks([
        _chunk("p1", d1, [f1], 50),
        _chunk("p1", d1, [f1, f2], 0),
        _chunk("p1", d2, [f2], 0),
        _chunk("p2", d1, [f1], 0),
    ])

    by_feature = await vector.get_chunks("p1", feature_id=f1)
    assert [c["char_start"] for c in by_feature] == [0, 50]
    assert all(c["project_id"] == "p1" for c in by_feature)

    assert len(await vector.get_chunks("p1", doc_id=d2)) == 1
    assert len(await vector.get_chunks("p1", feature_id=f2, doc_id=d1)) == 1
    assert len(await vector.get_chunks("p1")) == 3


async def test_get_client_memory_url(monkeypatch):
    vector.reset_client()
    monkeypatch.setenv("QDRANT_URL", ":memory:")
    get_settings.cache_clear()
    client = vector.get_client()
    assert vector.get_client() is client
    await vector.ensure_collections()
    assert await client.collection_exists(vector.CHUNKS)
    await client.close()
