---
name: mvp-agents
description: Wave 2 of the MVP v0 build. Deterministic ingest convert/split/cite, five agents, three LangGraph graphs, and unit tests with the fake chat model.
---

You own `backend/app/ingest/{convert,split,cite}.py`, `backend/app/agents/*` (except llm.py) and the three graphs. Pipeline code never calls Gemini directly. Tests inject the fake model through `get_chat_model()`.
