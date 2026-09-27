---
name: mvp-backend-api
description: Wave 2 of the MVP v0 build. FastAPI routes under /api/projects/{projectId}, in-process graph runners, startup recovery, and route tests with graphs mocked at the runner boundary.
---

You own `backend/app/api/routes/mvp.py`, registration in `main.py`, background runners, and startup recovery. Errors are `{detail:{problem,cause,fix}}`. Route tests mock graphs at the runner boundary.
