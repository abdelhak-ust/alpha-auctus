// Derive the Trace / impact graph from board items, decisions, and features.
// Layout is layered and deterministic — no hardcoded demo nodes.

import {
  Candidate,
  Decision,
  Feature,
  GeneratedTask,
  ImpactEdgeKind,
  ImpactNeighbor,
  ImpactNodeKind,
  Item,
  VerdictDetail,
  VerdictType,
} from '../types.js';

export const IMPACT_COLLAPSE_AT = 40;

export interface ImpactGraphNode {
  id: string;
  label: string;
  type: ImpactNodeKind;
  x: number;
  y: number;
  details?: string;
  /** Set only for published board cards — drawer opens on this id. */
  boardItemId?: number;
  collapsedCount?: number;
  verdict?: VerdictDetail | null;
}

export interface ImpactGraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  type: ImpactEdgeKind;
}

export interface ImpactGraphData {
  nodes: ImpactGraphNode[];
  edges: ImpactGraphEdge[];
}

const COL_X = { source: 120, area: 340, rest: 580 } as const;
const ROW_Y = 88;
const ORIGIN_Y = 70;

export function areaSlug(area: string): string {
  const slug = area.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  return slug || 'general';
}

export function areaNodeId(area: string): string {
  return `area-${areaSlug(area)}`;
}

export function itemNodeId(id: number): string {
  return `item-${id}`;
}

export function decisionNodeId(id: number): string {
  return `decision-${id}`;
}

export function featureNodeId(id: string): string {
  return `feature-${id}`;
}

export function taskNodeId(id: string): string {
  return `task-${id}`;
}

function shortLabel(text: string, max = 24): string {
  const t = text.trim();
  return t.length <= max ? t : `${t.slice(0, max - 1)}…`;
}

function parseNumericId(raw: string): number | null {
  const n = parseInt(String(raw).replace(/[^\d]/g, ''), 10);
  return Number.isFinite(n) ? n : null;
}

function verdictEdgeType(type: VerdictType): ImpactEdgeKind | null {
  if (type === 'duplicate') return 'duplicate';
  if (type === 'conflict') return 'contradicts';
  if (type === 'impact') return 'affects';
  return null;
}

function edgeLabel(type: ImpactEdgeKind): string {
  if (type === 'duplicate') return 'duplicate';
  if (type === 'depends-on') return 'depends-on';
  if (type === 'contradicts') return 'contradicts';
  if (type === 'supersedes') return 'supersedes';
  return 'affects';
}

function candidateTargetId(candidate: Candidate): string | null {
  if (candidate.type === 'item') {
    const id = parseNumericId(candidate.id);
    return id == null ? null : itemNodeId(id);
  }
  if (candidate.type === 'decision') {
    const id = parseNumericId(candidate.id);
    return id == null ? null : decisionNodeId(id);
  }
  return null;
}

export function buildImpactGraph(input: {
  items: Item[];
  decisions: Decision[];
  features: Feature[];
}): ImpactGraphData {
  const items = input.items ?? [];
  const decisions = input.decisions ?? [];
  const features = input.features ?? [];

  const nodes = new Map<string, Omit<ImpactGraphNode, 'x' | 'y'>>();
  const edges: ImpactGraphEdge[] = [];
  const edgeKeys = new Set<string>();

  const addNode = (node: Omit<ImpactGraphNode, 'x' | 'y'>) => {
    if (!nodes.has(node.id)) nodes.set(node.id, node);
  };

  const addEdge = (source: string, target: string, type: ImpactEdgeKind) => {
    if (source === target) return;
    if (!nodes.has(source) || !nodes.has(target)) return;
    const key = `${source}|${target}|${type}`;
    if (edgeKeys.has(key)) return;
    edgeKeys.add(key);
    edges.push({
      id: `e-${source}-${target}-${type}`,
      source,
      target,
      label: edgeLabel(type),
      type,
    });
  };

  const ensureArea = (area: string) => {
    const trimmed = area.trim();
    if (!trimmed) return null;
    const id = areaNodeId(trimmed);
    addNode({
      id,
      type: 'area',
      label: shortLabel(`Area: ${trimmed}`),
      details: trimmed,
    });
    return id;
  };

  for (const item of items) {
    addNode({
      id: itemNodeId(item.id),
      type: 'item',
      label: shortLabel(`${item.title} (#${item.id})`),
      details: item.description || item.title,
      boardItemId: item.id,
      verdict: item.verdict,
    });
    const areaId = ensureArea(item.area);
    if (areaId) addEdge(itemNodeId(item.id), areaId, 'depends-on');
  }

  for (const feature of features) {
    addNode({
      id: featureNodeId(feature.id),
      type: 'source',
      label: shortLabel(feature.name),
      details: feature.summary || feature.name,
    });
    for (const task of feature.tasks ?? []) {
      linkFeatureTask(feature, task, addNode, addEdge, ensureArea, items);
    }
  }

  for (const decision of decisions) {
    addNode({
      id: decisionNodeId(decision.id),
      type: 'decision',
      label: shortLabel(`${decision.title} (Dec #${decision.id})`),
      details: decision.description || decision.title,
    });
  }

  for (const item of items) {
    const verdict = item.verdict;
    if (!verdict) continue;
    const from = itemNodeId(item.id);
    const edgeType = verdictEdgeType(verdict.type);
    if (edgeType) {
      for (const candidate of verdict.candidates ?? []) {
        const to = candidateTargetId(candidate);
        if (to) addEdge(from, to, edgeType);
      }
    }
    linkDecisionCitation(item, verdict, decisions, addEdge);
  }

  const placed = layoutNodes(collapseExtraItems([...nodes.values()], edges), edges);
  return placed;
}

function linkFeatureTask(
  feature: Feature,
  task: GeneratedTask,
  addNode: (node: Omit<ImpactGraphNode, 'x' | 'y'>) => void,
  addEdge: (source: string, target: string, type: ImpactEdgeKind) => void,
  ensureArea: (area: string) => string | null,
  items: Item[],
) {
  const featureId = featureNodeId(feature.id);
  if (task.boardItemId != null && items.some(i => i.id === task.boardItemId)) {
    addEdge(featureId, itemNodeId(task.boardItemId), 'affects');
    return;
  }
  const id = taskNodeId(task.id);
  addNode({
    id,
    type: 'item',
    label: shortLabel(task.title),
    details: task.description || task.title,
  });
  addEdge(featureId, id, 'affects');
  const areaId = ensureArea(task.area);
  if (areaId) addEdge(id, areaId, 'depends-on');
}

function linkDecisionCitation(
  item: Item,
  verdict: VerdictDetail,
  decisions: Decision[],
  addEdge: (source: string, target: string, type: ImpactEdgeKind) => void,
) {
  const citation = verdict.citation;
  if (!citation || citation.type !== 'decision') return;
  const decId = parseNumericId(citation.id);
  if (decId == null || !decisions.some(d => d.id === decId)) return;
  addEdge(decisionNodeId(decId), itemNodeId(item.id), 'affects');
}

function itemAreaId(
  nodeId: string,
  edges: ImpactGraphEdge[],
): string {
  const edge = edges.find(e => e.source === nodeId && e.type === 'depends-on' && e.target.startsWith('area-'));
  return edge?.target ?? 'area-general';
}

function collapseExtraItems(
  nodes: Array<Omit<ImpactGraphNode, 'x' | 'y'>>,
  edges: ImpactGraphEdge[],
): Array<Omit<ImpactGraphNode, 'x' | 'y'>> {
  if (nodes.length <= IMPACT_COLLAPSE_AT) return nodes;

  const items = nodes.filter(n => n.type === 'item' && n.collapsedCount == null);
  const kept = nodes.filter(n => n.type !== 'item' || n.collapsedCount != null);
  const byArea = new Map<string, Array<Omit<ImpactGraphNode, 'x' | 'y'>>>();
  for (const item of items) {
    const areaId = itemAreaId(item.id, edges);
    const list = byArea.get(areaId) ?? [];
    list.push(item);
    byArea.set(areaId, list);
  }

  let keepPerArea = 2;
  const extras = () =>
    [...byArea.values()].reduce((n, list) => n + Math.max(0, list.length - keepPerArea), 0);
  while (keepPerArea > 0 && kept.length + items.length - extras() + byArea.size > IMPACT_COLLAPSE_AT) {
    keepPerArea -= 1;
  }

  const dropped = new Set<string>();
  for (const [areaId, list] of byArea) {
    const visible = list.slice(0, keepPerArea);
    const extra = list.slice(keepPerArea);
    kept.push(...visible);
    if (extra.length > 0) {
      const moreId = `${areaId}-more`;
      kept.push({
        id: moreId,
        type: 'item',
        label: `+${extra.length}`,
        details: `${extra.length} more items in this area`,
        collapsedCount: extra.length,
      });
      extra.forEach(n => dropped.add(n.id));
      const key = `${moreId}|${areaId}|depends-on`;
      if (!edges.some(e => `${e.source}|${e.target}|${e.type}` === key) && nodes.some(n => n.id === areaId)) {
        edges.push({
          id: `e-${moreId}-${areaId}-depends-on`,
          source: moreId,
          target: areaId,
          label: 'depends-on',
          type: 'depends-on',
        });
      }
    }
  }

  if (dropped.size > 0) {
    for (let i = edges.length - 1; i >= 0; i--) {
      const e = edges[i];
      if (dropped.has(e.source) || dropped.has(e.target)) edges.splice(i, 1);
    }
  }

  return kept;
}

function layoutNodes(
  nodes: Array<Omit<ImpactGraphNode, 'x' | 'y'>>,
  edges: ImpactGraphEdge[],
): ImpactGraphData {
  const sources = nodes.filter(n => n.type === 'source').sort(byId);
  const areas = nodes.filter(n => n.type === 'area').sort(byId);
  const rest = nodes
    .filter(n => n.type === 'item' || n.type === 'decision')
    .sort((a, b) => {
      const aa = itemAreaId(a.id, edges);
      const bb = itemAreaId(b.id, edges);
      if (aa !== bb) return aa.localeCompare(bb);
      return a.id.localeCompare(b.id);
    });

  const placed: ImpactGraphNode[] = [
    ...stackColumn(sources, COL_X.source),
    ...stackColumn(areas, COL_X.area),
    ...stackColumn(rest, COL_X.rest),
  ];

  return { nodes: placed, edges: [...edges] };
}

function stackColumn(
  column: Array<Omit<ImpactGraphNode, 'x' | 'y'>>,
  x: number,
): ImpactGraphNode[] {
  return column.map((node, i) => ({ ...node, x, y: ORIGIN_Y + i * ROW_Y }));
}

function byId(a: { id: string }, b: { id: string }): number {
  return a.id.localeCompare(b.id);
}

export function graphViewBox(nodes: ImpactGraphNode[]): string {
  if (nodes.length === 0) return '0 0 800 400';
  const xs = nodes.map(n => n.x);
  const ys = nodes.map(n => n.y);
  const minX = Math.min(...xs) - 90;
  const minY = Math.min(...ys) - 70;
  const width = Math.max(Math.max(...xs) - minX + 90, 420);
  const height = Math.max(Math.max(...ys) - minY + 70, 300);
  return `${minX} ${minY} ${width} ${height}`;
}

export function neighborsOf(
  nodeId: string,
  nodes: ImpactGraphNode[],
  edges: ImpactGraphEdge[],
): ImpactNeighbor[] {
  const byIdMap = new Map(nodes.map(n => [n.id, n]));
  const out: ImpactNeighbor[] = [];
  for (const edge of edges) {
    let otherId: string | null = null;
    if (edge.source === nodeId) otherId = edge.target;
    else if (edge.target === nodeId) otherId = edge.source;
    if (!otherId) continue;
    const other = byIdMap.get(otherId);
    if (!other) continue;
    out.push({
      id: other.id,
      type: other.type,
      label: other.label,
      edgeType: edge.type,
    });
  }
  return out;
}

export function formatDegree(neighbors: ImpactNeighbor[]): string {
  const counts: Record<ImpactNodeKind, number> = { item: 0, decision: 0, area: 0, source: 0 };
  for (const n of neighbors) counts[n.type] += 1;
  const parts: string[] = [];
  if (counts.item) parts.push(`${counts.item} item${counts.item === 1 ? '' : 's'}`);
  if (counts.source) parts.push(`${counts.source} feature${counts.source === 1 ? '' : 's'}`);
  if (counts.area) parts.push(`${counts.area} area${counts.area === 1 ? '' : 's'}`);
  if (counts.decision) parts.push(`${counts.decision} decision${counts.decision === 1 ? '' : 's'}`);
  if (parts.length === 0) return 'touches nothing else yet';
  return `touches ${parts.join(', ')}`;
}

export function nodeTypeLabel(type: ImpactNodeKind): string {
  if (type === 'source') return 'Feature';
  if (type === 'decision') return 'Decision';
  if (type === 'area') return 'Area';
  return 'Item';
}

export function isBoardItemNode(node: ImpactGraphNode | null | undefined): node is ImpactGraphNode & { boardItemId: number } {
  return node != null && node.boardItemId != null;
}
