# Implementation log

A dated, narrative record of what's actually been built and verified — not a roadmap (that's
the master plan at `.claude/plans/we-want-nexus-to-sorted-shell.md`) and not a per-feature plan
(those live in `/plans/`). This is the backward-looking counterpart: what landed, when, how it
was verified, and what's still open. Appended to by the `nexus-log` skill after a feature or
phase is implemented and passes `nexus-verify` — newest entry on top.

---

## 2026-09-24 — Dev-standards, planning, and progress-tracking skills

**What:** Four more project skills, closing the gaps from the previous entry's foundations
pass. `nexus-frontend-standards` and `nexus-backend-standards` — this codebase's specific
conventions (component/reuse rules, the design-token system, the API-contract-lives-in-
types.ts rule, async/AI-adapter discipline, migration discipline, error handling) as a
reference while writing code, not just when scaffolding. `nexus-plan` — plans one feature at a
time: grounds it in spec + the master plan's phase status, does an impact analysis (greps
every consumer of anything the feature modifies, especially shared types/schemas, so a
contract change can't silently break a consumer), and saves the result to `plans/<slug>.md`
with `status: active` frontmatter — refuses to start a second plan while one is still active.
`nexus-log` (this skill, used to write this very entry) — records what shipped into this file
and flips the matching `plans/` entry to `done`.

**Files:** `.claude/skills/{nexus-frontend-standards,nexus-backend-standards,nexus-plan,
nexus-log}/SKILL.md` (new); `plans/README.md` (new — the one-active-plan-at-a-time convention);
`IMPLEMENTATION_LOG.md` (new, this file); `CLAUDE.md` (new "Workflow" section tying all six
skills together, plus `plans/`/`IMPLEMENTATION_LOG.md` added to "Repo layout").

**Verified:** `grep -l "^status: active" plans/*.md --exclude=README.md` — confirmed empty
(no plan blocks the first real one). Caught and fixed a real bug in the same pass: the
README's own example frontmatter block literally started a line with `status: active`, which
would have made `nexus-plan` permanently refuse to ever start a feature — fixed by excluding
`README.md` from the check and rewording the example so it can't false-match a similar grep
elsewhere.

**Open:** none — this entry is itself the first real use of `nexus-log`.

**Commit:** `6582610`

## 2026-09-24 — Foundations: CLAUDE.md, project skills, GCP/Vertex AI backend

**What:** `CLAUDE.md`; the first three project skills (`nexus-verify`, `nexus-new-phase`,
`nexus-spec`); backend P0 pivoted from a direct-Anthropic-API/local-only design to GCP-native
(`AnthropicVertex` + Vertex embeddings via Application Default Credentials, Postgres+pgvector
local for dev / Cloud SQL when deployed, arq/Redis local / Cloud Tasks deployed); Alembic wired
to the app's real settings; `gcloud` CLI installed.

**Files:** `CLAUDE.md`; `.claude/skills/{nexus-verify,nexus-new-phase,nexus-spec}/SKILL.md`;
`backend/app/ai/vertex.py` (new); `backend/app/{config.py,main.py}`; `backend/pyproject.toml`;
`backend/migrations/` (new, async Alembic template); `.claude/launch.json`.

**Verified:** `pytest` 4/4, `ruff` clean; direct uvicorn+curl round-trip on `/`, `/api/health`,
`/api/health/ready` (confirms live Postgres + pgvector 0.8.6); `alembic current` connects
cleanly; `app.ai`'s `VertexNotConfigured` error tested for the not-yet-configured case.

**Open:** account-level GCP steps only the user can do (project ID/region, confirm Vertex AI
Model Garden access, `gcloud auth application-default login`); the Browser-pane preview tool
couldn't actually bind either the new backend or (on retest) the previously-working frontend
config this session — flagged as likely session-side preview-daemon state, not an app defect.

**Commit:** `b0bf4fd`

---

## 2026-09-23 — `ui_v2`: BUILD→VERIFY lifecycle screens

**What:** The app was UI-complete for the PLAN half (Board, Verdicts, Memory, Trace, Author,
Sources, Deprecate, Settings) but missing the entire BUILD→VERIFY half the current product
vision is built on. Added: nav regrouped into lifecycle phases (PLAN/BUILD/VERIFY/KNOWLEDGE,
ui_ux_design.md §3) with two triage bells (Verdicts + Reviews); **Runs** (§4.12) — live
activity stream, acceptance-criteria tracker, blocking-question prompt, self-assessment;
**Reviews** (§4.13, the co-hero) — the per-requirement coverage matrix (met/partial/unmet/
off-task, dual citations, staggered reveal, human-only approve); **Delivery** (§4.14) — PR/CI/
build/deploy with the requirement re-check that travels with the PR; run-status chips on board
cards. New screens derive deterministically from real board items (`lib/delivery.ts`) since the
backend for these phases didn't exist yet. Kept the app's established warm accent/neutral
palette rather than the spec's nominal indigo (documented tradeoff, not an oversight).

**Files:** `client/src/components/{RunsView,ReviewsView,DeliveryView,StatusBadges}.tsx` (new);
`client/src/lib/delivery.ts` (new); `client/src/types.ts`, `App.tsx`,
`context/ProjectContext.tsx`; `client/src/components/CommandBar.tsx` (follow-up fix — the ⌘K
"Go to…" list hadn't been updated for the three new screens).

**Verified:** `tsc --noEmit` clean throughout; full live browser walkthrough of every screen in
both light and dark mode (see the session's verification pass) plus a dedicated re-verification
pass after the fact confirming nothing regressed.

**Commits:** `649eda8`, `358f8fc`

---

## 2026-09-23 — Git repository initialized

**What:** The project had no git history (a nested `client/.git` existed but the top-level repo
didn't). Initialized a single top-level repo (removed the nested one — its GitHub history is
safe on `origin`), committed the existing app + `architecture.md`/`ui_ux_design.md` to `main`,
branched `ui_v2` for the UI redesign work above.

**Commit:** `6eb3931` (initial), branch `ui_v2` created from it.
