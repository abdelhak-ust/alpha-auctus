// Deterministic derivation of the BUILD → VERIFY → DELIVER lifecycle (spec
// §4.12–4.14) from the board's items. There is no backend for these stages yet
// (ui_ux_design.md §14 flags them as UI-ahead-of-architecture), so we synthesise
// stable, plausible runs / reviews / deliveries seeded off each item's id. The
// output is fully deterministic — no flicker across re-renders — and grounded in
// the actual cards on the board, so the screens are never empty theatre.

import {
  Item, Agent, Run, Review, Delivery, RunActivity, RunFile,
  AcceptanceCriterion, RequirementCoverage, CoverageState, ReviewVerdict, ACState
} from '../types.js';
import { resolveAssignee } from './assignee.js';

// The MVP runner. Everything else in the catalog is assignment-only (spec §4.9).
const DEFAULT_AGENT = { name: 'Claude Code', kind: 'code' as const };

/** Tiny deterministic PRNG (mulberry32) so a given item always yields the same run. */
function seeded(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function pick<T>(rng: () => number, arr: T[]): T {
  return arr[Math.floor(rng() * arr.length) % arr.length];
}

// Requirement pool — generic enough to read plausibly for any card, anchored on
// the item's own title as the first requirement.
const REQ_POOL = [
  'Connect to the existing API surface',
  'Validate required input fields',
  'Handle API errors per product UX',
  'Persist state across reloads',
  'Responsive layout down to mobile',
  'Emit an audit event on the action',
  'Guard the flow behind auth',
  'Cover the happy path with tests',
];

const UNMET_REASON = [
  'spec: show "email in use" on 409; impl shows a generic toast',
  'spec required a retry with backoff; not implemented',
  'no mapping for the 409 / conflict case',
];
const PARTIAL_REASON = [
  'spec said 8+ chars with 1 number; impl checks non-empty only',
  'covers the desktop breakpoint but not < 480px',
  'validates on submit but not on blur as the AC asks',
];
const OFFTASK = [
  'Rate-limit middleware added',
  'Refactored the logger utility',
  'Bumped an unrelated dependency',
];

function agentFor(item: Item, agents: Agent[]) {
  const a = resolveAssignee(item.assignee, agents);
  if (a.kind === 'agent' && a.agent) return { name: a.agent.name, kind: a.agent.kind };
  return DEFAULT_AGENT;
}

function fileNames(rng: () => number, n: number): RunFile[] {
  const bases = ['auth/routes.ts', 'ui/Signup.tsx', 'ui/api.ts', 'auth/session.ts', 'lib/validate.ts', 'ui/Form.tsx', 'server/handlers.ts'];
  const out: RunFile[] = [];
  for (let i = 0; i < n; i++) {
    out.push({
      path: bases[i % bases.length],
      change: i === 0 ? 'M' : rng() > 0.6 ? 'A' : 'M',
      added: 8 + Math.floor(rng() * 120),
      removed: Math.floor(rng() * 20),
    });
  }
  return out;
}

/** Items whose lifecycle has actually started — assigned to an agent, or moving. */
function isAgentWork(item: Item, agents: Agent[]): boolean {
  const a = resolveAssignee(item.assignee, agents);
  return a.kind === 'agent' || item.status === 'in_progress' || item.status === 'done';
}

export function buildRuns(items: Item[], agents: Agent[]): Run[] {
  return items
    .filter(i => isAgentWork(i, agents) && i.status !== 'inbox')
    .map(item => {
      const rng = seeded(item.id * 2654435761);
      const agent = agentFor(item, agents);
      const status: Run['status'] =
        item.status === 'done' ? 'done'
        : item.status === 'next' ? 'queued'
        : rng() > 0.72 ? 'blocked' : 'running';

      const progress = status === 'done' ? 100 : status === 'queued' ? 0 : status === 'blocked' ? 45 + Math.floor(rng() * 25) : 40 + Math.floor(rng() * 50);
      const acCount = 3 + Math.floor(rng() * 3);
      const criteria: AcceptanceCriterion[] = Array.from({ length: acCount }).map((_, i) => {
        let s: ACState;
        if (status === 'done') s = 'done';
        else if (status === 'queued') s = 'not_started';
        else if (i < acCount - 2) s = 'done';
        else if (i === acCount - 1 && status === 'blocked') s = 'blocked';
        else s = i === acCount - 2 ? 'in_progress' : 'not_started';
        return { id: `AC${i + 1}`, label: i === 0 ? item.title : pick(rng, REQ_POOL), state: s };
      });

      const files = fileNames(rng, status === 'queued' ? 0 : 3 + Math.floor(rng() * 6));
      const activity: RunActivity[] = status === 'queued' ? [] : [
        { time: '14:02', kind: 'read', text: `read ${files[0]?.path ?? 'auth/session.ts'}` },
        { time: '14:03', kind: 'edit', text: `edit ${files[1]?.path ?? 'auth/routes.ts'} (+${files[1]?.added ?? 48} −${files[1]?.removed ?? 6})` },
        { time: '14:05', kind: 'run', text: 'run `npm test` → 41 pass, 0 fail' },
        { time: '14:06', kind: 'note', text: 'validating field rules against AC #3' },
      ];
      const blockingQuestion = status === 'blocked'
        ? 'AC5 says "lock after 5 tries" — is that per-account or per-IP?'
        : undefined;
      if (blockingQuestion) activity.push({ time: '14:07', kind: 'blocked', text: blockingQuestion });

      return {
        id: `run-${item.id}`,
        itemId: item.id,
        itemTitle: item.title,
        agentName: agent.name,
        agentKind: agent.kind,
        status,
        progress,
        commands: status === 'queued' ? 0 : 2 + Math.floor(rng() * 5),
        activity,
        files,
        criteria,
        selfAssessment: status === 'done'
          ? 'All acceptance criteria addressed; ready for review.'
          : status === 'blocked'
          ? 'Signup UI + API wired; AC5 pending your answer.'
          : 'Implementation in progress; core path wired.',
        blockingQuestion,
      };
    });
}

function coverageFor(item: Item, agents: Agent[]): { coverage: RequirementCoverage[]; overall: ReviewVerdict } {
  const rng = seeded(item.id * 40503 + 7);
  const done = item.status === 'done';
  const reqCount = 4 + Math.floor(rng() * 3);
  const coverage: RequirementCoverage[] = [];

  for (let i = 0; i < reqCount; i++) {
    let state: CoverageState;
    if (i === 0) state = 'met';
    else if (done) state = rng() > 0.82 ? 'partial' : 'met';
    else state = rng() > 0.75 ? 'unmet' : rng() > 0.55 ? 'partial' : 'met';

    const codeFiles = ['ui/Signup.tsx', 'ui/api.ts', 'auth/routes.ts', 'lib/validate.ts'];
    coverage.push({
      id: `R${i + 1}`,
      requirement: i === 0 ? item.title : pick(rng, REQ_POOL),
      state,
      reason: state === 'unmet' ? pick(rng, UNMET_REASON) : state === 'partial' ? pick(rng, PARTIAL_REASON) : undefined,
      codeCitation: { file: codeFiles[i % codeFiles.length], line: 12 + Math.floor(rng() * 60) },
      reqCitation: state === 'unmet' ? 'PRD §4.2' : state === 'partial' ? `task AC #${i + 1}` : undefined,
      lowConfidence: state !== 'met' && rng() > 0.75,
      tested: i < 2,
    });
  }

  // Occasionally the agent did something nobody asked for (off-task, spec §4.13).
  if (rng() > 0.5) {
    coverage.push({
      id: '—',
      requirement: pick(rng, OFFTASK),
      state: 'off-task',
      reason: "not in this task's scope",
      codeCitation: { file: 'auth/routes.ts', line: 70 },
      suggestedHome: '#98',
    });
  }

  const met = coverage.filter(c => c.state === 'met').length;
  const unmet = coverage.filter(c => c.state === 'unmet').length;
  const off = coverage.filter(c => c.state === 'off-task').length;
  const overall: ReviewVerdict = unmet > 0 ? 'needs-work' : off > 0 && met === 0 ? 'off-task' : coverage.every(c => c.state === 'met' || c.state === 'off-task') && unmet === 0 && coverage.filter(c => c.state === 'partial').length === 0 ? 'all-met' : 'needs-work';
  return { coverage, overall };
}

export function buildReviews(items: Item[], agents: Agent[]): Review[] {
  return items
    .filter(i => i.status === 'done' && isAgentWork(i, agents))
    .map(item => {
      const agent = agentFor(item, agents);
      const { coverage, overall } = coverageFor(item, agents);
      const req = coverage.filter(c => c.state !== 'off-task');
      return {
        id: `rev-${item.id}`,
        itemId: item.id,
        itemTitle: item.title,
        agentName: agent.name,
        agentKind: agent.kind,
        runTime: '14:08',
        coverage,
        metCount: req.filter(c => c.state === 'met').length,
        unmetCount: req.filter(c => c.state === 'unmet').length,
        offTaskCount: coverage.filter(c => c.state === 'off-task').length,
        totalCount: req.length,
        overall,
        regressionNote: seeded(item.id + 99)() > 0.7 ? 'possible regression in login redirect (#120)' : undefined,
      };
    });
}

export function buildDeliveries(items: Item[], agents: Agent[]): Delivery[] {
  return items
    .filter(i => i.status === 'done' && isAgentWork(i, agents))
    .map((item, idx) => {
      const rng = seeded(item.id * 7919 + 3);
      const { coverage } = coverageFor(item, agents);
      const req = coverage.filter(c => c.state !== 'off-task');
      const total = req.length;
      const wasMet = req.filter(c => c.state === 'met').length;
      const roll = rng();
      const status: Delivery['status'] = roll > 0.66 ? 'deployed' : roll > 0.33 ? 'merged' : 'open';
      const ciFailing = status === 'open' && rng() > 0.6;
      // Follow-up commits close the gaps once a PR is open (coverage travels with the PR).
      const nowMet = status === 'open' ? wasMet : total;
      return {
        id: `pr-${item.id}`,
        itemId: item.id,
        itemTitle: item.title,
        prNumber: 300 + idx * 3 + (item.id % 7),
        status,
        ci: ciFailing ? 'failing' : status === 'open' ? 'passing' : 'passing',
        build: 'passing',
        lint: 'passing',
        commits: 2 + Math.floor(rng() * 4),
        files: 3 + Math.floor(rng() * 10),
        reqMet: nowMet,
        reqTotal: total,
        reqWas: nowMet !== wasMet ? wasMet : undefined,
        fixedNotes: nowMet !== wasMet ? [
          { req: 'R3 min-length rule now enforced', file: 'ui/Signup.tsx:44' },
          { req: 'R4 409 → "email in use" now mapped', file: 'ui/api.ts:31' },
        ] : undefined,
        deployStaging: status !== 'open' ? '13:10' : undefined,
        deployProd: status === 'deployed' ? 'live' : status === 'merged' ? 'awaiting' : undefined,
        ciFailCount: ciFailing ? 2 : undefined,
      };
    });
}
