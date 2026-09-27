# Feature plans

One file per feature, written by the `nexus-plan` skill before implementation starts.

**This is not the master plan.** The whole-platform roadmap (feature catalog, user stories,
architecture, phased build order P0–P9, resolved decisions) lives at
`.claude/plans/we-want-nexus-to-sorted-shell.md` and doesn't move. Files in *this* folder are
finer-grained: one specific feature or slice of a phase, planned right before it's built.

## Convention

Each file is named `<slug>.md` and starts with frontmatter:

```yaml
---
feature: Short human title
phase: P6              # which master-plan phase this belongs to, if any
status: <draft|active|done|abandoned>   # exactly one word, no angle brackets, in a real plan file
created: 2026-09-24
completed:              # filled in when status flips to done
---
```

## The one rule this folder exists to enforce

**Only one file may have `status: active` at a time.** `nexus-plan` checks this before writing
a new plan and refuses to start a second one until the active feature is finished (`done`) or
explicitly dropped (`abandoned`). This is deliberate: it keeps implementation to one feature at
a time instead of several half-finished ones in flight.

`status: draft` is a design written ahead of time and not yet started — any number may exist;
`nexus-plan` flips one to `active` when its implementation begins.

**The feature pipeline** (new standard, 2026-09-26) is three drafts built in order —
`ingestion.md` → `FEATURE_REGISTRY.md` → `Devevloper_tasks_factory.md` — bound together by
`feature-pipeline-contract.md`.

`status: done` files stay in this folder as a record of what was planned and how — they're not
deleted. `nexus-log` flips a plan's status to `done` (and records a completion note) when it
logs that feature as finished in `/IMPLEMENTATION_LOG.md`.
