import React, { useEffect, useMemo, useState, useTransition } from 'react';
import { ZoomIn, ZoomOut, Maximize2, Search, Zap, AlertCircle, Bookmark, Clipboard, Tag, FileText } from 'lucide-react';
import { useProject } from '../context/ProjectContext.js';
import { BackendError, explainImpact } from '../lib/backend.js';
import {
  formatDegree,
  graphViewBox,
  isBoardItemNode,
  neighborsOf,
  nodeTypeLabel,
  buildImpactGraph,
  type ImpactGraphNode,
} from '../lib/impactGraph.js';
import { CitationChip } from './CitationChip.js';
import { VerdictBadge } from './VerdictBadge.js';
import { ImpactExplainResponse, ImpactNeighbor, ImpactEdgeKind, ImpactNodeKind } from '../types.js';

const NODE_COLOR: Record<ImpactNodeKind, { fill: string; stroke: string; icon: string }> = {
  item: { fill: 'var(--verdict-impact-bg)', stroke: 'var(--verdict-impact-txt)', icon: 'text-[var(--verdict-impact-txt)]' },
  decision: { fill: 'var(--verdict-dup-bg)', stroke: 'var(--warning)', icon: 'text-[var(--warning)]' },
  area: { fill: 'var(--verdict-new-bg)', stroke: 'var(--verdict-new-txt)', icon: 'text-[var(--verdict-new-txt)]' },
  source: { fill: 'var(--accent-bg)', stroke: 'var(--accent)', icon: 'text-[var(--accent)]' },
};

const EDGE_STROKE: Record<ImpactEdgeKind, string> = {
  contradicts: 'var(--verdict-conf-txt)',
  duplicate: 'var(--verdict-dup-txt)',
  'depends-on': 'var(--verdict-impact-txt)',
  affects: 'var(--text-tertiary)',
  supersedes: 'var(--text-tertiary)',
};

const EDGE_MARKER: Record<ImpactEdgeKind, string> = {
  contradicts: 'arrow-contradicts',
  duplicate: 'arrow-duplicate',
  'depends-on': 'arrow-depends',
  affects: 'arrow-affects',
  supersedes: 'arrow-affects',
};

export const ImpactGraph: React.FC = () => {
  const { state, features, setSelectedCardId, activeProjectId, triggerToast } = useProject();
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [explaining, setExplaining] = useState(false);
  const [llmExplanation, setLlmExplanation] = useState<ImpactExplainResponse | null>(null);
  const [, startTransition] = useTransition();

  const { nodes, edges } = useMemo(
    () => buildImpactGraph({
      items: state?.items ?? [],
      decisions: state?.decisions ?? [],
      features,
    }),
    [state?.items, state?.decisions, features],
  );

  const selectedNode = nodes.find(n => n.id === selectedNodeId) ?? null;
  const neighbors = selectedNode ? neighborsOf(selectedNode.id, nodes, edges) : [];

  useEffect(() => {
    setLlmExplanation(null);
  }, [selectedNodeId]);

  const filteredNodes = nodes.filter(n => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return n.label.toLowerCase().includes(q) || n.id.toLowerCase().includes(q) || (n.details ?? '').toLowerCase().includes(q);
  });
  const visibleIds = new Set(filteredNodes.map(n => n.id));

  const handleZoom = (direction: 'in' | 'out') => {
    setZoom(prev => {
      if (direction === 'in') return Math.min(prev + 0.15, 2.0);
      return Math.max(prev - 0.15, 0.5);
    });
  };

  const resetGraph = () => {
    setZoom(1);
    setOffset({ x: 0, y: 0 });
  };

  const isConnected = (nodeId: string) => {
    if (!hoveredNodeId) return true;
    if (nodeId === hoveredNodeId) return true;
    return edges.some(e =>
      (e.source === hoveredNodeId && e.target === nodeId) ||
      (e.target === hoveredNodeId && e.source === nodeId)
    );
  };

  const openCard = (node: ImpactGraphNode) => {
    if (isBoardItemNode(node)) setSelectedCardId(node.boardItemId);
  };

  const handleNodeClick = (node: ImpactGraphNode) => {
    setSelectedNodeId(node.id);
  };

  const handleExplain = async () => {
    if (!selectedNode || !activeProjectId || explaining) return;
    setExplaining(true);
    try {
      const res = await explainImpact(activeProjectId, {
        nodeId: selectedNode.id,
        node: { id: selectedNode.id, type: selectedNode.type, label: selectedNode.label },
        neighbors,
        verdictSnippet: selectedNode.verdict?.message || selectedNode.verdict?.citation?.snippet,
      });
      setLlmExplanation(res);
    } catch (e) {
      triggerToast(e instanceof BackendError
        ? e.toDisplay()
        : "Couldn't explain this impact. Retry.");
    } finally {
      setExplaining(false);
    }
  };

  const viewBox = graphViewBox(nodes);
  const empty = nodes.length === 0;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[calc(100vh-140px)]">
      <div className="lg:col-span-2 border border-stone-200 dark:border-stone-850 bg-stone-50/60 dark:bg-stone-900/60 rounded-[var(--r-lg)] relative overflow-hidden flex flex-col">
        <div className="p-3.5 border-b border-stone-200 dark:border-stone-850 bg-stone-100/40 dark:bg-stone-900/40 flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-[var(--accent)]" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-stone-700 dark:text-stone-300">
              Interactive Impact & Alignment Graph
            </h3>
          </div>

          <div className="flex items-center gap-2">
            <div className="relative">
              <input
                type="text"
                placeholder="Search node..."
                aria-label="Search nodes"
                value={searchQuery}
                onChange={(e) => startTransition(() => setSearchQuery(e.target.value))}
                className="pl-8 pr-3 py-1 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-950 text-xs text-stone-800 dark:text-stone-200 focus:outline-none focus:border-[var(--accent)]"
              />
              <Search className="w-3.5 h-3.5 text-stone-400 absolute left-2.5 top-2" />
            </div>

            <button
              type="button"
              onClick={() => handleZoom('in')}
              className="p-1 px-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 hover:bg-stone-100 dark:hover:bg-stone-850 text-stone-600 dark:text-stone-300 text-xs flex items-center gap-1 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
              title="Zoom In"
              aria-label="Zoom in"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => handleZoom('out')}
              className="p-1 px-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 hover:bg-stone-100 dark:hover:bg-stone-850 text-stone-600 dark:text-stone-300 text-xs flex items-center gap-1 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
              title="Zoom Out"
              aria-label="Zoom out"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={resetGraph}
              className="p-1 px-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 hover:bg-stone-100 dark:hover:bg-stone-850 text-stone-600 dark:text-stone-300 text-xs flex items-center gap-1 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
              title="Fit Screen"
              aria-label="Fit graph to screen"
            >
              <Maximize2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <div className="flex-1 relative cursor-grab select-none">
          {empty ? (
            <p className="absolute inset-0 flex items-center justify-center text-sm text-stone-500 dark:text-stone-400 px-6 text-center">
              No items to trace yet. Add board cards or extract features to see impact.
            </p>
          ) : (
            <svg className="w-full h-full" style={{ minHeight: '400px' }} viewBox={viewBox} role="img" aria-label="Impact graph">
              <defs>
                <marker id="arrow-contradicts" viewBox="0 0 10 10" refX="18" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--verdict-conf-txt)" />
                </marker>
                <marker id="arrow-duplicate" viewBox="0 0 10 10" refX="18" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--verdict-dup-txt)" />
                </marker>
                <marker id="arrow-depends" viewBox="0 0 10 10" refX="18" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--verdict-impact-txt)" />
                </marker>
                <marker id="arrow-affects" viewBox="0 0 10 10" refX="18" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--text-tertiary)" />
                </marker>
              </defs>

              <g style={{ transform: `scale(${zoom}) translate(${offset.x}px, ${offset.y}px)`, transformOrigin: 'center' }}>
                {edges.map((edge) => {
                  const srcNode = nodes.find(n => n.id === edge.source);
                  const tgtNode = nodes.find(n => n.id === edge.target);
                  if (!srcNode || !tgtNode) return null;
                  if (!visibleIds.has(edge.source) || !visibleIds.has(edge.target)) return null;

                  const col = EDGE_STROKE[edge.type];
                  const isDimmed = hoveredNodeId && hoveredNodeId !== edge.source && hoveredNodeId !== edge.target;

                  return (
                    <g key={edge.id} className="transition-opacity duration-200" style={{ opacity: isDimmed ? 0.15 : 0.8 }}>
                      <line
                        x1={srcNode.x}
                        y1={srcNode.y}
                        x2={tgtNode.x}
                        y2={tgtNode.y}
                        stroke={col}
                        strokeWidth={edge.type === 'contradicts' ? 2 : 1.5}
                        strokeDasharray={edge.type === 'contradicts' || edge.type === 'duplicate' ? '4,4' : undefined}
                        markerEnd={`url(#${EDGE_MARKER[edge.type]})`}
                      />
                      <text
                        x={(srcNode.x + tgtNode.x) / 2}
                        y={(srcNode.y + tgtNode.y) / 2 - 5}
                        className="fill-stone-400 dark:fill-stone-500 font-mono text-[9px] text-center"
                        textAnchor="middle"
                      >
                        {edge.label}
                      </text>
                    </g>
                  );
                })}

                {filteredNodes.map((node) => {
                  const colors = NODE_COLOR[node.type];
                  const isHovered = hoveredNodeId === node.id;
                  const isSelected = selectedNodeId === node.id;
                  const isDimmed = !isConnected(node.id);

                  return (
                    <g
                      key={node.id}
                      tabIndex={0}
                      role="button"
                      aria-label={`${nodeTypeLabel(node.type)} ${node.label}`}
                      aria-pressed={isSelected}
                      onMouseEnter={() => setHoveredNodeId(node.id)}
                      onMouseLeave={() => setHoveredNodeId(null)}
                      onClick={() => handleNodeClick(node)}
                      onDoubleClick={() => openCard(node)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          handleNodeClick(node);
                        }
                      }}
                      className="cursor-pointer transition-all duration-200 focus:outline-none"
                      style={{ opacity: isDimmed ? 0.25 : 1 }}
                    >
                      <circle
                        cx={node.x}
                        cy={node.y}
                        r={isSelected ? 42 : isHovered ? 40 : 36}
                        fill="none"
                        stroke={colors.stroke}
                        strokeWidth={isSelected ? 3 : isHovered ? 2 : 0}
                        className="transition-all opacity-40 duration-200"
                      />
                      <circle
                        cx={node.x}
                        cy={node.y}
                        r={26}
                        fill={colors.fill}
                        stroke={colors.stroke}
                        strokeWidth={2}
                      />
                      <g transform={`translate(${node.x - 6}, ${node.y - 14})`}>
                        {node.type === 'decision' && <Bookmark className={`w-3 h-3 ${colors.icon}`} />}
                        {node.type === 'item' && <Clipboard className={`w-3 h-3 ${colors.icon}`} />}
                        {node.type === 'area' && <Tag className={`w-3 h-3 ${colors.icon}`} />}
                        {node.type === 'source' && <FileText className={`w-3 h-3 ${colors.icon}`} />}
                      </g>
                      <text
                        x={node.x}
                        y={node.y + 12}
                        className="fill-stone-800 dark:fill-stone-200 font-sans font-medium text-[9px] text-center select-none"
                        textAnchor="middle"
                      >
                        {node.label}
                      </text>
                    </g>
                  );
                })}
              </g>
            </svg>
          )}
        </div>

        <div className="p-3 border-t border-stone-200 dark:border-stone-850 bg-stone-100/30 dark:bg-stone-900/40 flex items-center gap-4 text-[10px] font-mono justify-center flex-wrap">
          <div className="flex items-center gap-1.5 text-stone-600 dark:text-stone-300">
            <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: 'var(--verdict-impact-txt)' }} />
            <span>Cards (▢)</span>
          </div>
          <div className="flex items-center gap-1.5 text-stone-600 dark:text-stone-300">
            <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: 'var(--warning)' }} />
            <span>Decisions (◆)</span>
          </div>
          <div className="flex items-center gap-1.5 text-stone-600 dark:text-stone-300">
            <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: 'var(--verdict-new-txt)' }} />
            <span>Areas (⬡)</span>
          </div>
          <div className="flex items-center gap-1.5 text-stone-600 dark:text-stone-300">
            <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: 'var(--accent)' }} />
            <span>Features (⤓)</span>
          </div>
          <div className="flex items-center gap-1.5 text-stone-600 dark:text-stone-300 border-l border-stone-250 dark:border-stone-800 pl-4">
            <span className="w-4 h-0.5 border-t-2 border-dashed inline-block" style={{ borderColor: 'var(--verdict-conf-txt)' }} />
            <span>Contradiction</span>
          </div>
        </div>
      </div>

      <div className="border border-stone-200 dark:border-stone-850 bg-stone-50/60 dark:bg-stone-900/60 rounded-[var(--r-lg)] p-5 flex flex-col justify-between min-h-0">
        <div className="min-h-0 overflow-y-auto pr-1">
          <div className="flex items-center gap-2 mb-4">
            <AlertCircle className="w-5 h-5 text-[var(--accent)]" />
            <h2 className="text-sm font-semibold text-stone-950 dark:text-stone-50 tracking-tight">
              Selected Impact Explanation
            </h2>
          </div>

          {!selectedNode ? (
            <div className="p-4 rounded-[var(--r-md)] bg-stone-100/50 dark:bg-stone-950/40 border border-stone-200 dark:border-stone-850">
              <p className="text-stone-600 dark:text-stone-400 text-xs leading-relaxed">
                Pick an item or decision to trace.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="p-4 rounded-[var(--r-md)] bg-stone-100/50 dark:bg-stone-950/40 border border-stone-200 dark:border-stone-850">
                <div className="flex items-start justify-between gap-2">
                  <h4 className="font-semibold text-stone-900 dark:text-stone-100 text-sm">
                    {selectedNode.label}
                  </h4>
                  <span className="shrink-0 text-[10px] font-mono uppercase tracking-wider text-stone-400">
                    {nodeTypeLabel(selectedNode.type)}
                  </span>
                </div>
                <p className="mt-2 text-stone-600 dark:text-stone-400 text-xs leading-relaxed">
                  {formatDegree(neighbors)}
                </p>
                {selectedNode.verdict && (
                  <div className="mt-3 space-y-1.5">
                    <VerdictBadge type={selectedNode.verdict.type} confidence={selectedNode.verdict.confidence} />
                    <p className="text-xs text-stone-600 dark:text-stone-400 leading-relaxed">
                      {selectedNode.verdict.message}
                    </p>
                    {selectedNode.verdict.citation?.snippet && (
                      <p className="text-[11px] font-mono text-stone-500 dark:text-stone-450 leading-relaxed">
                        “{selectedNode.verdict.citation.snippet}”
                      </p>
                    )}
                  </div>
                )}
              </div>

              {neighbors.length > 0 && (
                <ul className="space-y-1.5">
                  {neighbors.map((n: ImpactNeighbor) => (
                    <li key={`${n.id}-${n.edgeType}`} className="text-xs text-stone-600 dark:text-stone-400 flex items-baseline gap-2">
                      <span className="font-mono text-[10px] text-stone-400 shrink-0">{n.edgeType}</span>
                      <span>{n.label}</span>
                    </li>
                  ))}
                </ul>
              )}

              {isBoardItemNode(selectedNode) && (
                <button
                  type="button"
                  onClick={() => openCard(selectedNode)}
                  className="text-xs font-semibold text-[var(--accent)] hover:opacity-80 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] rounded-[var(--r-sm)]"
                >
                  Open card
                </button>
              )}

              {explaining && (
                <p className="text-[11px] font-mono text-stone-400 italic">thinking…</p>
              )}

              {llmExplanation && (
                <div className="p-4 rounded-[var(--r-md)] bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-850 space-y-2">
                  <h4 className="font-semibold text-stone-900 dark:text-stone-100 text-sm">
                    {llmExplanation.headline}
                  </h4>
                  <p className="text-xs text-stone-600 dark:text-stone-400 leading-relaxed whitespace-pre-line">
                    {llmExplanation.text}
                  </p>
                  {llmExplanation.citations.length > 0 && (
                    <div className="pt-2 border-t border-stone-200 dark:border-stone-800 flex items-center gap-1.5 flex-wrap">
                      <span className="text-[10px] text-stone-400 font-mono">Cites:</span>
                      {llmExplanation.citations.map((cit, idx) => (
                        <CitationChip
                          key={`${cit.id}-${idx}`}
                          id={cit.id}
                          type={cit.type}
                          title={cit.title}
                          snippet={cit.snippet}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="pt-4">
          <button
            type="button"
            onClick={handleExplain}
            disabled={!selectedNode || !activeProjectId || explaining}
            className="w-full py-2 bg-[var(--accent)] hover:opacity-90 active:scale-95 transition-transform text-white rounded-[var(--r-md)] text-xs font-semibold cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
          >
            {explaining ? 'Thinking…' : 'Explain this impact'}
          </button>
        </div>
      </div>
    </div>
  );
};
