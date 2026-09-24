from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_health_liveness():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_health_readiness_reaches_db_and_pgvector():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    # nexus_dev has pgvector 0.8.6 installed locally (see backend/README.md)
    assert body["pgvector"] != "not installed"
