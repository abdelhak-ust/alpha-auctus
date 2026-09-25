---
name: nexus-verify
description: Run the full verification pass for Nexus after implementing or changing anything in client/ or backend/ — client typecheck, backend tests/lint, and the current phase's specific verification steps from the build plan. Use this instead of inventing an ad-hoc check.
---

# nexus-verify

Run every applicable step below, in order. Report each step's pass/fail explicitly — never
silently skip a failing step or declare success without having run it.

## 1. Frontend (if `client/` changed)

```bash
cd client && npx tsc --noEmit && npm test
```

Both must pass (`npm test` runs the `client/db/` repository tests — `node:test` via tsx, in-memory
SQLite, touches no files). If the change is visually/behaviorally observable, drive it in the browser
preview (`preview_start` with the `nexus-client` config from `.claude/launch.json`) — never
launch dev servers with plain `bash`.

## 2. Backend (if `backend/` changed)

```bash
cd backend && poetry run pytest && poetry run ruff check .
```

Both must pass. If a new route was added, also confirm it boots:

```bash
cd backend && poetry run uvicorn app.main:app --port 8000 &
curl -s localhost:8000/api/health/ready
```

## 3. Phase-specific verification (always do this)

1. Open `.claude/plans/we-want-nexus-to-sorted-shell.md`.
2. Find the phase table row (§4) matching what was just built, and — if the phase has its
   own detailed section (like §5's Ingestion pipeline) — read that section's own
   "Verification" subsection.
3. Run those exact checks (e.g. "upload via the existing Sources screen → candidate appears
   in the review queue → approve → real citation in the Drawer"). Don't substitute a
   different check that seems equivalent — the plan's checks were chosen deliberately (e.g.
   §6 calls out that a silent miss on the validation engine is worse than a false alarm).

## 4. Report

State plainly, per step: ran / passed / failed (with the actual error), or not applicable
and why. If anything failed, fix it and re-run before declaring the work done — don't hand
back a "mostly working" result silently.
