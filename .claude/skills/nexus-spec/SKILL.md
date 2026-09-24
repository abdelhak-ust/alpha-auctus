---
name: nexus-spec
description: Look up and quote the exact ui_ux_design.md / architecture.md / build-plan requirements for a Nexus screen or feature before implementing or reviewing it, so work stays grounded in spec instead of improvised. Use before building any screen, flow, or backend service, or when checking whether an implementation matches spec.
---

# nexus-spec

Args: a screen or feature name (e.g. "Reviews", "requirement-validation engine",
"New Project setup").

## 1. Find the exact section

- `ui_ux_design.md` — grep for the feature name or its §4.x screen number. This is the
  source of truth for anything user-facing: layout, states, microcopy, keyboard shortcuts,
  citation rules, accessibility requirements.
- `architecture.md` — grep for the matching capability/component. Source of truth for data
  model, pipeline shape, and the product's non-negotiable principles (cite-or-stay-silent,
  never-silently-miss, etc.).
- `.claude/plans/we-want-nexus-to-sorted-shell.md` — check the feature-catalog letter (§1)
  it belongs to, its phase in §4, and whether it has a detailed section of its own (like §5).

## 2. Quote, don't paraphrase from memory

Pull the actual requirement text — states table rows, keyboard shortcuts, exact microcopy,
data shapes — rather than summarizing from recollection. Specs here are precise on purpose
(e.g. §7's states table, §12's microcopy table, §9's keyboard model); a paraphrase can
silently drop a required state or citation rule.

## 3. Report before writing code

Summarize: what the spec requires, which phase it belongs to and whether that phase's
dependencies are real yet (per the plan's status notes), and anything the request conflicts
with or isn't covered by either doc. An uncovered gap is something to flag and ask about —
never fill it in from taste or from how a similar product elsewhere does it.
