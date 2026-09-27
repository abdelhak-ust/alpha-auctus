"""Every MVP route and the structured error shape."""

import io

from app.api.routes import mvp as mvp_routes


async def test_upload_starts_graph_and_lists(api_client, monkeypatch, db_session):
    started: list[str] = []

    async def fake_start(doc_id: str) -> None:
        started.append(doc_id)

    monkeypatch.setattr(mvp_routes, "start_document_graph", fake_start)
    files = {"file": ("spec.md", io.BytesIO(b"# Hello\n\nA spec."), "text/markdown")}
    resp = await api_client.post("/api/projects/proj-test/documents", files=files)
    assert resp.status_code == 202
    body = resp.json()
    assert body["filename"] == "spec.md"
    assert body["status"] == "uploaded"
    assert body["projectId"] == "proj-test"
    assert started == [body["id"]]

    listed = await api_client.get("/api/projects/proj-test/documents")
    assert listed.status_code == 200
    assert any(d["id"] == body["id"] for d in listed.json())

    got = await api_client.get(f"/api/projects/proj-test/documents/{body['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == body["id"]


async def test_duplicate_returns_existing(api_client, monkeypatch):
    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(mvp_routes, "start_document_graph", _noop)
    files = {"file": ("spec.md", io.BytesIO(b"# Same\n"), "text/markdown")}
    first = await api_client.post("/api/projects/proj-test/documents", files=files)
    assert first.status_code == 202
    files = {"file": ("spec.md", io.BytesIO(b"# Same\n"), "text/markdown")}
    second = await api_client.post("/api/projects/proj-test/documents", files=files)
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["id"] == first.json()["id"]


async def test_failed_reupload_restarts(api_client, monkeypatch, db_session, make_document):
    started: list[str] = []

    async def fake_start(doc_id: str) -> None:
        started.append(doc_id)

    monkeypatch.setattr(mvp_routes, "start_document_graph", fake_start)
    content = b"# Retry me\n"
    import hashlib

    digest = hashlib.sha256(content).hexdigest()
    doc = await make_document(content_hash=digest, status="failed", error='{"problem":"x"}')
    files = {"file": ("spec.md", io.BytesIO(content), "text/markdown")}
    resp = await api_client.post("/api/projects/proj-test/documents", files=files)
    assert resp.status_code == 202
    assert resp.json()["id"] == str(doc.id)
    assert started == [str(doc.id)]
    await db_session.refresh(doc)
    assert doc.status == "uploaded"


async def test_unsupported_type_415(api_client):
    files = {"file": ("notes.exe", io.BytesIO(b"MZ"), "application/octet-stream")}
    resp = await api_client.post("/api/projects/proj-test/documents", files=files)
    assert resp.status_code == 415
    detail = resp.json()["detail"]
    assert {"problem", "cause", "fix"} <= set(detail)


async def test_bad_project_id_404(api_client):
    resp = await api_client.get("/api/projects/../etc/documents")
    assert resp.status_code == 404
    assert {"problem", "cause", "fix"} <= set(resp.json()["detail"])


async def test_markdown_and_features(api_client, make_document, make_feature, db_session):
    doc = await make_document(status="ready", markdown="# Spec\n\nHello there world.")
    feat = await make_feature(document=doc, status="needs_clarification")
    md = await api_client.get(f"/api/projects/proj-test/documents/{doc.id}/markdown")
    assert md.status_code == 200
    assert "Hello there world" in md.json()["markdown"]

    listed = await api_client.get("/api/projects/proj-test/features")
    assert listed.status_code == 200
    assert any(f["id"] == str(feat.id) for f in listed.json())

    one = await api_client.get(f"/api/projects/proj-test/features/{feat.id}")
    assert one.status_code == 200
    assert one.json()["name"] == feat.name

    missing = await api_client.get("/api/projects/proj-test/features/not-a-uuid")
    assert missing.status_code == 404


async def test_activity_empty_then_row(api_client, make_feature, db_session):
    feat = await make_feature()
    resp = await api_client.get(f"/api/projects/proj-test/features/{feat.id}/activity")
    assert resp.status_code == 200
    assert resp.json() == []
    from app.graph.audit import record_audit

    await record_audit(
        db_session,
        project_id="proj-test",
        feature_id=feat.id,
        graph="document",
        node="analyse",
        type="agent_step",
        detail={"agent": "Feature Analyst", "detail": "Analysed it."},
    )
    await db_session.commit()
    resp = await api_client.get(f"/api/projects/proj-test/features/{feat.id}/activity")
    assert resp.status_code == 200
    assert resp.json()[0]["agent"] == "Feature Analyst"


async def test_clarification_and_tasks(
    api_client, make_feature, make_task, monkeypatch, db_session
):
    feat = await make_feature(
        questions=[{"question": "Who?", "why": "roles", "target_field": "user_roles"}]
    )

    class _Snap:
        values = {"done": True}
        tasks = []
        next = ()

    async def fake_start(_pid: str):
        return _Snap()

    monkeypatch.setattr(mvp_routes, "_clarification_snapshot", fake_start)
    got = await api_client.get("/api/projects/proj-test/clarification")
    assert got.status_code == 200
    body = got.json()
    assert "history" in body and "remaining" in body

    from app.models import FeatureQuestion

    q = (
        await db_session.execute(
            __import__("sqlalchemy").select(FeatureQuestion).where(
                FeatureQuestion.feature_id == feat.id
            )
        )
    ).scalar_one()

    class _Ans:
        values = {"changes": ["Updated Email sign-in → user_roles"]}
        tasks = []
        next = ()

    async def fake_resume(_pid, _payload):
        q.status = "answered"
        q.answer = "admins"
        await db_session.commit()
        return _Ans()

    monkeypatch.setattr(
        "app.agents.graphs.clarification.run_clarification_resume", fake_resume
    )
    ans = await api_client.post(
        "/api/projects/proj-test/clarification/answer",
        json={"questionId": str(q.id), "answer": "admins"},
    )
    assert ans.status_code == 200
    assert ans.json()["feature"]["id"] == str(feat.id)

    q2_feat = await make_feature(
        questions=[{"question": "Skip?", "why": "x", "target_field": "description"}],
        name="Other",
        position=1,
    )
    from sqlalchemy import select

    q2 = (
        await db_session.execute(
            select(FeatureQuestion).where(FeatureQuestion.feature_id == q2_feat.id)
        )
    ).scalar_one()

    async def fake_skip(_pid, payload):
        assert payload.get("skip") is True
        q2.status = "skipped"
        await db_session.commit()
        return _Snap()

    monkeypatch.setattr("app.agents.graphs.clarification.run_clarification_resume", fake_skip)
    skipped = await api_client.post(
        "/api/projects/proj-test/clarification/skip", json={"questionId": str(q2.id)}
    )
    assert skipped.status_code == 200

    started: list[str] = []

    async def fake_tasks(fid: str) -> None:
        started.append(fid)

    monkeypatch.setattr(mvp_routes, "start_task_graph", fake_tasks)
    gen = await api_client.post(f"/api/projects/proj-test/features/{feat.id}/tasks/generate")
    assert gen.status_code == 202
    assert started == [str(feat.id)]

    task = await make_task(feat)
    patched = await api_client.patch(
        f"/api/projects/proj-test/tasks/{task.id}",
        json={"status": "approved", "title": "Renamed"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "approved"
    assert patched.json()["title"] == "Renamed"
    assert patched.json()["subtasks"] == []
    assert patched.json()["definitionOfDone"] == []

    richer = await api_client.patch(
        f"/api/projects/proj-test/tasks/{task.id}",
        json={
            "subtasks": ["Add the form", "Validate work email", "Reject personal domains"],
            "definitionOfDone": [
                "Tests cover accepted and rejected emails",
                "Cited AC are met",
                "No invented scope",
            ],
        },
    )
    assert richer.status_code == 200
    assert len(richer.json()["subtasks"]) == 3
    assert len(richer.json()["definitionOfDone"]) == 3

    boarded = await api_client.patch(
        f"/api/projects/proj-test/tasks/{task.id}", json={"boardItemId": 42}
    )
    assert boarded.json()["status"] == "on_board"
    assert boarded.json()["boardItemId"] == 42


async def test_unknown_task_404(api_client):
    resp = await api_client.patch(
        "/api/projects/proj-test/tasks/00000000-0000-0000-0000-000000000000",
        json={"status": "approved"},
    )
    assert resp.status_code == 404


async def test_markdown_not_ready_409(api_client, make_document):
    doc = await make_document(status="converting", markdown=None)
    resp = await api_client.get(f"/api/projects/proj-test/documents/{doc.id}/markdown")
    assert resp.status_code == 409
    assert {"problem", "cause", "fix"} <= set(resp.json()["detail"])


async def test_empty_answer_422(api_client, make_feature, db_session):
    feat = await make_feature(questions=[{"question": "Q?", "why": "w", "target_field": "x"}])
    from sqlalchemy import select

    from app.models import FeatureQuestion

    q = (
        await db_session.execute(
            select(FeatureQuestion).where(FeatureQuestion.feature_id == feat.id)
        )
    ).scalar_one()
    resp = await api_client.post(
        "/api/projects/proj-test/clarification/answer",
        json={"questionId": str(q.id), "answer": "   "},
    )
    assert resp.status_code == 422
