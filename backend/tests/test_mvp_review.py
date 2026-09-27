"""Feature review_status, skip-remaining, and chat history/kind (chat workflow UX)."""

from sqlalchemy import select

from app.api.routes import mvp as mvp_routes
from app.models import ChatMessage, FeatureQuestion


async def test_feature_defaults_to_pending_review(api_client, make_feature):
    feat = await make_feature()
    resp = await api_client.get(f"/api/projects/proj-test/features/{feat.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["reviewStatus"] == "pending"


async def test_patch_name_summary_and_approve_without_questions(
    api_client, make_feature, monkeypatch
):
    started: list[str] = []

    async def fake_tasks(fid: str) -> None:
        started.append(fid)

    monkeypatch.setattr(mvp_routes, "start_task_graph", fake_tasks)
    feat = await make_feature()

    renamed = await api_client.patch(
        f"/api/projects/proj-test/features/{feat.id}",
        json={"name": "Renamed sign-in", "summary": "Work email only."},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed sign-in"
    assert renamed.json()["summary"] == "Work email only."
    assert renamed.json()["reviewStatus"] == "pending"

    approved = await api_client.patch(
        f"/api/projects/proj-test/features/{feat.id}",
        json={"reviewStatus": "approved"},
    )
    assert approved.status_code == 200
    assert approved.json()["reviewStatus"] == "approved"
    assert started == []


async def test_patch_approve_with_open_questions_409(api_client, make_feature, db_session):
    feat = await make_feature(
        questions=[{"question": "Who?", "why": "roles", "target_field": "user_roles"}]
    )
    resp = await api_client.patch(
        f"/api/projects/proj-test/features/{feat.id}",
        json={"reviewStatus": "approved"},
    )
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert {"problem", "cause", "fix"} <= set(detail)
    assert "open" in detail["cause"].lower() or "question" in detail["problem"].lower()

    await db_session.refresh(feat)
    assert feat.review_status == "pending"


async def test_patch_reject_does_not_generate_tasks(api_client, make_feature, monkeypatch):
    started: list[str] = []

    async def fake_tasks(fid: str) -> None:
        started.append(fid)

    monkeypatch.setattr(mvp_routes, "start_task_graph", fake_tasks)
    feat = await make_feature(
        questions=[{"question": "Who?", "why": "roles", "target_field": "user_roles"}]
    )
    resp = await api_client.patch(
        f"/api/projects/proj-test/features/{feat.id}",
        json={"reviewStatus": "rejected"},
    )
    assert resp.status_code == 200
    assert resp.json()["reviewStatus"] == "rejected"
    assert started == []

    gen = await api_client.post(f"/api/projects/proj-test/features/{feat.id}/tasks/generate")
    assert gen.status_code == 409
    assert {"problem", "cause", "fix"} <= set(gen.json()["detail"])
    assert started == []


async def test_skip_remaining_skips_all_open_never_answers(
    api_client, make_feature, db_session
):
    feat = await make_feature(
        questions=[
            {"question": "Who?", "why": "roles", "target_field": "user_roles"},
            {"question": "When?", "why": "scope", "target_field": "description"},
        ]
    )
    other = await make_feature(
        name="Other",
        position=1,
        questions=[{"question": "Keep me?", "why": "x", "target_field": "description"}],
    )

    # peek may fail or return None; leftover DB skip must still run and never answer.
    resp = await api_client.post(
        "/api/projects/proj-test/clarification/skip-remaining",
        json={"featureId": str(feat.id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["feature"]["id"] == str(feat.id)
    assert body["changes"] == ["Skipped remaining"]

    qs = (
        await db_session.execute(
            select(FeatureQuestion).where(FeatureQuestion.feature_id == feat.id)
        )
    ).scalars().all()
    assert {q.status for q in qs} == {"skipped"}
    assert all(q.answer is None for q in qs)

    kept = (
        await db_session.execute(
            select(FeatureQuestion).where(FeatureQuestion.feature_id == other.id)
        )
    ).scalar_one()
    assert kept.status == "open"
    assert body["remaining"] == 1

    approved = await api_client.patch(
        f"/api/projects/proj-test/features/{feat.id}",
        json={"reviewStatus": "approved"},
    )
    assert approved.status_code == 200
    assert approved.json()["reviewStatus"] == "approved"


async def test_skip_remaining_loops_existing_skip_interrupt(
    api_client, make_feature, db_session, monkeypatch
):
    feat = await make_feature(
        questions=[
            {"question": "First?", "why": "a", "target_field": "user_roles"},
            {"question": "Second?", "why": "b", "target_field": "description"},
        ]
    )
    qs = (
        await db_session.execute(
            select(FeatureQuestion)
            .where(FeatureQuestion.feature_id == feat.id)
            .order_by(FeatureQuestion.ordinal)
        )
    ).scalars().all()
    first, second = qs

    class _Snap:
        def __init__(self, qid: str | None):
            self.values = {"done": qid is None}
            self.tasks = []
            self.next = ()
            self._qid = qid

    def _interrupt_for(qid: str, name: str = "Email sign-in"):
        class _Item:
            value = {
                "questionId": qid,
                "featureId": str(feat.id),
                "featureName": name,
                "question": "?",
                "why": "",
            }

        class _Task:
            interrupts = (_Item(),)

        snap = _Snap(qid)
        snap.tasks = [_Task()]
        return snap

    resumes: list[dict] = []

    async def fake_peek(_pid: str):
        return _interrupt_for(str(first.id))

    async def fake_resume(_pid: str, payload: dict):
        resumes.append(payload)
        assert payload.get("skip") is True
        assert payload.get("answer") in (None, "")
        qid = payload["question_id"]
        q = await db_session.get(FeatureQuestion, __import__("uuid").UUID(qid))
        assert q is not None
        q.status = "skipped"
        q.answer = None
        await db_session.commit()
        if qid == str(first.id):
            return _interrupt_for(str(second.id))
        return _Snap(None)

    monkeypatch.setattr(
        "app.agents.graphs.clarification.peek_clarification_state", fake_peek
    )
    monkeypatch.setattr(
        "app.agents.graphs.clarification.run_clarification_resume", fake_resume
    )

    resp = await api_client.post(
        "/api/projects/proj-test/clarification/skip-remaining",
        json={"featureId": str(feat.id)},
    )
    assert resp.status_code == 200
    assert all(p.get("skip") is True for p in resumes)
    assert all(not p.get("answer") for p in resumes)
    assert {p["question_id"] for p in resumes} == {str(first.id), str(second.id)}

    await db_session.refresh(first)
    await db_session.refresh(second)
    assert first.status == "skipped" and first.answer is None
    assert second.status == "skipped" and second.answer is None


async def test_workflow_and_clarification_history_include_decision_kind(
    api_client, make_feature, db_session
):
    feat = await make_feature()
    patched = await api_client.patch(
        f"/api/projects/proj-test/features/{feat.id}",
        json={"reviewStatus": "approved"},
    )
    assert patched.status_code == 200

    workflow = await api_client.get("/api/projects/proj-test/workflow")
    assert workflow.status_code == 200
    history = workflow.json()["history"]
    decisions = [m for m in history if m.get("kind") == "decision"]
    assert decisions
    assert any("approved" in m["text"].lower() for m in decisions)
    assert decisions[0]["featureId"] == str(feat.id)

    clar = await api_client.get("/api/projects/proj-test/clarification")
    assert clar.status_code == 200
    clar_kinds = {m.get("kind") for m in clar.json()["history"]}
    assert "decision" in clar_kinds

    rows = (
        await db_session.execute(
            select(ChatMessage).where(ChatMessage.project_id == "proj-test")
        )
    ).scalars().all()
    assert any(m.kind == "decision" for m in rows)


async def test_patch_unknown_feature_404(api_client):
    resp = await api_client.patch(
        "/api/projects/proj-test/features/00000000-0000-0000-0000-000000000000",
        json={"reviewStatus": "approved"},
    )
    assert resp.status_code == 404
    assert {"problem", "cause", "fix"} <= set(resp.json()["detail"])


async def test_skip_remaining_unknown_feature_404(api_client):
    resp = await api_client.post(
        "/api/projects/proj-test/clarification/skip-remaining",
        json={"featureId": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404
    assert {"problem", "cause", "fix"} <= set(resp.json()["detail"])
