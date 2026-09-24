---
name: nexus-plan
description: Plan the implementation of ONE feature before building it — confirms it's grounded in spec and correctly placed, analyzes what it could break, and saves the plan to /plans/. Enforces one feature planned/in-progress at a time. Use before starting work on any non-trivial feature or phase slice.
---

# nexus-plan

Args: a feature description (e.g. "Task Contract schema + Drawer editor", "PDF parsing for
ingestion").

This is **not** the master plan (`.claude/plans/we-want-nexus-to-sorted-shell.md` — the
whole-platform roadmap, which doesn't move) and not a replacement for Claude Code's own Plan
Mode. It's a lighter, repo-visible ritual for one feature at a time, with a durable file to
show for it. If Plan Mode's tool restrictions are active when this is invoked, do the analysis
there as usual and write the full plan to the Plan Mode file first — copy it into
`plans/<slug>.md` once plan mode exits, since only the Plan Mode file is editable while it's
active.

## 1. Enforce one-at-a-time — check this FIRST

```bash
grep -l "^status: active" plans/*.md --exclude=README.md 2>/dev/null
```

(`README.md` holds an *example* frontmatter block for illustration — exclude it explicitly, or
this permanently false-positives as an active plan.)

If anything matches: **stop**. Tell the user which feature is already active (its `feature:`
and `created:` frontmatter) and that it needs to reach `done` or `abandoned` (via `nexus-log`
or manually) before a new one starts. Don't proceed to plan a second feature concurrently —
this check exists specifically to prevent that.

If nothing matches, continue.

## 2. Ground it — is this the right feature, in the right place?

Same method as `nexus-spec`:
1. Grep `ui_ux_design.md` and `architecture.md` for the relevant section(s). Quote the actual
   requirements, don't paraphrase from memory.
2. Check the master plan's §1 feature catalog for which letter (A–K) this belongs to, and §4
   for which phase (P0–P9) — confirm that phase's stated dependencies are actually done (see
   the master plan's status notes), not still mocked. If they're not done, say so; planning
   a feature on top of an undone dependency is a trap, not progress.
3. If the request doesn't clearly map to anything in either spec doc or the master plan, flag
   that explicitly rather than inventing scope — ask the user, don't guess.

## 3. Impact analysis — what could this break?

For every file the feature will **modify** (not new files — those can't break anything yet):
1. Find its consumers: `grep -rn` for the exported symbol/type/route across `client/src/` and
   `backend/app/`. List every call site.
2. If it touches a shape in `client/src/types.ts` or a backend schema that mirrors one: list
   every consumer on both sides that assumes the old shape, and how each one will be updated
   (per `nexus-frontend-standards` / `nexus-backend-standards`'s "API contract" rule) — a
   shape change with an unlisted consumer is exactly the kind of break this step exists to
   catch.
3. If it touches a shared component, a DB model, or a websocket/queue message shape: same
   treatment — list what reads/writes it today.
4. Note any behavior change a human would notice that isn't the point of this feature (a
   side effect) — flag it, don't let it ride along silently.

## 4. Write the plan to `plans/<slug>.md`

```markdown
---
feature: <short title>
phase: <P0-P9 or "-">
status: active
created: <today>
completed:
---

# <feature title>

## Spec grounding
<quoted requirements + citations from step 2>

## Placement
<which phase/package/screen, and confirmation its dependencies are real>

## Impact analysis
<step 3's findings — files touched, consumers found, how compatibility is preserved>

## Implementation steps
<concrete steps, files to create/modify — reuse existing utilities named where found>

## Verification
<specific checks — reuse nexus-verify's steps, add feature-specific ones (see
nexus-backend-standards' "Tests" section for what "specific" means)>
```

## 5. Hand off

Implement only this one feature. When it's done and verified, use `nexus-log` — it flips this
file's status to `done` and records the outcome, which is what unblocks planning the next one.
