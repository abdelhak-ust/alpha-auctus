# UI/UX Design Spec: Nexus — AI-native software delivery platform

Build-ready end-user design for **Nexus**: the platform that carries software work
from unstructured input all the way to deployment, keeping context and traceability
at every stage. This document is the source of truth for *what the developer builds
on screen*: information architecture, every screen, component specs, states, flows,
microcopy, keyboard model, responsive rules, and accessibility.

The central question every screen serves: **"Why does this code exist, what
requirement does it satisfy, what task produced it, and does the final
implementation actually match what was requested?"**

Companion docs:
- Product intent (current): `/Users/abdelhak/.gstack/projects/unicorn/abdelhak-unknown-design-20260809-111036.md` (the 15-stage Nexus vision; supersedes the June doc)
- Product intent (June, superseded): `/Users/abdelhak/.gstack/projects/unicorn/abdelhak-unknown-design-20260601-161532.md`
- System architecture: `architecture.md` (**note:** currently specs only the plan/memory half — stages 1-11. Agent execution, requirement-validation, and PR/verification (stages 12-15) are UI-ahead-of-architecture; see §14 and §15.)

## The lifecycle this spec covers (A to Z)

Nexus is one continuous chain. The 15 stages of the vision map onto the screens in
this spec:

```
INPUT ─▶ UNDERSTAND ─▶ CLARIFY ─▶ TASKS ─▶ BOARD ─▶ VERDICT ─▶ ASSIGN ─▶ EXECUTE ─▶ REVIEW ─▶ PR/VERIFY ─▶ DEPLOY
  1-2        2            3        4       5       6         7         12         13         14           14
                                                   (+8 ask · 9-10 graph/impact · 11 project chat · 15 traceability run throughout)
```

Two experiences carry the product. Both are "hero pixels," and neither may be quiet:
1. **The task verdict** (stage 6) — is a new item net-new, a duplicate, or a conflict with a past decision? (the June wedge, on the board)
2. **The requirement-validation verdict** (stage 13) — did the AI agent's implementation actually satisfy the task and its acceptance criteria? (the current wedge, on the review screen)

Locked decisions feeding this spec:
- **Surface:** a Kanban board that is as easy as a spreadsheet (open/add/move a card in ~1s), plus a review surface that is as glanceable as a good PR review.
- **Aesthetic:** calm, dense, professional (Linear/Notion-grade) — neutral palette, one accent, tight grid, keyboard-first, all verdicts (task conflict AND requirement coverage) as quiet color-coded, cited badges.
- **The spine is traceability.** Every artifact — source, requirement, task, agent run, code change, PR, deploy — links back to why it exists. No orphan screens.

---

## 1. Design principles (the rules every screen obeys)

1. **Spreadsheet-fast or it dies.** Add a card in one keystroke, edit inline, move
   with drag or keyboard. No modal walls between the user and their data.
2. **The verdict is the product — both of them.** Two pixels matter most: the
   task **conflict/dedup verdict** on a new item (§6.1), and the
   **requirement-validation verdict** on an agent's implementation (§6.5). Each must
   be glanceable, cited, and never silently wrong. Surface ranked candidates /
   per-requirement findings for confirmation, never a lone assertion.
3. **Calm under a firehose.** The user is drowning in inputs. The UI stays quiet:
   muted neutrals, one accent, color reserved for meaning (verdicts, status). No
   decoration competes with data.
4. **Decide for me, let me override.** Smart defaults everywhere (auto-tagged
   entities, suggested priority), every default editable in place.
5. **Cite or stay silent.** Any AI statement (verdict, answer, authored doc) shows
   its source as a clickable citation. No citation ⇒ it says "no match / net-new."
6. **Progressive disclosure.** The board is dead simple at rest. Power (impact graph,
   authoring, memory query) is one click away, never in the user's face.
7. **Keyboard-first, mouse-friendly.** Every primary action has a shortcut; nothing
   *requires* the shortcut.
8. **Trace, don't strand.** Every screen answers "why does this exist?" one click
   away: task→requirement→source, code→task, PR→requirement. If a screen can't link
   back up the chain, it's incomplete.
9. **The human is the final approver.** AI verifies, ranks, and explains; it never
   merges, deploys, or closes a requirement on its own. Every AI verdict on an agent's
   work is a recommendation the developer accepts, edits, or rejects.

---

## 2. Design system

### 2.1 Color tokens

Neutral-led, single accent (indigo), semantic colors reserved for verdicts/status.
Values given for **light** and **dark** (ship both; default to system preference).

| Token | Light | Dark | Use |
|-------|-------|------|-----|
| `--bg-app` | `#FFFFFF` | `#0E0F11` | app background |
| `--bg-subtle` | `#F7F8FA` | `#16181C` | board background, panels |
| `--bg-card` | `#FFFFFF` | `#1B1E24` | cards, popovers |
| `--bg-hover` | `#F0F1F4` | `#23262E` | row/card hover |
| `--border` | `#E4E6EB` | `#2A2E37` | hairlines, card borders |
| `--border-strong` | `#CDD1D9` | `#3A404B` | inputs, focused dividers |
| `--text-primary` | `#1A1D23` | `#ECEDEF` | titles, body |
| `--text-secondary` | `#5C6370` | `#9BA1AC` | meta, labels |
| `--text-tertiary` | `#8A909C` | `#6B717C` | placeholders, hints |
| `--accent` | `#5B5BD6` | `#7C7CF0` | primary actions, focus ring, selection |
| `--accent-bg` | `#EEF0FE` | `#23254A` | accent fills, selected rows |
| **Verdict — net-new** | `#3A7D44` on `#E9F5EC` | `#7FD18C` on `#15291A` | "net-new" badge |
| **Verdict — duplicate** | `#8A6D00` on `#FBF3D9` | `#E3C766` on `#2A2410` | "duplicate" badge |
| **Verdict — conflict** | `#B42318` on `#FDECEA` | `#F6897F` on `#2E1513` | "conflict" badge |
| **Verdict — impact** | `#1F6FB2` on `#E6F1FA` | `#7CC0F0` on `#0F2433` | "impact/collision" badge |
| **Req — met** | `#3A7D44` on `#E9F5EC` | `#7FD18C` on `#15291A` | requirement satisfied (reuses net-new green) |
| **Req — unmet** | `#B42318` on `#FDECEA` | `#F6897F` on `#2E1513` | requirement not implemented (reuses conflict red) |
| **Req — partial / at-risk** | `#8A6D00` on `#FBF3D9` | `#E3C766` on `#2A2410` | partially met, weak coverage (reuses duplicate amber) |
| **Req — off-task** | `#1F6FB2` on `#E6F1FA` | `#7CC0F0` on `#0F2433` | change outside the task's scope (reuses impact blue) |
| **Run — active** | `#5B5BD6` on `#EEF0FE` | `#7C7CF0` on `#23254A` | agent running (accent) |
| **Run — blocked** | `#B54708` on `#FBEEDF` | `#F2A65A` on `#2A1C0E` | agent stuck / needs input |
| `--warning` | `#B54708` | `#F2A65A` | low-confidence, needs review |
| `--focus-ring` | `#5B5BD6` @ 2px | `#7C7CF0` @ 2px | keyboard focus (always visible) |

Rule: a verdict is **never** communicated by color alone — always color + label text
+ icon (accessibility, see §11). **One hue, one meaning** across both verdict families:
green = good/met/net-new, red = bad/unmet/conflict, amber = caution/partial/duplicate,
blue = informational/off-task/impact. This keeps a developer's color memory consistent
whether they're triaging the board or a review.

### 2.2 Typography

- **Font:** Inter (UI), `ui-monospace`/JetBrains Mono (IDs, citations, code).
- **Scale (rem / px @16):**

| Token | Size | Weight | Line | Use |
|-------|------|--------|------|-----|
| `display` | 1.75rem/28 | 600 | 1.2 | empty-state headlines only |
| `h1` | 1.25rem/20 | 600 | 1.3 | screen titles |
| `h2` | 1.0rem/16 | 600 | 1.4 | section headers, column titles |
| `body` | 0.875rem/14 | 400 | 1.5 | card titles, body text |
| `meta` | 0.8125rem/13 | 400 | 1.4 | labels, timestamps |
| `mono` | 0.8125rem/13 | 450 | 1.4 | item IDs (`#142`), citations |
| `caption` | 0.75rem/12 | 500 | 1.3 | badges, tags (uppercase tracking 0.02em) |

Density target: card title 14px, board comfortably shows 6–8 cards per column
without scrolling on a 900px-tall viewport.

### 2.3 Spacing, radius, elevation

- **Spacing scale (px):** 2, 4, 6, 8, 12, 16, 20, 24, 32, 48. Default gutter 16.
- **Card padding:** 12 horizontal, 10 vertical (dense).
- **Radius:** `--r-sm` 6px (badges, inputs), `--r-md` 8px (cards, buttons),
  `--r-lg` 12px (panels, modals).
- **Elevation:** flat by default. `--shadow-1` (cards on drag): `0 1px 2px rgba(0,0,0,.06), 0 2px 8px rgba(0,0,0,.08)`. `--shadow-2` (popovers/drawer): `0 8px 24px rgba(0,0,0,.12)`. Dark mode uses border emphasis over shadow.

### 2.4 Iconography & motion

- **Icons:** Lucide (1.5px stroke, 16px default). Consistent set, no mixing.
- **Agent kind icons:** assignee badges for AI agents use a per-kind Lucide glyph —
  design→PenTool, code→Code2, qa→Bug, docs→FileText, test→FlaskConical,
  security→ShieldCheck, custom→Bot — tinted to read distinctly from human-initials chips.
- **Motion:** fast and subtle. Durations 120ms (hover/press), 180ms (drawer/popover),
  240ms (verdict reveal). Easing `cubic-bezier(.2,.8,.2,1)`. Respect
  `prefers-reduced-motion` (drop transforms, keep opacity).
- **The two expressive moments:** (1) task verdict reveal on a new card (§6.1) gets a
  240ms badge pop + candidate list slide; (2) the requirement-validation result (§6.5)
  reveals the coverage matrix row-by-row (staggered 40ms per requirement, 240ms total)
  so the developer *sees* each requirement get checked. Everything else stays calm.

---

## 3. Information architecture & navigation

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  TOP BAR  [Project ▾]  ⌘K Search/Ask  [+ Add]   [Verdicts ●3] [Reviews ●2] [@]│
├────────────┬───────────────────────────────────────────────────────────────────┤
│ LEFT NAV   │  MAIN WORKSPACE (one view at a time)                             │
│ (grouped   │                                                                  │
│  by phase) │                                                                  │
│            │                                                                  │
│ PLAN       │                                                                  │
│  ▢ Board   │   ← default                                                      │
│  ⚑ Verdicts│   (task conflict / dedup)                                        │
│ BUILD      │                                                                  │
│  ⚙ Runs    │   (agent execution — stage 12)                                   │
│ VERIFY     │                                                                  │
│  ✓ Reviews │   (requirement validation — stage 13)  ★ co-hero                 │
│  ⤴ Delivery│   (PRs · CI/CD · deploy — stage 14)                              │
│ KNOWLEDGE  │                                                                  │
│  ⌕ Memory  │   (ask-a-task / project chat)                                    │
│  ⬡ Trace   │   (impact + end-to-end traceability graph)                       │
│  ✎ Author  │                                                                  │
│  ⤓ Sources │   (ingestion / connectors)                                       │
│  ⓘ Deprecate│                                                                 │
│ ──────     │                                                                  │
│  ⚙ Settings│                                                                  │
└────────────┴───────────────────────────────────────────────────────────────────┘
```

- **Left nav groups by lifecycle phase** — PLAN (board, task verdicts), BUILD (agent
  runs), VERIFY (requirement reviews, delivery), KNOWLEDGE (memory, trace, author,
  sources, deprecate) + Settings. Phase labels are quiet section headers, not clickable.
  Collapsible to icons (64px, phase labels become dividers) or hidden (⌘\\). Board is home.
- **Two inbox bells** in the top bar, the product's two triage queues: **Verdicts**
  (unconfirmed task conflicts/dups) and **Reviews** (agent implementations awaiting
  requirement validation). Both show a count badge; both are where a lead spends real time.
- **Top bar** is otherwise global: project switcher, the universal ⌘K command/search/ask
  bar, the global **+ Add**, and the account/data-mode indicator (🔒).
- **One primary view at a time** in the workspace. Card detail, verdict drawer, and
  review drawer open as a **right drawer** over the current view, never a full
  navigation (keeps context).
- **New Project** is a **full-screen takeover** (no left nav / board chrome — there's
  no project context yet), reachable from (a) **first run** and (b) the top-bar
  **Project switcher ▾ → ＋ New project**. Full spec in §4.10–4.11.

Navigation map (the full A-to-Z chain):

```
New Project ─▶ (background ingest) ─▶ Clarification chat ─▶ Task generation ─▶ Verdict review queue ─▶ Board
  │                                                                                                      │
  ▼  (per project, before the board exists — §4.10–4.11, §6.4)                                           ▼
Board ──(click card)──▶ Card Drawer ──(tab)──▶ Overview · Ask · Run · Review · Impact · History · Citations
  │                                                       │        │
  ├─(new item)──▶ inline verdict ──▶ Verdict Drawer       │        └─▶ requirement-validation result (stage 13)
  │              (confirm/dismiss)                        └─▶ live agent execution (stage 12)
  │
  ├─(assign to agent)──▶ Runs ── live agent executions; open one → Run detail (files/commands/tests/progress)
  ├─(agent finishes)──▶ Reviews ── requirement-validation queue; open one → Review (coverage matrix, §4.13)
  ├─(review passes)──▶ Delivery ── PR · diff · CI/CD · build · deploy, with continuous requirement re-check (§4.14)
  │
Memory (Ask) ── conversational query + project-level chat over all items, decisions, runs, PRs
Trace ── entity/impact graph, extended: source → requirement → task → run → code → PR → deploy
Author ── pick scope → generate BRD/spec/task-tree (cited)
Sources ── connectors, ingest log, per-source review queue
Deprecate ── ranked retire suggestions
Settings ── data mode (BYO-key/no-retention), members, agents, entities, GitHub, audit log
```

---

## 4. Screen specs

Each screen lists: layout, components, states, interactions, keyboard.

### 4.1 Board (home)

The frictionless surface. Columns are statuses; cards are items. Must feel like a
spreadsheet you can also drag.

```
┌─ Board ───────────────────────────────────────── [Group: Status ▾] [Filter] ─┐
│                                                                                │
│  INBOX (12)        NEXT (8)         IN PROGRESS (5)     DONE (40)              │
│  ┌──────────────┐  ┌──────────────┐ ┌──────────────┐   ┌──────────────┐       │
│  │ #142 Add SSO │  │ #98  Rate... │ │ #71 Billing  │   │ ...          │       │
│  │ ⚑ conflict #4│  │ ◇ net-new    │ │ area: auth   │   │              │       │
│  │ area: auth   │  │ ★ P1         │ │ ▣▣▣ 3 subtsk │   │              │       │
│  └──────────────┘  └──────────────┘ └──────────────┘   └──────────────┘       │
│  ┌──────────────┐  ┌──────────────┐                                            │
│  │ + Add card   │  │ #95 Export…  │                                            │
│  └──────────────┘  │ ⧉ dup of #88 │                                            │
│                    └──────────────┘                                            │
└────────────────────────────────────────────────────────────────────────────────┘
```

**Card anatomy (dense):**
```
┌────────────────────────────────┐
│ #142  Add SSO for enterprise   │  ← mono ID + title (14px)
│ ⚑ Conflicts with decision #4   │  ← verdict badge (only if not net-new/plain)
│ ⬡ auth   ★ P1   👤AM   ⤓ call  │  ← entity tag · priority · assignee · source icon
└────────────────────────────────┘
```
- Verdict badge shows only when verdict ∈ {duplicate, conflict, impact} or while
  "checking". Net-new/confirmed-clean cards show no badge (calm).
- The **assignee** slot is either a **human** (initials chip, accent tint) or an
  **AI agent** (kind icon + short agent name in a distinct violet/kind tint, e.g.
  `⌨ Claude Code`) — see §2.4. One assignee per card. Assigning to an AI agent (Claude
  Code in the MVP) can **launch a run** (§4.12); a small run-status chip then appears on
  the card (`⚙ running` / `✓ 5/7 met` / `⚑ needs review` / `⚠ blocked`), so the board
  doubles as an at-a-glance execution dashboard.
- Source icon (⤓ doc / 🎙 transcript / ✉ email / 🎫 ticket / ⊞ sheet) appears when the
  item came from ingestion; click opens the cited source snippet.

**Add a card (the 1-second promise):**
- Click "+ Add card" or press `n` (new card in focused column) or `N` (new in Inbox).
- An inline editable card appears in place, cursor in the title field. Type, press
  `Enter` to commit and immediately open a new blank card below (rapid entry);
  `Esc` to stop. **No modal.**
- On commit, the card silently enters the conflict/dedup check (see §6.1). A small
  pulsing dot (`⟳ checking`) sits on the card for ~1–3s, then resolves to a verdict
  badge or nothing.

**Inline edit:** click any card title to edit in place. Click the entity tag/priority
to change via a tiny inline popover. Drag to reorder/move columns; or focus a card and
use `←/→` to move columns, `↑/↓` to reorder.

**Board controls:**
- **Group by** (Status default; also Entity/Area, Priority, Source, Verdict).
- **Filter** chip bar (by entity, priority, verdict type, source, assignee — humans and
  AI agents — date).
- **Density toggle** (comfortable / compact). Compact hides the meta row until hover.

**States:**
- *Empty project:* big friendly empty state (see §7) with "Paste your backlog" and
  "Connect a source" CTAs.
- *Empty column:* dashed "+ Add card" placeholder only.
- *Loading:* skeleton cards (3 per column) with shimmer.
- *Filtered to nothing:* "No cards match these filters — Clear filters".

**Keyboard:** `n`/`N` new, `Enter` open card, `e` edit title, `←/→/↑/↓` move/reorder,
`x` select, `⌘K` command bar, `/` focus filter, `g b` go board.

### 4.2 Card drawer (item detail)

Opens from the right (480px, resizable to 640) over the board. Context stays visible.

```
┌─ #142  Add SSO for enterprise ───────────────────────────── [⤢] [×] ┐
│ Status: Inbox ▾   ★ P1 ▾   👤 AM / ⌨ Claude Code ▾   ⬡ auth ✕  + tag    │
│─────────────────────────────────────────────────────────────────────│
│ [ Overview ][ Ask ][ Run ][ Review ][ Impact ][ History ][ Citations ]│
│─────────────────────────────────────────────────────────────────────│
│ ⚑ CONFLICT — contradicts decision #4                       82% ▸     │
│   “We decided NOT to build our own SSO; use the customer’s IdP.”      │
│   from: 2026-03 Architecture call · ⤓ open source     [Resolve ▾]    │
│─────────────────────────────────────────────────────────────────────│
│ Description (click to edit)                                          │
│ Enterprise clients are asking for built-in SSO…                     │
│                                                                      │
│ Linked items:  ⧉ near-dup #95 ·  ⬡ same area: #71                   │
│ Subtasks ▣▣▢                                                         │
└─────────────────────────────────────────────────────────────────────┘
```

- **Tabs:** Overview (default), Ask (chat scoped to this item), **Run** (live agent
  execution for this task when assigned to an AI agent — the per-task view of §4.12),
  **Review** (the requirement-validation result for this task — the per-task view of
  §4.13; the tab shows a coverage summary badge, e.g. "5/7 met", once a run finishes),
  Impact (mini graph of what this touches), History (audit of edits + decisions + runs
  + PRs over time), Citations (every source snippet that informs this item).
- **Tab availability:** Run and Review appear only once the task has been assigned to an
  agent / has at least one run. Before that they show a one-line empty state ("Assign to
  an agent to run and verify this task"), never a dead tab.
- **Verdict banner** at top when applicable, with the cited decision quoted inline,
  confidence %, and a **Resolve** menu: *Confirm conflict · It's fine (dismiss) ·
  Supersede decision #4 · Merge into #95 (if dup)*.
- **Assignee** is a searchable picker grouped into **People** and **AI Agents**: type to
  filter both, with an inline "+ Add person" and "+ Add custom agent" row. Selecting an
  agent shows a small caption beneath the field — "AI agent · <description>" — and stamps
  the card with the agent badge (§4.1). The agent catalog is managed in Settings (§4.9).
- Everything inline-editable. `⤢` expands to full page; `×` or `Esc` closes.

### 4.3 Verdicts inbox

The triage queue for everything the engine flagged. This is where a lead spends the
"is this new or already decided?" time. Ranked, confirmable, never auto-applied.

```
┌─ Verdicts ─────────────────────────  [All ▾] [Conflict] [Dup] [Impact] ┐
│ 3 need review · 12 resolved today                       [Confirm all ✓] │
│────────────────────────────────────────────────────────────────────────│
│ ⚑ CONFLICT   #142 Add SSO  ⇄  decision #4 “don’t build SSO”      82%    │
│    ▸ 2 more candidates                          [Confirm] [Dismiss] [⋯] │
│────────────────────────────────────────────────────────────────────────│
│ ⧉ DUPLICATE  #95 Export CSV  ⇄  #88 CSV export                    91%    │
│    suggested: merge #95 → #88                   [Merge]   [Keep both]   │
│────────────────────────────────────────────────────────────────────────│
│ ⬡ IMPACT     #150 Change auth flow  →  touches #71, #120, decision #9   │
│                                                 [Review]  [Acknowledge] │
└────────────────────────────────────────────────────────────────────────┘
```

- Each row = new item ⇄ what it matched, with **confidence** and the **top-3 ranked
  candidates** expandable (`▸`). The design doc's accuracy bar: show ranked candidates,
  let the human confirm; optimize so a real conflict is never silently missed.
- **Confidence < threshold** ⇒ row tinted `--warning` with "Low confidence — please
  review", and bulk "Confirm all" excludes it.
- Resolving a row writes the relationship (merge/supersede/link) and removes it from
  the queue; an undo toast appears for 6s.
- Empty state: "All clear. New items will show up here when they look like a duplicate
  or conflict with a past decision."

### 4.4 Memory / Ask (ask-a-task + global query)

Conversational query over all items and decisions. Reached via ⌘K ("Ask…") or left nav.

```
┌─ Memory ───────────────────────────────────────────────────────────┐
│  Ask anything about this project…                            [↵]     │
│─────────────────────────────────────────────────────────────────────│
│  Q: why did we decide against building SSO?                          │
│                                                                      │
│  A: In the 2026-03 architecture call the team decided to rely on    │
│     the customer’s IdP instead of building SSO, to avoid owning      │
│     credential security. [decision #4 ▸]  It was reaffirmed when     │
│     #71 (billing auth) shipped. [#71 ▸]                              │
│                                                                      │
│     Sources:  🎙 Arch call 2026-03-14 (12:04)   ▣ #71                │
│     ─────────────────────────────────────────────────────────       │
│     Follow-ups:  • What would change that decision?                  │
│                  • Show everything touching ‘auth’                   │
└─────────────────────────────────────────────────────────────────────┘
```

- Answers are **always cited** with clickable chips (decision/item/source). Clicking a
  citation opens the source snippet or item drawer.
- Streaming response with a typing indicator; a "thinking… searching memory" status
  while retrieval runs.
- Suggested follow-ups under each answer.
- Scoped variant: the same component inside a card drawer's **Ask** tab is pre-scoped
  to that item ("What is this / what it depends on / why decided").
- **Project-level chat (stage 11).** The same surface answers status questions over the
  live execution state, not just the plan: "What's the state of authentication?",
  "Which tasks are assigned to AI agents right now?", "What changed this week?", "Which
  requirements haven't been implemented yet?", "Are there any unresolved spec conflicts?",
  "What's blocking release?" Answers cite the runs, reviews, and PRs behind them (§4.12–4.14).
- Empty/first-run: example prompts ("Is anyone already working on X?", "What did we
  decide about Y?", "What breaks if we change Z?", "Which requirements are still unmet?").

### 4.5 Trace (impact + end-to-end traceability) — stages 9, 10, 15

Visualizes what a change touches AND the full chain from origin to deployment.
Graph-first, explanation second.

```
┌─ Impact ───────────────────  pick an item/decision to trace ────────┐
│                                                                      │
│              ┌─ decision #4 (don’t build SSO)                        │
│   #142 ──────┤                                                       │
│  (Add SSO)   └─ ⬡ auth ── #71 billing-auth                           │
│                          └ #120 login redirect                       │
│                                                                      │
│  Selected: #142  →  contradicts 1 decision, touches 2 items          │
│  [Explain ▾]  “Changing this re-opens the SSO decision and affects   │
│               the login redirect (#120)…”                            │
└──────────────────────────────────────────────────────────────────────┘
```

- Nodes: sources (⤓), requirements/decisions (◆), items/tasks (▢), entities/areas (⬡),
  **agent runs (⚙), code changes (⌘), PRs (▲), deploys (⤴)**. Edges typed and labeled
  (affects / depends-on / contradicts / supersedes / **implements / verified-by /
  shipped-in**), color per type.
- **The end-to-end chain (stage 15).** A dedicated "Trace" mode on any task renders the
  spine as a horizontal chain, each hop clickable and cited:
  `Source → Requirement → Task → Run → Code → PR → Deploy`. This is how a developer
  answers "why does this line of code exist?" — click the deploy, walk back to the
  customer call that requested it. The chain is the product's spine (principle #8).
- Click a node to recenter; hover to highlight its neighborhood and dim the rest.
- "Explain" turns the selected subgraph into a cited natural-language summary (e.g.
  "changing decision #4 re-opens SSO, affects #120, and touches shipped PR #318").
- Controls: zoom/fit, filter by edge/node type (toggle plan-side vs delivery-side),
  search to focus a node.
- Scales gracefully: beyond ~40 visible nodes, collapse by entity cluster or by
  lifecycle phase with a count badge ("auth +12"); expand on click.

### 4.6 Sources (ingestion)

Where the firehose connects, and where extracted items get reviewed before they land.

```
┌─ Sources ────────────────────────────────────────────────────────────┐
│ Connectors                                                            │
│  ⊞ Google Sheet  ✓ synced 2m ago   ✉ Feedback inbox  ● 4 new          │
│  🎙 Meeting transcripts (webhook)  ✓   🎫 Tickets (Jira)  + Connect    │
│  ⤓ Upload files (drag & drop here)                                     │
│─────────────────────────────────────────────────────────────────────│
│ Ingest review queue (7)            extracted items await confirm      │
│  🎙 Arch call 2026-05-30 → 5 items, 2 decisions       [Review →]      │
│  ✉ Customer email → 3 feedback items                  [Review →]      │
│─────────────────────────────────────────────────────────────────────│
│ Ingest log:  2026-05-30 14:02  transcript parsed → 5 items …          │
└───────────────────────────────────────────────────────────────────────┘
```

- **Every ingested source is dedup/conflict-checked before items land** — the review
  queue shows extracted items with their verdicts, so ingestion is never a dumb dump.
- Per-source review screen reuses the Verdicts row component, grouped by source, with
  the original snippet shown beside each extracted item.
- Connector cards show status (synced/error/needs-auth) and a count of pending items.
- Drag-and-drop file zone with progress + parse status per file.
- States: no connectors (onboarding CTA), syncing (progress), error (clear cause +
  "Reconnect"), empty queue ("Nothing waiting — connected sources are quiet").
- **Same pipeline as New Project.** The New Project **Files / Videos / Images** zones
  (§4.10) are just the first-run entry to *this* ingestion pipeline, and tasks generated
  from the clarification chat (§4.11) land in *this* review queue. One dedup/conflict
  path, one review component — no parallel machinery for onboarding vs. steady state.

### 4.7 Author (BRD / spec / task tree)

Turns accumulated memory into a cited document.

```
┌─ Author ──────────────────────────────────────────────────────────────┐
│ Generate:  ( BRD )  ( Tech spec )  ( Task tree )                       │
│ Scope:  [⬡ auth ✕] [+ area]   from  [last 30 days ▾]                   │
│ [ Generate → ]                                                         │
│─────────────────────────────────────────────────────────────────────│
│  # Authentication BRD (draft)                          [Copy] [Export]│
│  ## Background                                                        │
│  The team decided to rely on customer IdP… [decision #4 ▸]           │
│  ## Requirements                                                      │
│  - SSO via customer IdP [#142 ▸] [🎙 call ▸]                          │
│  …                                                                    │
│  ⚠ 1 unresolved conflict in scope (#142 ⇄ #4) — resolve first? [Open]│
└───────────────────────────────────────────────────────────────────────┘
```

- Output is a live, editable draft. **Every claim carries a citation chip** back to a
  decision/item/source. Hover a chip to preview, click to open.
- If the chosen scope contains **unresolved conflicts**, a banner warns before/at
  generation ("authoring on top of an unresolved contradiction") with a jump to fix.
- Export: Markdown, PDF, copy-to-clipboard; "Send to…" (Google Doc/Notion later).
- Streaming generation with section-by-section reveal; cancelable.

### 4.8 Deprecate

Ranked suggestions of what to retire, each justified and cited.

```
┌─ Deprecate ───────────────────────────────────────────────────────────┐
│ Suggested to retire (5)                                               │
│  #33 Legacy CSV import — superseded by #88 (decision #12)   [Retire]  │
│  #51 Beta feedback widget — no activity 90d, area dormant   [Retire]  │
│        why? ▸                                          [Keep] [Snooze] │
└───────────────────────────────────────────────────────────────────────┘
```

- Each suggestion states the reason (superseded-by / dormant / contradicted) with
  citations. Actions: Retire (archives, not deletes), Keep, Snooze (30d).
- Never auto-retires. Bulk select + retire with undo.

### 4.9 Settings — data posture (enterprise-critical)

Makes the BYO-key/no-retention promise visible and configurable — the thing that
unblocks enterprise.

```
┌─ Settings ▸ Data & AI ────────────────────────────────────────────────┐
│ AI provider                                                           │
│  ( ) Managed (we run the AI)  — fastest start, for evaluation         │
│  (•) Bring your own key       — your data, your key, your region      │
│       Provider [Anthropic ▾]  Key [••••••••]  Region [us ▾]  [Test]   │
│  Embeddings  [Voyage ▾]  Key [••••••••]                               │
│─────────────────────────────────────────────────────────────────────│
│ Data handling                                                         │
│  ☑ No-retention mode (AI calls request zero data retention)          │
│  ☑ Keep raw content only in our tenant store                          │
│  Audit log: every AI call recorded            [View audit log →]      │
│─────────────────────────────────────────────────────────────────────│
│  Status: 🔒 BYO-key · no-retention · isolated tenant                  │
└───────────────────────────────────────────────────────────────────────┘
```

- The top-bar account chip shows a small 🔒 with the active mode; hovering explains it.
  This is a trust signal an enterprise reviewer looks for.
- Other settings sections: Members & roles, **AI Agents** (below), Entities/Areas (manage
  the tag vocabulary), Projects, Billing.

**Settings ▸ AI Agents** — the workspace-wide catalog of agents a card can be assigned to.

```
┌─ Settings ▸ AI Agents ────────────────────────────────────────────────┐
│ Workspace catalog · shared across projects            runs?           │
│  ⌨ Claude Code         code     [Built-in]            ● runs (MVP)     │
│  ✎ Figma AI            design   [Built-in]            ○ assignment-only│
│  ⌨ GitHub Copilot      code     [Built-in]            ○ assignment-only│
│  … Backend Dev · QA Tester · Docs Writer · Security   ○ assignment-only│
│  🤖 Data Pipeline Agent custom   [×]                   ○ assignment-only│
│─────────────────────────────────────────────────────────────────────│
│  + Add agent   Name [____________]   Kind [Custom ▾]   [Add]          │
└───────────────────────────────────────────────────────────────────────┘
```

- Each row: kind icon + name + kind + a **runs?** indicator. **Claude Code** is the only
  agent that actually **executes** in the MVP (● runs → launches §4.12 and feeds §4.13);
  every other catalog entry is **assignment-only** (○ marks ownership on a card, no run).
  This keeps the board's assignee model honest about what will and won't happen when you
  assign. **Built-in** agents carry a tag and cannot be removed; **custom** agents have a
  remove (×). The card-drawer picker's "+ Add custom agent" writes into this same catalog.
- **Execution scope:** for **Claude Code** (the MVP agent), assignment can **launch a real
  run** with full activity streaming and requirement validation (§4.12–4.14). **Deferred:**
  real **Figma / Copilot / Cursor** integrations (catalog entries exist, but they are
  assignment-only until built) and **multi-agent orchestration** (agents coordinating /
  splitting one feature across several runs — stages 6-7's orchestration ambition). MVP is
  single-agent-per-task; see the deferred list at the end and the design doc's open question
  on orchestration (the most crowded, best-funded battleground — enter with a named edge or
  not at all).

### 4.10 New Project (guided setup)

The **entry point to every project** — the first thing a first-time user sees, and the
view behind Project switcher ▾ → ＋ New project. Full-screen takeover, single
left-aligned column (~640px), one visual anchor (headline + description). It seeds the
memory layer from the inputs a lead already has, so the board is never born empty.

**Anti-slop guard:** the three source inputs are a **stacked labeled list**, not three
symmetric centered cards. One accent, left-aligned, description is the loudest element.

```
┌─ New project ─────────────────────────────────────────────────┐
│   Start a new project                                (h1)      │
│   Drop in what you already have. We'll read it and ask a       │
│   few questions before building your board.          (body)    │
│                                                                │
│   Description  *required                                       │
│   ┌──────────────────────────────────────────────────────┐    │
│   │ What is this project? Goals, stakeholders, context…  │    │
│   └──────────────────────────────────────────────────────┘    │
│                                                                │
│   Sources  (optional)                                          │
│   ⤓ Files    docs, PDFs, specs, CSVs        [drop or browse]   │
│   ▶ Videos   meeting & client calls         [drop or browse]   │
│   ▧ Images   whiteboards, diagrams          [drop or browse]   │
│      brief.pdf ✓   call-0530.mp4 ⟳ 12MB   board.png ✓          │
│                                                                │
│   GitHub repo  (optional)                                      │
│   [ github.com/org/repo             ]  ⓘ we'll scan code &     │
│                                         track progress here    │
│                                                     [Skip]     │
│                                                                │
│                 [ Ingest & continue → ]   ← disabled until     │
│                                             description filled │
└────────────────────────────────────────────────────────────────┘
```

- **Three distinct inputs, distinct accepted types.** Files: `pdf, docx, md, txt, csv`
  (project documents). Videos: `mp4, mov, m4a, wav`, audio ok (meeting/client calls).
  Images: `png, jpg, svg, pdf` (whiteboards, diagrams). Each zone rejects the others'
  types with a clear inline message. Multi-file; **drag-drop and a visible `browse`
  button** (click/keyboard fallback — no drop-only zones, §11).
- **Description is the only required field.** Primary CTA `Ingest & continue →` stays
  disabled until it has content; the requirement is a visible label + `aria-required`,
  never placeholder-only. Sources and GitHub are optional — a description-only project
  is valid and goes straight to the chat (§4.11).
- **GitHub field.** Live URL validation (✓ valid / ✗ "that doesn't look like a repo
  URL"), a `Skip` link, and helper copy: "we'll scan existing code and track progress
  here once connected." **No analysis happens in this spec** — the URL is captured for
  a later connector (see the deferred list).
- **States.** Empty (fresh, CTA disabled) · uploading (per-file name + size + progress +
  parse status ✓/⟳/⚠) · unsupported type · file too large · description-only / no
  sources (valid) · GitHub invalid. Uploads continue in the background once submitted;
  the user does not wait on this screen.
- **Keyboard.** Tab order: description → each source zone (`Enter`/`Space` opens the
  file picker) → GitHub → CTA. `⌘/Ctrl+Enter` submits from anywhere on the screen.

### 4.11 Clarification chat

Opens **immediately** after `Ingest & continue` — no waiting on ingestion. A calm
conversational panel grounded on the description plus whatever sources have finished so
far, with a persistent **background-ingest indicator**. The AI asks a bounded set of
clarification questions, then generates the first tasks.

```
┌─ Setting up: "Acme redesign" ──────────── reading sources ▓▓░ ─┐
│  ⚙ brief.pdf ✓ · call-0530.mp4 ⟳ transcribing · board.png ✓    │
│                                                                │
│  🤖 I've read your brief and the whiteboard. Who's the primary │
│     decision-maker here?                        [brief.pdf ▸]  │
│                                                                │
│                                 You:  The client's CTO, Dana   │
│                                                                │
│  🤖 Got it. Is the May 30 call the latest source of truth, or  │
│     does the brief win where they disagree?                    │
│                                                                │
│  ┌──────────────────────────────────────────────────────┐     │
│  │ Type your answer…                                     │     │
│  └──────────────────────────────────────────────────────┘     │
│                                        [ Generate tasks → ]     │
└────────────────────────────────────────────────────────────────┘
```

- **Grounded and cited.** When the AI references a source it shows a `CitationChip`
  (§8) back to that source — consistent with "cite or stay silent" (principle #5).
- **Background ingest surfaced.** Header progress bar + a per-source row; sources light
  up ✓ as they finish, and the AI may fold in a late arrival ("just finished the call —
  one more question"). Ingestion runs on the async job queue (`architecture.md`), so
  slow inputs like video transcription never block the conversation.
- **Bounded, terse-friendly.** A small set of core questions; short answers are fine.
  `Generate tasks →` becomes enabled once the core questions are answered (or the user
  triggers it). This **completes** the guided flow — it is not a "skip to a blank
  board" escape (the first-project flow is mandatory; the mitigation is that it's never
  dead waiting).
- **States.** AI thinking (§7 "AI working" ellipsis) · ingestion still running · a
  source failed to parse (inline, non-blocking: "couldn't read call-0530.mp4 — continue
  without it? / retry") · user sends empty / very terse.
- **On `Generate tasks`.** Transition to the **verdict review queue** (§4.6): proposed
  tasks, each dedup + conflict-checked with citations, human confirms before they land
  on the board. For a brand-new project (empty memory, §13) everything is net-new, so
  this is a light "confirm all / edit" pass, then the Board opens.
- **Keyboard.** `Enter` sends, `Shift+Enter` inserts a newline; `Generate tasks`
  reachable via Tab.

### 4.12 Runs (agent execution) — stage 12

Where AI-agent work stops being a black box. A top-level **Runs** queue lists every
active/recent agent execution; opening one (or the card drawer's **Run** tab) shows the
live detail. MVP agent: **Claude Code**.

```
┌─ Runs ──────────────────────────────────  [Active] [Done] [Blocked] [All ▾] ┐
│  ⚙ #142 Add SSO           ⌨ Claude Code   ▓▓▓▓░ 68%  12 files · 4 cmds · running│
│  ⚠ #150 Change auth flow  ⌨ Claude Code   blocked — needs a decision   [Open →]│
│  ✓ #98 Rate limiting      ⌨ Claude Code   done · review ready  ✓5/7 met [Review]│
└───────────────────────────────────────────────────────────────────────────────┘
```

**Run detail** (top-level page, or the card-drawer Run tab, ~640px):

```
┌─ Run · #142 Add SSO ─── ⌨ Claude Code ─────────── running ▓▓▓▓░ 68% [Stop] ┐
│ Task context sent ▸  (requirements · acceptance criteria · related tasks ·   │
│                       repo context · prior decisions · citations — §4.7)      │
│──────────────────────────────────────────────────────────────────────────────│
│ Activity (live)                                        Files changed (12)     │
│  14:02 read  auth/session.ts                            M auth/routes.ts  +48 │
│  14:03 edit  auth/routes.ts  (+48 −6)                   A ui/Signup.tsx  +120 │
│  14:05 run   `npm test`  → 41 pass, 0 fail              M ui/api.ts      +22  │
│  14:06 note  "validating field rules against AC #3"     …                     │
│  14:07 ⚠ blocked: "AC #5 says lock after 5 tries —      Acceptance criteria   │
│         is that per-account or per-IP?"                   AC1 ✓ AC2 ✓ AC3 ⟳    │
│         [Answer inline ▾]                                 AC4 – AC5 ⚠ blocked  │
│──────────────────────────────────────────────────────────────────────────────│
│ Agent self-assessment: "Signup UI + API wired; AC5 pending your answer."      │
│                                     [Answer & continue]  [Stop]  [Hand to human]│
└────────────────────────────────────────────────────────────────────────────────┘
```

- **Not a black box.** Live stream of what the agent did: files read/modified (with
  ±line counts), commands run and their results, tests executed, and free-text notes the
  agent emits ("validating field rules against AC #3"). Streamed over the websocket
  (same channel as live verdicts, `architecture.md` §Surface).
- **Acceptance-criteria tracker** runs alongside: each AC from the task shows ✓ done /
  ⟳ in progress / – not started / ⚠ blocked, so the human sees *coverage forming in real
  time*, not just activity.
- **Blocking questions are first-class.** When the agent hits ambiguity it **pauses and
  asks** (mirrors the clarification chat, §4.11) rather than guessing — this is the
  product's answer to "agents guess wrong when the task is vague." Answer inline →
  agent resumes. Unanswered blocks surface on the board (`⚠ blocked` chip) and in the
  Runs queue.
- **Agent self-assessment** at the end: the agent states whether it believes the AC are
  met. This is the agent's *claim*; §4.13 is where that claim gets **independently
  checked** — the two are deliberately separate (an agent grading its own work is not
  verification).
- **Controls:** Stop (halts the run, keeps work-in-progress), Hand to human (converts to
  a human-assigned task carrying the run's context), Answer & continue.
- **States:** queued (waiting for a runner slot) · running · blocked (needs input) ·
  done (→ review ready) · failed (agent errored / provider outage — show cause + Retry) ·
  stopped by user. Never a stuck spinner: a run with no event for >N seconds shows
  "no activity — still working / check run?" with a Stop affordance.
- **Keyboard:** `j/k` move between runs, `Enter` open, `s` stop focused run, `a` focus
  the answer box on a blocked run.

> **Architecture note:** running Claude Code against a repo, streaming its activity, and
> the runner/sandbox model are **not in `architecture.md` today** (it explicitly models
> agents as assignment targets only). This screen depends on new backend work; see §14.

### 4.13 ⭐ Requirement-validation review — stage 13 (co-hero screen)

**The screen the new product is built on.** After a run finishes, the task enters
**review**: Nexus compares the original requirement → task spec → agent implementation →
code changes → tests, and tells the developer, per requirement, whether the
implementation actually satisfies it — with citations to both the requirement and the
code. This is not "is the code good" (CodeRabbit/tests answer that); it is **"did the
agent build what was asked."**

A top-level **Reviews** queue (parallels Verdicts) lists implementations awaiting
validation; opening one (or the card-drawer **Review** tab) shows the review. The
**requirement coverage matrix** is the hero.

```
┌─ Review · #142 Add SSO ──────────────── ⌨ Claude Code · run 14:08 ──── [⤢][×] ┐
│  Requirement coverage                             5 / 7 met · 1 unmet · 1 off-task│
│  ┌────────────────────────────────────────────────────────────────────────────┐│
│  │ ✓  R1 Signup form with email + password        met      → ui/Signup.tsx:1  ││
│  │ ✓  R2 Connect to existing auth API             met      → ui/api.ts:22     ││
│  │ ⚠  R3 Validate required fields                  partial  AC: min-length rule ││
│  │       spec said 8+ chars w/ 1 number; impl checks non-empty only            ││
│  │                                     → ui/Signup.tsx:44  · task AC #3 ▸       ││
│  │ ✗  R4 Handle API errors per product UX         unmet    no mapping for 409  ││
│  │       spec: show "email in use" on 409; impl shows generic toast            ││
│  │                                     → ui/api.ts:31  · PRD §4.2 ▸            ││
│  │ ✓  R5 …                                          met                         ││
│  │ ◆  —  Rate-limit middleware added              off-task  not in this task's  ││
│  │       scope; belongs to #98?          → auth/routes.ts:70  [Link to #98]     ││
│  └────────────────────────────────────────────────────────────────────────────┘│
│  Also: ⚠ possible regression in login redirect (#120) · tests cover R1,R2 only  │
│──────────────────────────────────────────────────────────────────────────────────│
│  [ Diff ]  [ Requirements ]  [ Tests ]      per-row: [Accept] [Reject] [Comment]  │
│  Verdict: NEEDS WORK — 1 unmet, 1 partial.   [Request changes ▾] [Approve anyway] │
└────────────────────────────────────────────────────────────────────────────────────┘
```

- **The coverage matrix is the hero pixel.** One row per requirement / acceptance
  criterion, each with a verdict badge (**met · partial · unmet · off-task**, colors per
  §2.1), a one-line reason, and **dual citations**: to the code that implements (or
  fails) it, and to the requirement/AC/source it came from. Click a code citation → the
  Diff tab scrolls to and highlights those lines; click a requirement citation → opens
  the task/PRD snippet.
- **Off-task detection is first-class.** Changes the agent made that no requirement asked
  for get their own `◆ off-task` rows, with a suggested home ("belongs to #98?") and a
  one-click link/move. This is the "it touched 10 files, some of it wasn't the task"
  pain, made visible.
- **Never silently miss; never cry wolf** (the product's make-or-break, from the design
  doc). Low-confidence findings are tinted `--warning` and labelled "possible — please
  check," excluded from any bulk accept. The matrix is a *recommendation the human
  confirms*, row by row — Accept / Reject / Comment per row, consistent with the task
  verdict inbox (§4.3).
- **Three supporting tabs:** **Diff** (requirement-annotated diff — gutter markers show
  which requirement each hunk serves, and unmapped hunks are flagged off-task),
  **Requirements** (the task's requirements/AC with their met/unmet status),
  **Tests** (which requirements have test coverage, which don't).
- **Overall verdict + actions:** a summary verdict (ALL MET / NEEDS WORK / OFF-TASK
  CHANGES) with **Request changes** (sends the unmet/partial rows back to the agent as a
  scoped follow-up run — closes the loop into §4.12) or **Approve** (moves to Delivery,
  §4.14). Per principle #9, AI never approves; the developer does.
- **Task-too-vague path.** If a requirement is too underspecified to validate against,
  the row reads `? unverifiable — requirement ambiguous` with "the agent had to guess:
  <what it assumed>" and a **Clarify** action that writes the answer back into the task
  (feeds stages 3-4). Turning a validation gap into a task-quality fix is a core move.
- **States:** validating (matrix reveals row-by-row, §2.4) · complete · no run yet
  (empty: "Assign to an agent and run this task to review it") · validation failed
  (provider/error — Retry) · huge diff (see §13).
- **Keyboard:** `j/k` move rows, `a` accept row, `r` reject row, `c` comment, `d` jump to
  the diff for the focused row, `Enter` open citation, `⌘↵` request changes.

> **Architecture note:** the **requirement-validation engine** (compare requirement ↔
> implementation ↔ tests, produce per-requirement coverage with citations) is a **new
> reasoning service not in `architecture.md`** — distinct from the conflict/dedup engine.
> It is the single biggest new backend dependency and the thing to de-risk first (design
> doc, "The Assignment"). See §14.

### 4.14 Delivery (PR · CI/CD · deploy) — stage 14

After a review is approved, the change moves through the delivery pipeline, and Nexus
**keeps re-checking the implementation against the task** as CI runs and the PR evolves.

```
┌─ Delivery ──────────────────────────────────────────  [Open] [Merged] [All ▾] ┐
│  #142 Add SSO   PR #318  ▲ open   CI ✓  build ✓  reqs ✓5/7→ now 7/7   [Review ▸]│
│  #98 Rate limit PR #315  ⚠ CI failing (2)   reqs ✓  → fix CI          [Open →] │
│  #71 Billing    PR #310  ✓ merged · deployed prod 12:40   reqs ✓7/7            │
└───────────────────────────────────────────────────────────────────────────────┘
```

**PR detail:**

```
┌─ PR #318 · Add SSO (#142) ───────────────────────────────────────── [Open in GH]┐
│ Commits (3) · Diff (12 files) · Checks: CI ✓ · build ✓ · lint ✓                 │
│ Requirement re-check (live):  7/7 met  ✓  (was 5/7 at review — R3, R4 fixed)     │
│   R3 min-length rule now enforced → ui/Signup.tsx:44 ▸                           │
│   R4 409 → "email in use" now mapped → ui/api.ts:31 ▸                            │
│─────────────────────────────────────────────────────────────────────────────────│
│ Deploy: staging ✓ 13:10 · prod — awaiting approval                              │
│                        [Approve & merge]   [Approve deploy → prod]   [Comment]   │
└───────────────────────────────────────────────────────────────────────────────────┘
```

- **Requirement coverage travels with the PR.** The §4.13 matrix re-runs on each push,
  so "does it still match the task" is answered continuously, not once. Coverage delta is
  shown (5/7 → 7/7) so a reviewer sees requirements getting closed by follow-up commits.
- **Standard PR surface, requirement-anchored:** commits, diff, CI/CD, build, tests,
  deploy status — plus the live requirement re-check no other tool shows.
- **Human is the final approver** (principle #9): Approve & merge and Approve deploy are
  explicit human actions; AI never merges or deploys.
- **States:** no PR yet (review not approved) · PR open (CI running / passing / failing) ·
  requirement regression detected after a push (a met requirement goes unmet → red banner
  + back to Reviews) · merged · deployed · deploy failed (cause + rollback link).
- **Keyboard:** `Enter` open PR, `g h` open in GitHub, `⌘↵` approve focused action
  (with a confirm — merge/deploy are one-way, §7 destructive pattern).

> **Architecture note:** GitHub App (PR create/read, CI/deploy signals) and the
> continuous requirement re-check are **not in `architecture.md`** (it has no GitHub
> integration). New backend + connector work; see §14. Until then, Delivery degrades to
> read-only status from a manually-linked PR.

---

## 5. The universal command bar (⌘K)

One bar, three jobs, disambiguated by intent:

```
┌─ ⌘K ──────────────────────────────────────────────┐
│ > add SSO for enterprise                           │
│ ─────────────────────────────────────────────────  │
│  ➕ Create card “add SSO for enterprise”            │
│  ⌕ Search items & decisions for “SSO”              │
│  💬 Ask: “add SSO for enterprise”                   │
│  ⚙ Go to… Board · Verdicts · Runs · Reviews · Delivery │
└────────────────────────────────────────────────────┘
```

- Type → ranked actions: **Create**, **Search**, **Ask**, **Navigate**. Default
  highlighted action is Create when the text looks like a new item, Ask when it's a
  question (starts with why/what/who/how or ends with "?").
- Recent + suggested when empty. Full keyboard nav. This is the fastest path to the
  magical moment (type an item → instant verdict).

---

## 6. Core user flows

### 6.1 ⭐ The magical moment — paste/add an item, get a cited verdict

The single flow the whole product is judged on.

```
1. User adds a card (n / +Add / ⌘K Create) and types:
      "Add SSO for enterprise clients"
2. On Enter, card lands in Inbox with a quiet  ⟳ checking  chip.
3. Engine runs dedup + conflict retrieval (target < 3s).
4a. NET-NEW  → chip fades, no badge. Calm. (Most common; we don't shout.)
4b. DUPLICATE → ⧉ badge "dup of #88 (91%)"; card offers inline [Merge][Keep].
4c. CONFLICT → ⚑ badge "Conflicts with decision #4 (82%)" with a 240ms reveal;
      clicking opens the Verdict drawer showing the quoted decision + top-3
      candidates + Resolve menu.
5. Nothing auto-applies. The user confirms. An undo toast follows any action.
```

Design guarantees from the product doc:
- **Ranked candidates, human confirms.** Never assert a single answer.
- **Cite the exact match.** Decision shown by ID + quoted snippet; pasted free text by
  source doc + quoted snippet.
- **Never silently miss.** Low confidence still surfaces (as "possible conflict"),
  tinted warning, excluded from bulk-confirm.

### 6.2 Ramp-up flow (new lead joins a messy project)

```
1. Open project → Board shows everything, grouped, with verdict badges already
   computed on the backlog.
2. ⌘K → Ask: "what's the state of auth?" → cited summary + links.
3. Click an item → drawer → History tab → see why each decision was made, cited.
4. Impact view → see what's entangled before touching anything.
Outcome: minutes to context instead of days.
```

### 6.3 Firehose flow (lead under input flood)

```
1. Sources: transcript webhook drops a meeting → 5 items + 2 decisions extracted.
2. Ingest review queue: each extracted item shows its verdict against existing memory.
3. Lead confirms/merges/dismisses in the Verdicts component (ranked, cited).
4. Confirmed items land on the board; decisions enter memory.
5. Author → generate updated BRD for the affected area, cited, conflict-checked.
```

### 6.4 Onboarding (first run) — the guided New Project flow

The first project is a mandatory guided setup (§4.10–4.11), not an empty board. It's
required so the memory layer is seeded before the user ever triages — but background
ingest means it's never dead waiting.

```
1. First run → New Project (full-screen, §4.10). Description *required*;
   Files / Videos / Images + GitHub repo all optional (GitHub skippable).
2. Ingest & continue → sources enter the async pipeline in the background.
3. Clarification chat (§4.11) opens immediately, grounded on the description;
   each source folds in as it finishes.
4. Generate tasks → verdict review queue (§4.6): dedup/conflict-checked, human confirms.
5. Data-mode nudge: "Working with sensitive data? Switch to Bring-your-own-key."
6. Land on Board (confirmed cards) with the magical-moment hint: "Add a card that
   already exists — watch what happens."
```

The old "paste a backlog" affordance folds into the Description textarea or a dropped
`.txt`/`.csv` file (smart-split still applies) — no separate paste step.

### 6.5 ⭐ The second magical moment — did the agent build what was asked?

The flow the *new* product is judged on. Where §6.1 proves the board is smart, this
proves the whole thesis: AI wrote the code fast, and Nexus tells you in seconds whether
it actually matches the task — the verification work that AI made *more* expensive.

```
1. A task assigned to Claude Code finishes its run (§4.12). The card flips to
      ✓ done · review ready, and the Reviews bell increments.
2. Open the Review (§4.13). The coverage matrix reveals row-by-row (240ms):
      each requirement / acceptance criterion gets a met · partial · unmet · off-task
      verdict, cited to both the code and the requirement.
3. The "holy shit": the diff passed tests and looked fine, but the matrix shows
      R4 "handle API errors per product UX" is UNMET (409 not mapped), and a
      rate-limit change is OFF-TASK. The exact thing that reached production in
      A.K.'s story, caught before merge, in seconds instead of a half-day.
4. Human confirms row by row (Accept/Reject/Comment). Nothing auto-applies.
5. Request changes → the unmet/partial rows become a scoped follow-up run (§4.12).
      The loop repeats until the matrix is green, then Approve → Delivery (§4.14).
```

Design guarantees (from the design doc, mirroring §6.1's for the board):
- **Per-requirement, ranked, human confirms.** Never a single "looks good / looks bad."
- **Dual citations.** Every row points to the code that implements/fails it AND the
  requirement/AC/source it came from.
- **Never silently miss.** Low-confidence findings surface as "possible — please check,"
  tinted warning, excluded from bulk accept. A miss here is worse than a false alarm,
  because the whole product is "you can trust the check."
- **Vague requirement ⇒ visible, not skipped.** An unverifiable requirement is shown as
  such with what the agent assumed, and offers Clarify (feeds stages 3-4).

### 6.6 End-to-end flow (assign → execute → review → ship)

```
1. Board: a task exists with requirements + acceptance criteria (authored in stages 3-4,
   or written by hand). Assign it to Claude Code.
2. Runs (§4.12): agent executes live; AC tracker fills in; agent pauses to ask on
   ambiguity; human answers inline.
3. Reviews (§4.13): requirement coverage matrix. Human accepts/rejects rows;
   Request changes loops back to a scoped run.
4. Delivery (§4.14): approved change → PR; CI/build/tests run; requirement coverage
   re-checks on every push; human approves merge, then deploy.
5. Trace (§4.5): the finished chain — source → requirement → task → run → code → PR →
   deploy — is now walkable for anyone asking "why does this exist?"
Outcome: AI does the building; the human's time goes to judgment (answering the agent,
confirming coverage, approving ship), not to reconstructing what the agent did.
```

---

## 7. States (apply to every screen)

| State | Treatment |
|-------|-----------|
| **Empty (first run)** | First run is the **New Project takeover** (§4.10), not an empty board — headline + required description + optional source zones. It carries its own sub-states: uploading (per-file parse status), description-only (no sources), and the chat's AI-working + background-ingest states (§4.11). Steady-state empty views (e.g. a filtered board with no cards) still use a centered illustration-light block: one headline (`display`), one sentence, 1–2 CTAs. Never a blank screen. |
| **Empty (cleared)** | Quiet single line + relevant action ("All clear. New flags show up here."). |
| **Loading** | Skeletons that match final layout (cards, rows, graph nodes). Shimmer 1.2s. No spinners for content; spinners only for in-place actions <1s. |
| **AI working** | Inline status text with animated ellipsis: "Searching memory…", "Checking against decisions…". Cancelable where it takes >2s. |
| **Error** | Inline, not modal. Problem + cause + fix + retry. e.g. "Couldn't reach the AI provider (key invalid). Update key in Settings ▸ Data & AI. [Retry]". |
| **Low confidence** | Warning tint + "Please review" label; excluded from bulk actions. |
| **Offline** | Top-bar banner "Offline — changes saved locally, will sync." Board stays editable; AI features disabled with explanation. |
| **No results (search/filter)** | "No matches — Clear filters / Broaden search." |
| **Agent running** | Live activity stream + AC tracker filling in; progress bar; Stop always visible. No stuck spinner — stalled run shows "no activity for Ns — still working / check run?" |
| **Agent blocked** | Warning tint; the agent's question surfaced with an inline answer box; `⚠ blocked` chip on the board card and Runs row. |
| **Agent failed** | Inline cause (provider outage / tool error) + Retry + Hand to human. Work-in-progress preserved, never discarded silently. |
| **Review validating** | Coverage matrix skeleton, then row-by-row reveal (§2.4). "Checking each requirement against the code…" |
| **Requirement regression** | A previously-met requirement goes unmet after a push: red banner on Delivery + item returns to Reviews; never silently downgraded. |
| **Review — nothing to check** | Task never ran: "Assign to an agent and run this task to review it." Not an error. |

---

## 8. Component library (build inventory)

Reusable components the developer implements once:

- **Card** (board): id, title, verdict badge, meta row, drag handle, selection, hover,
  inline-edit, checking state.
- **VerdictBadge**: variants net-new (hidden by default) / duplicate / conflict /
  impact / checking / low-confidence. Always icon + label + color.
- **VerdictRow**: new-item ⇄ candidate(s), confidence, expandable top-3, action buttons.
  Reused in Verdicts inbox and Sources review queue.
- **CitationChip**: type (decision/item/source) + label; hover preview popover; click to
  open. Used in Ask, Author, Card drawer, Impact.
- **Drawer**: right-side, resizable, tabbed, stackable (max 1 level), Esc to close.
- **CommandBar (⌘K)**: intent-ranked action list.
- **InlineEditField**: text/select/tag, click-to-edit, Enter/Esc, optimistic save.
- **AssigneeSelect**: searchable combobox grouped into **People** and **AI Agents**,
  keyboard nav, inline "+ Add person" / "+ Add custom agent". Pairs with the **agent badge**
  variant (kind icon + name + tint, §2.4) reused on the board card and drawer.
- **TagChip / EntityTag**: removable, color-coded by entity optional.
- **FilterBar**: chips + add-filter popover.
- **Toast**: success/undo/error, 6s, action button, stack bottom-left.
- **GraphCanvas**: nodes/edges, zoom/pan, cluster-collapse, focus/dim.
- **MessageThread**: streaming answer + citations + follow-ups (Ask).
- **Skeletons**: card, row, graph, message.
- **Buttons**: primary (accent), secondary (border), ghost, danger (verdict-conflict
  red, used only for destructive confirm). Sizes sm(28h)/md(32h).
- **EmptyState**: icon, headline, body, CTA(s).

New for the build/verify half of the lifecycle:

- **RunStatusChip**: compact status on a board card / Runs row — `⚙ running` (+ %) /
  `✓ N/M met` / `⚑ needs review` / `⚠ blocked` / `⚠ failed`. Color per §2.1 run/req tokens.
- **AgentActivityStream**: live, append-only log of agent events (read/edit/run/note/
  block), streamed over websocket; virtualized for long runs; each row links to the file
  or command. Used in Run detail (§4.12) and the card Run tab.
- **AcceptanceCriteriaTracker**: per-AC ✓/⟳/–/⚠ list that fills in during a run; reused
  in Run detail and as the Review tab's summary.
- **RequirementCoverageMatrix** *(the review hero)*: one row per requirement/AC with a
  coverage badge (met/partial/unmet/off-task), reason, dual citations (code + requirement),
  and per-row Accept/Reject/Comment. Row-by-row reveal on validate. Reused in the Reviews
  queue (collapsed) and Review drawer/page (expanded).
- **ReqCoverageBadge**: met/partial/unmet/off-task/unverifiable + low-confidence variant.
  Always icon + label + color (§11). The verify-side sibling of **VerdictBadge**.
- **AnnotatedDiffViewer**: file diff with a requirement gutter — each hunk marked with the
  requirement it serves; unmapped hunks flagged `off-task`. Keyboard-navigable by hunk.
  Reused in Review (Diff tab) and PR detail.
- **PRStatusPanel**: commits, checks (CI/build/lint), deploy status, and the live
  requirement re-check with coverage delta. Used in Delivery (§4.14).
- **RunControls**: Stop / Hand to human / Answer & continue, with the destructive-confirm
  pattern on Stop when work would be lost.

Every interactive component ships: default, hover, focus-visible (2px accent ring),
active, disabled, loading states.

---

## 9. Keyboard model

| Key | Action | Scope |
|-----|--------|-------|
| `⌘K` | Command bar (create/search/ask/nav) | global |
| `n` / `N` | New card (focused column / inbox) | board |
| `Enter` | Open focused card / commit edit | board |
| `e` | Edit title inline | board/card |
| `←/→` | Move card across columns | board |
| `↑/↓` | Reorder / navigate cards | board |
| `x` | Select card (multi with shift) | board |
| `/` | Focus filter | board/lists |
| `c` | Confirm focused verdict / comment on focused review row | verdicts / review |
| `d` | Dismiss focused verdict / jump to diff for focused row | verdicts / review |
| `a` / `r` | Accept / Reject focused requirement row | review |
| `⌘/Ctrl+Enter` | Request changes (review) / approve focused action (delivery) | review / delivery |
| `s` | Stop focused run | runs |
| `g` then `b/v/u/e/y/m/t/a/o` | Go to Board/Verdicts/rUns/rEviews/deliverY/Memory/Trace/Author/sOurces | global |
| `?` | Keyboard help overlay | global |
| `⌘/Ctrl+Enter` | Ingest & continue (submit setup) | new project |
| `Enter` / `Shift+Enter` | Send answer / newline | clarification chat |
| `Esc` | Close drawer/popover/edit | global |

A discoverable `?` overlay lists all shortcuts. Nothing is keyboard-only.

---

## 10. Responsive behavior

Primary target is desktop (this is a work tool), but it must not break on smaller
widths.

- **≥1280px:** full layout, left nav expanded, drawer 480–640px.
- **1024–1279px:** left nav auto-collapses to icons; drawer 420px.
- **768–1023px (tablet):** nav hidden behind a toggle; board horizontally scrolls
  columns; drawer becomes a full-height sheet 90% width.
- **<768px (phone, read/triage only):** board becomes a single-column list grouped by
  status (swipe between groups); Verdicts and Ask are first-class (a lead triaging on
  the go); authoring/impact are view-only with "open on desktop" hint. Add-card still
  works.
- Touch: drag uses a long-press handle; all hover-only affordances get a tap equivalent.
- **New Project (§4.10) & Clarification chat (§4.11):** ≥1024px a centered column
  (~640px). Tablet/phone: single column, the three source rows stack full-width, GitHub
  field full-width. The chat becomes a full-height sheet with the composer pinned to the
  bottom and the background-ingest indicator in the header. These screens are usable on
  phone (unlike authoring/impact) — a lead can kick off a project on the go.
- **Runs / Review / Delivery (§4.12–4.14):** desktop-primary (code diffs and the coverage
  matrix need width). ≥1280px the matrix and diff sit side by side; 1024–1279px they
  stack (matrix first, diff below). Tablet: Runs and the Review coverage matrix are
  readable and confirmable (Accept/Reject rows work), but the annotated diff is view-only
  with an "open on desktop to review code" hint. Phone: Runs status and the Reviews queue
  are triage-only (see coverage summary, approve/request-changes at the task level);
  per-line diff review is desktop. A lead can unblock an agent's question (§4.12) from a
  phone — that path is first-class on mobile, like Verdicts.

## 11. Accessibility (WCAG 2.1 AA, non-negotiable)

- **Never color-only.** Every verdict = color + icon + text label. Confirmed in §2.1.
- **Contrast:** body text ≥ 4.5:1, large/UI ≥ 3:1 in both themes. Verdict pairs above
  are chosen to pass on their tinted backgrounds.
- **Focus:** visible 2px accent ring on every focusable element; logical tab order;
  focus trapped in drawers/modals, restored on close.
- **Keyboard:** every action reachable without a mouse (see §9). Drag-and-drop has a
  keyboard equivalent (←/→/↑/↓).
- **Screen readers:** semantic landmarks (nav/main/complementary); board is an ARIA
  list/listitem with `aria-grabbed` on drag; verdict badges have descriptive
  `aria-label` ("Conflicts with decision 4, 82% confidence, needs review"); live region
  announces verdict results and toasts.
- **Motion:** honor `prefers-reduced-motion` (no transforms, opacity only).
- **Text:** supports 200% zoom and OS font scaling without clipping; no text in images.
- **Forms:** labels tied to inputs; errors announced and tied via `aria-describedby`.
- **New Project & chat (§4.10–4.11):** each source zone is a keyboard-operable control
  with a visible `browse` button and a screen-reader label ("Upload files: documents and
  PDFs" / "…videos: meeting and client calls" / "…images: whiteboards and diagrams");
  never a drop-only zone. The description is `aria-required`; the disabled `Ingest &
  continue` CTA explains why ("Add a description to continue"). Per-file parse status is
  announced via a live region; the chat transcript is an `aria-live` log so new AI
  messages are read out.
- **Runs / Review / Delivery (§4.12–4.14):** the requirement-coverage verdict is never
  color-only — icon + label ("R4 unmet") + color, with an `aria-label` carrying the full
  finding ("Requirement 4, handle API errors, not met, cited to ui/api.ts line 31").
  The agent activity stream and the coverage-matrix reveal are `aria-live` regions
  (activity = polite, a new blocking question = assertive). The annotated diff is
  keyboard-navigable by hunk with per-hunk requirement labels exposed to screen readers;
  it is not the only way to act — Accept/Reject/Comment work from the matrix rows without
  entering the diff. Merge/deploy confirmations are reachable and clearly labelled as
  one-way actions.

## 12. Microcopy & verdict language

Tone: plain, direct, confident-but-honest. No jargon, no hype.

| Situation | Copy |
|-----------|------|
| Net-new | (silent — no badge) |
| Duplicate | "Looks like a duplicate of #88" |
| Conflict | "Conflicts with decision #4" + quoted decision |
| Impact | "Touches the same area as #71, #120" |
| Low confidence | "Possible conflict — worth a look" |
| No match | "Net-new — nothing like this yet" |
| AI working | "Checking against past decisions…" |
| Provider error | "Couldn't reach the AI provider. Check your key in Settings ▸ Data & AI." |
| Author w/ open conflict | "Heads up: this scope has an unresolved conflict (#142 ⇄ #4). Resolve it first?" |
| Undo | "Merged #95 into #88. Undo" |
| New project headline | "Start a new project" |
| New project subhead | "Drop in what you already have. We'll read it and ask a few questions before building your board." |
| Files zone hint | "Files — docs, PDFs, specs, CSVs" |
| Videos zone hint | "Videos — meeting & client calls" |
| Images zone hint | "Images — whiteboards, diagrams" |
| Description required | "Add a description to continue" (on the disabled CTA) |
| GitHub helper | "We'll scan existing code and track progress here once connected." |
| GitHub invalid | "That doesn't look like a repo URL" |
| Ingest in progress | "Reading your sources…" |
| Chat intro | "I've read your sources. A couple of quick questions before I build the board." |
| Generate tasks | "Generate tasks" |
| Source parse failed | "Couldn't read call-0530.mp4 — continue without it?" |
| Agent running | "Claude Code is working — 12 files, 4 commands so far" |
| Agent blocked | "Claude Code needs a decision before it continues" |
| Agent asks | "AC5 says lock after 5 tries — per-account or per-IP?" |
| Run failed | "The agent run failed (provider error). Retry, or hand to a human?" |
| Requirement met | "Met — cited to ui/Signup.tsx:1" |
| Requirement partial | "Partially met — spec asked for 8+ chars, impl checks non-empty" |
| Requirement unmet | "Not implemented — no 409 handling for 'email in use'" |
| Off-task change | "Off-task — this wasn't in the task. Belongs to #98?" |
| Unverifiable req | "Can't verify — requirement is ambiguous. The agent assumed X. Clarify?" |
| Review summary | "5 of 7 requirements met · 1 unmet · 1 off-task" |
| Requirement regression | "Heads up: R3 was met at review but is unmet after the last push" |
| Approve gate | "You're the final say — approve to merge, or request changes" |

Never claim certainty the system doesn't have ("Definitely a duplicate" ✗ →
"Looks like a duplicate" ✓; "The code is correct" ✗ → "R4 looks unmet — please check" ✓).
The product's credibility is built on honest hedging + citations, on both the task
verdict and the requirement-coverage verdict.

---

## 13. Edge cases the developer must handle

- **Verdict check fails/times out:** card keeps a retry affordance, not a stuck spinner;
  item still lands ("couldn't check yet — retry").
- **Huge paste (hundreds of rows):** chunk the import, show progress, dedupe within the
  paste itself before checking against the backlog.
- **Conflicting verdicts on the same item over time** (memory changed): re-check on
  demand; History tab shows verdict evolution.
- **Superseding a decision:** confirm dialog explains the ripple (what re-opens), since
  it rewrites memory.
- **Empty memory:** every new item is net-new; explain that conflict-detection gets
  useful as history accumulates (ties to the "minimum history" open question).
- **Citation target deleted/archived:** chip shows "source archived" but keeps the
  snippet.
- **Multi-tenant / BYO-key off vs on:** AI-dependent UI (Ask, verdicts, author) must
  degrade gracefully with a clear reason when no provider is configured.
- **Long titles / RTL / non-Latin text:** truncate with tooltip; layout must not break.
- **Agent run crashes / provider outage mid-run:** preserve work-in-progress, mark
  `failed` with cause, offer Retry and Hand to human; never lose the activity log.
- **Agent edits far more than the task (huge/scattered diff):** the review still maps
  hunks to requirements; unmapped hunks pile into `off-task` with a count ("14 off-task
  changes across 6 files") so the human isn't drowned. Diff virtualized for large changes.
- **Requirement too vague to validate:** row = `unverifiable`, show the agent's assumption,
  offer Clarify (writes back to the task). Never silently score it met or unmet.
- **Agent's self-assessment disagrees with the validation:** show both ("agent says done;
  validation finds R4 unmet"). The independent check wins the display; the agent's claim is
  labelled as a claim.
- **Validation on a task with no acceptance criteria:** fall back to validating against
  the description + PRD citations, and flag "no acceptance criteria — coverage is
  best-effort; add AC for a reliable check."
- **Requirement regression after a green review:** a met requirement flips unmet on a later
  push → item returns to Reviews, red banner on the PR, never a silent downgrade.
- **PR merged outside Nexus / edited on GitHub:** reconcile on next sync; if the merged
  code diverges from the approved review, flag "shipped code differs from what was
  reviewed."
- **BYO-key off for execution/validation:** the run and review features degrade with a
  clear reason (same pattern as Ask/verdicts) when no provider is configured.

---

## 14. Build handoff notes

- **Stack fit (from architecture.md):** React/TypeScript SPA; websocket for live verdict
  AND live agent-run results pushed to cards; optimistic UI on edits with server
  reconciliation.
- **Architecture gap (read this first).** `architecture.md` currently specs only the
  plan/memory half (stages 1-11: surface, ingestion, conflict/dedup engine, memory,
  reasoning services). The build/verify half this spec adds needs **new backend not yet
  designed**:
  - **Agent execution / runner** (stage 12): running Claude Code against a repo, sandbox,
    streaming activity, blocking-question round-trips.
  - **Requirement-validation engine** (stage 13): a NEW reasoning service, distinct from
    the conflict/dedup engine — compare requirement ↔ implementation ↔ tests → per-
    requirement coverage with dual citations. This is the biggest new dependency.
  - **GitHub App + delivery signals** (stage 14): PR create/read, CI/build/deploy status,
    continuous requirement re-check.
  `architecture.md` must be extended before 12-14 are buildable; until then those screens
  are UI-ahead-of-backend and should be built against mocks.
- **Recommended v1 (from the design doc, verification-first / Approach A).** Even though
  this spec covers all 15 stages A-to-Z, the design doc recommends *entering* at
  verification. The smallest shippable, demoable slice is:
  **AnnotatedDiffViewer + RequirementCoverageMatrix + Reviews queue** (§4.13) pointed at a
  real PR + its task, powered by the requirement-validation engine. That single screen is
  the wedge; the board/plan half and the delivery half can follow. De-risk the engine
  (recall vs false-positive on real PRs) before building the rest — see the design doc's
  "The Assignment."
- **Component order to build (full platform):** Card + Board → InlineEdit + Add flow →
  VerdictBadge + checking state → VerdictRow + Verdicts inbox → CommandBar → Drawer + Card
  detail → CitationChip + Ask → **RequirementCoverageMatrix + AnnotatedDiffViewer + Reviews
  queue (the wedge — build early)** → AgentActivityStream + AcceptanceCriteriaTracker + Runs
  → PRStatusPanel + Delivery → Sources/ingest review → Trace graph → Author → Deprecate →
  Settings/data mode/agents.
- **The non-negotiables to get right first:** (1) the **requirement-coverage matrix**
  (per-requirement, cited, ranked, human-confirmed, never silently wrong) — this is the
  new product; (2) 1-second add on the board; (3) the task-verdict reveal + ranked-
  candidate confirm; (4) citations everywhere, on both verdict families. Everything else
  is supporting cast.
- **Design tokens** in §2 should be implemented as CSS variables / a theme file so light
  and dark ship together from day one.

---

## What this spec deliberately leaves out (defer)

- Full visual brand (logo, marketing site) — separate from the app design system.
- Native mobile apps — responsive web first; phone is triage-only (unblock-an-agent and
  approve/request-changes are the first-class mobile paths).
- Real-time multiplayer cursors/presence — later; start with live verdicts + live runs +
  last-write reconciliation.
- Theming beyond light/dark.
- The spreadsheet add-on's inline UI (lives in Google/Microsoft chrome) — a separate
  surface spec when that connector is built.
- **Real third-party agent integrations beyond Claude Code** (Figma, Copilot, Cursor) and
  **multi-agent orchestration** (coordinating several agents across one feature) — MVP is
  Claude Code, single-agent-per-task. The orchestration ambition (stages 6-7) is the most
  crowded, best-funded battleground; defer until there's a named edge.
- Video/audio transcription provider specifics — the UI shows `⟳ transcribing` and folds
  results into the chat as they land; the provider itself is an architecture concern.

**In scope here but pending architecture work** (UI specced, backend not yet in
`architecture.md` — build against mocks until §14's gaps are closed):

- **Agent execution / runner** for Claude Code (stage 12, §4.12).
- **Requirement-validation engine** (stage 13, §4.13) — the new reasoning service and the
  thing to de-risk first.
- **GitHub App: PR create/read, CI/build/deploy signals, continuous requirement re-check**
  (stage 14, §4.14), and **repo scanning to seed tasks** (stages 1-2 from a connected
  repo). New Project (§4.10) still only *captures and validates* the repo URL today.
