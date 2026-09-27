---
name: nexus-frontend-standards
description: Coding conventions and best practices for Nexus's client/ (React 19 + TypeScript + Vite + Tailwind v4). Use whenever writing or reviewing frontend code — new components, screens, or changes to existing ones.
---

# nexus-frontend-standards

## Reuse before creating

Check for an existing component before writing a new one — this codebase already has:
`Card`/board pattern, `VerdictBadge`/`CoverageBadge`/`RunStatusBadge`/`RunChip`
([StatusBadges.tsx](client/src/components/StatusBadges.tsx)), `CitationChip`, `Drawer`,
`CommandBar`, `AssigneeSelect`, `Toast`. Extending one of these is almost always right;
adding a near-duplicate is almost always wrong. If a genuinely new pattern is needed, put it
in `client/src/components/` following the existing single-purpose-file convention, not inline
in `App.tsx` (a few legacy views are inline there — don't add to that pile).

## The API contract is `client/src/types.ts`

Never invent a shape for something the backend will eventually own — check `types.ts` first.
If a backend response needs a new field, add it there first and treat it as the source of
truth both sides code against (see `nexus-backend-standards`'s matching rule).

## Design system discipline

- Colors are CSS variables in [index.css](client/src/index.css) (`--accent`, `--bg-*`,
  `--verdict-*`, `--warning`) — never hardcode a hex value in a component. Every color needs
  a working `dark:` pairing; check both themes before calling a UI change done.
- A verdict/coverage/status badge is never color-only — icon + label + color, always (WCAG,
  ui_ux_design.md §11). Reuse `StatusBadges.tsx`'s existing badges rather than rolling a new
  color scheme per screen.
- Spacing/radius/motion: use the existing `--r-sm/md/lg` tokens and the established Tailwind
  utility patterns already in the codebase, not new ad hoc values.

## State management

Global state goes through `ProjectContext` ([context/ProjectContext.tsx](client/src/context/ProjectContext.tsx))
— don't introduce a second state-management pattern (Redux, Zustand, etc.) for something that
fits the existing context. Local component state (`useState`) is fine for UI-only concerns
(open/closed, input drafts).

## Accessibility (non-negotiable per ui_ux_design.md §11)

- Every focusable element gets a visible focus ring; logical tab order.
- Every icon-only control has an `aria-label` or equivalent.
- Respect `prefers-reduced-motion` (the codebase already does this via Tailwind/CSS — don't
  add a raw CSS transform-based animation that ignores it).
- Text scales; no text baked into images.

## Before calling a frontend change done

1. `cd client && npx tsc --noEmit` — must be clean.
2. Check both light and dark mode.
3. If it's a screen/flow covered by `ui_ux_design.md`, run `nexus-spec` first to confirm you
   built what's actually specified (states, keyboard shortcuts, microcopy) — don't improvise.
4. Run `nexus-verify` before considering the work finished.
