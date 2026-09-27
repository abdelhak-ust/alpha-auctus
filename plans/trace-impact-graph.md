---
feature: Trace impact graph
phase: -
status: done
created: 2026-09-27
completed: 2026-09-27
note: built and verified — live Trace graph from board/features/decisions; POST /api/projects/{projectId}/impact/explain via get_chat_model(); fake-model tests cover neighbor cite, stay-silent, fabricated Dec #4 drop, Vertex missing; client builder tests cover same-area edges, duplicate verdict, empty project.
---

# Live Trace / impact graph

Replace the hardcoded Trace demo (SSO/CSV nodes and canned explanations) with a live graph from the project's board cards, areas, decisions, features/tasks, and verdicts. Clicking a node fills Selected Impact Explanation from real neighbors; Explain calls Vertex on that subgraph.

## Spec grounding

Quoted — do not invent product behavior.

**Trace** ([ui_ux_design.md](../ui_ux_design.md) §4.5):

> Graph-first, explanation second. Pick an item/decision to trace. Click a node to recenter; hover highlights the neighborhood. “Explain” turns the selected subgraph into a cited natural-language summary.

**Architecture** ([architecture.md](../architecture.md) L266–268):

> Impact analysis (5): given a change, traverse `affects` / `depends_on` Edges from the touched Entities → list affected Items. Graph traversal first, LLM to explain second.

**This slice:** plan-side graph only (items, areas, decisions, sources/features). No stage-15 Run → PR → Deploy. No persisted `Edge` table (MVP has none).

## Why it is dead

[`ImpactGraph.tsx`](../client/src/components/ImpactGraph.tsx) hardcodes `#142` / Dec `#4` / CSV nodes and `getExplanation()` copy. `state` from `useProject()` is unused. Clicking an item calls `setSelectedCardId` for fake ids. **Explain this impact** is `alert(...)`.

## Placement

Keep the existing Trace view (`activeView === 'impact'`). Derive the graph on the client from data we already have. One new FastAPI explain route (same pattern as Memory Ask). Do not invent Qdrant or Decision Records beyond SQLite `state.decisions`.

```mermaid
flowchart LR
  nav[Sidebar Trace] --> graph[ImpactGraph]
  items[Board items] --> build[lib/impactGraph]
  feats[Features and tasks] --> build
  decs[SQLite decisions] --> build
  verdicts[Item verdicts] --> build
  build --> canvas[SVG nodes and edges]
  click[Click node] --> panel[Selected Impact Explanation]
  explain[Explain this impact] --> api["POST /impact/explain"]
  api --> panel
```

## Impact analysis

- [`client/src/components/ImpactGraph.tsx`](../client/src/components/ImpactGraph.tsx) — replace `baseNodes` / `baseEdges` / canned `getExplanation`. Keep zoom, search, hover-dim, layout chrome.
- New [`client/src/lib/impactGraph.ts`](../client/src/lib/impactGraph.ts) — build + layout (unit-testable).
- [`client/src/lib/backend.ts`](../client/src/lib/backend.ts) — `explainImpact(...)`.
- [`client/src/types.ts`](../client/src/types.ts) — `ImpactNode` / `ImpactEdge` / `ImpactExplainResponse` if the API needs them.
- Backend: `IMPACT_EXPLAIN` in [`prompts.py`](../backend/app/agents/prompts.py), `backend/app/agents/impact.py`, route on [`mvp.py`](../backend/app/api/routes/mvp.py).
- **Side effect:** none for Memory/Ask/Board except item-node click should open the **real** card drawer (by board id), not fake `#142`.

## Implementation

### 1. Derive the graph (client)

From `state.items`, `state.decisions`, `features`:

**Nodes**

- `item` — each board card (`id: item-{n}`)
- `area` — distinct `item.area` / task.area (`id: area-{slug}`)
- `decision` — SQLite decisions if any (`id: decision-{n}`)
- `source` — each feature (spec: source nodes). Label = feature name; id = `feature-{uuid}`

**Edges** (typed, labeled)

- item → area: `depends-on` (card’s area)
- feature → item: `affects` when a task has `boardItemId`
- feature → unpublished task: skip a second node type; fold draft/approved tasks as `item` nodes with id `task-{uuid}` (no drawer) so unpublished work still shows
- item → item: `duplicate` / `contradicts` / `affects` from `item.verdict.candidates` (`duplicate` / `conflict` / `impact`)
- decision → area or item only when a verdict citation `type === 'decision'` actually matches a decision id — **never invent** Dec #4

**Layout:** layered columns (sources | areas | items/decisions), simple vertical stack, not hardcoded demo coordinates. If more than ~40 nodes, collapse extra items under their area with a “+N” count (spec). Empty project: one-line empty state, no demo graph.

Search filters nodes as today. Hover still dims non-neighbors.

### 2. Selection + panel (no LLM yet)

On click: set `selectedNodeId`. Panel **immediately** shows:

- Node title + type
- Degree: “touches N items, M features…” from real edges
- Neighbor list with edge labels
- If an item has a verdict, the existing `verdict.message` + citation snippet

Single-click does **not** open the drawer. Item nodes: optional “Open card” or double-click → `setSelectedCardId(realId)`.

Drop the hardcoded Interactive Tips / fake default `node-120`.

### 3. Explain (LLM)

`POST /api/projects/{projectId}/impact/explain`

Body: `nodeId`, `node` snapshot, `neighbors[]` (id, type, label, edgeType), optional verdict snippet. No full-project dump.

Response: `{ headline, text, citations: AskCitation[] }` (reuse citation chips).

`IMPACT_EXPLAIN`: only from the supplied subgraph; cite or stay silent; never invent decisions. `get_chat_model()` only. Empty Vertex → structured 4xx; button toasts and leaves the derived panel text in place.

**Explain this impact** calls this; show “thinking…” on the panel. Do not `alert`.

### 4. Out of scope

- Persisted Edge table / Qdrant
- Stage 15 delivery chain
- Replacing the SVG with a new graph library
- Changing Memory Ask or verdict check

## Verification

- `npx tsc --noEmit && npm test` — graph builder: two cards same area → area node + two depends-on edges; verdict duplicate → duplicate edge; empty items → no demo SSO nodes.
- `poetry run pytest && poetry run ruff check .` — fake explain cites a neighbor; unknown subgraph stays silent; Vertex missing 4xx; Memory/Ask tests still pass.
- Browser: Trace shows this project’s cards/features; click a node → right panel updates; Explain returns a cited summary; item double-click opens the real drawer. If the browser tab drops, assert the builder + route and say what was not clicked.

---

**Completed 2026-09-27.** Trace derives a live graph from board cards, areas, features/tasks, and SQLite decisions; Explain cites only the selected subgraph via `get_chat_model()`. See [IMPLEMENTATION_LOG.md](../IMPLEMENTATION_LOG.md) 2026-09-27 — Live Trace / impact graph.
