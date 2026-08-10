import React, { useState } from 'react';
import { ZoomIn, ZoomOut, Maximize2, Search, Zap, AlertCircle, Bookmark, Clipboard, Tag } from 'lucide-react';
import { useProject } from '../context/ProjectContext.js';
import { useTransition } from 'react';

interface GraphNode {
  id: string;
  label: string;
  type: 'item' | 'decision' | 'area';
  x: number;
  y: number;
  details?: string;
}

interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  type: 'affects' | 'depends-on' | 'contradicts' | 'supersedes' | 'duplicate';
}

export const ImpactGraph: React.FC = () => {
  const { state, setSelectedCardId } = useProject();
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>("node-120"); // Defaults to redirected flow
  const [searchQuery, setSearchQuery] = useState("");
  const [isPending, startTransition] = useTransition();

  // Nodes definition
  const baseNodes: GraphNode[] = [
    { id: "node-142", type: "item", label: "Add SSO (#142)", x: 220, y: 150, details: "Add SSO logins with customized parameters." },
    { id: "dec-4", type: "decision", label: "Rely on IdP (Dec #4)", x: 420, y: 150, details: "Minimize credentials by avoiding custom SSO." },
    { id: "dec-9", type: "decision", label: "MFA for Admins (Dec #9)", x: 420, y: 280, details: "Enforce multi factor login parameters." },
    { id: "area-auth", type: "area", label: "Area: Auth", x: 300, y: 350, details: "Access tokens & validations block." },
    { id: "node-71", type: "item", label: "Billing Auth (#71)", x: 180, y: 280, details: "Secure checks in invoice pages." },
    { id: "node-120", type: "item", label: "Redirection Flow (#120)", x: 100, y: 220, details: "Sequence route redirects on success." },
    
    { id: "dec-12", type: "decision", label: "Server CSV (Dec #12)", x: 620, y: 220, details: "Asynchronous server calculations only." },
    { id: "node-88", type: "item", label: "CSV Reporter (#88)", x: 740, y: 300, details: "AWS S3 file exporter streaming worker." },
    { id: "node-95", type: "item", label: "CSV Button (#95)", x: 740, y: 140, details: "Direct export invoices CSV UI button." }
  ];

  // Edges definition
  const baseEdges: GraphEdge[] = [
    { id: "e1", source: "node-142", target: "dec-4", label: "contradicts", type: "contradicts" },
    { id: "e2", source: "node-120", target: "node-71", label: "affects", type: "affects" },
    { id: "e3", source: "node-71", target: "area-auth", label: "depends-on", type: "depends-on" },
    { id: "e4", source: "dec-4", target: "area-auth", label: "affects", type: "affects" },
    { id: "e5", source: "dec-9", target: "area-auth", label: "affects", type: "affects" },
    { id: "e6", source: "node-95", target: "node-88", label: "duplicate of", type: "duplicate" },
    { id: "e7", source: "node-88", target: "dec-12", label: "depends-on", type: "depends-on" }
  ];

  const filteredNodes = baseNodes.filter(n =>
    n.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
    n.id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleZoom = (direction: 'in' | 'out') => {
    setZoom(prev => {
      if (direction === 'in') return Math.min(prev + 0.15, 2.0);
      return Math.max(prev - 0.15, 0.5);
    });
  };

  const resetGraph = () => {
    setZoom(1);
    setOffset({ x: 0, y: 0 });
    setSelectedNodeId("node-120");
  };

  const getExplanation = () => {
    if (selectedNodeId === 'node-142') {
      return {
        headline: "Item #142 Analysis (Add SSO)",
        text: "This item directly contradicts **Decision #4 (Rely on customer IdP)**. Building user directory login tables and passwords breaks the rule of avoiding in-house credential management. Proceeding requires a formal override."
      };
    } else if (selectedNodeId === 'node-120') {
      return {
        headline: "Item #120 Analysis (Redirection Flow)",
        text: "This item touches login redirections and shares core auth controllers with **Billing Auth (#71)**. To avoid deep-linking vulnerabilities, both modules must be verified side-by-side using unified redirection helpers."
      };
    } else if (selectedNodeId === 'node-95') {
      return {
        headline: "Item #95 Analysis (CSV Button)",
        text: "This item overlaps **91% with Item #88 (CSV Reporter)**. Merging #95's direct export invoice requirement directly into #88's background stream keeps our reporting engine modular and prevents duplicative reports."
      };
    }
    return {
      headline: "Area / Node Analysis",
      text: "Select a node (Item, Decision, or Area) to trace system connections and compile dynamic automated impact briefs."
    };
  };

  const isConnected = (nodeId: string) => {
    if (!hoveredNodeId) return true;
    if (nodeId === hoveredNodeId) return true;
    return baseEdges.some(e =>
      (e.source === hoveredNodeId && e.target === nodeId) ||
      (e.target === hoveredNodeId && e.source === nodeId)
    );
  };

  const handleNodeClick = (nodeId: string) => {
    setSelectedNodeId(nodeId);
    // If it's an item, allow clicking to inspect
    if (nodeId.startsWith("node-")) {
      const idNum = parseInt(nodeId.replace("node-", ""));
      if (!isNaN(idNum)) {
        // Double-click or select
        setSelectedCardId(idNum);
      }
    }
  };

  const nodeColor = (type: 'item' | 'decision' | 'area') => {
    if (type === 'decision') return { bg: '#F59E0B', text: '#F59E0B', fill: 'rgba(245, 158, 11, 0.1)', border: '#F59E0B' };
    if (type === 'item') return { bg: '#8B5CF6', text: '#8B5CF6', fill: 'rgba(139, 92, 246, 0.1)', border: '#8B5CF6' };
    return { bg: '#06B6D4', text: '#06B6D4', fill: 'rgba(6, 182, 212, 0.1)', border: '#06B6D4' };
  };

  const edgeColor = (type: 'affects' | 'depends-on' | 'contradicts' | 'supersedes' | 'duplicate') => {
    if (type === 'contradicts') return '#EF4444'; // Red
    if (type === 'duplicate') return '#F59E0B'; // Amber
    if (type === 'depends-on') return '#8B5CF6'; // Purple
    return '#A1A1AA'; // Zinc
  };

  const explanation = getExplanation();

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[calc(100vh-140px)]">
      {/* Visual Canvas Block */}
      <div className="lg:col-span-2 border border-stone-200 dark:border-stone-850 bg-stone-50/60 dark:bg-stone-900/60 rounded-[var(--r-lg)] relative overflow-hidden flex flex-col">
        {/* Header toolbar */}
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
                value={searchQuery}
                onChange={(e) => startTransition(() => setSearchQuery(e.target.value))}
                className="pl-8 pr-3 py-1 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-950 text-xs text-stone-800 dark:text-stone-200 focus:outline-none focus:border-[var(--accent)]"
              />
              <Search className="w-3.5 h-3.5 text-stone-400 absolute left-2.5 top-2" />
            </div>

            <button
              onClick={() => handleZoom('in')}
              className="p-1 px-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 hover:bg-stone-100 dark:hover:bg-stone-850 text-stone-600 dark:text-stone-300 text-xs flex items-center gap-1 cursor-pointer"
              title="Zoom In"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => handleZoom('out')}
              className="p-1 px-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 hover:bg-stone-100 dark:hover:bg-stone-850 text-stone-600 dark:text-stone-300 text-xs flex items-center gap-1 cursor-pointer"
              title="Zoom Out"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={resetGraph}
              className="p-1 px-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 hover:bg-stone-100 dark:hover:bg-stone-850 text-stone-600 dark:text-stone-300 text-xs flex items-center gap-1 cursor-pointer"
              title="Fit Screen"
            >
              <Maximize2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Canvas Area */}
        <div className="flex-1 relative cursor-grab select-none">
          <svg className="w-full h-full" style={{ minHeight: '400px' }}>
            {/* Draw arrow definitions */}
            <defs>
              <marker id="arrow- zinc" viewBox="0 0 10 10" refX="18" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#A1A1AA" />
              </marker>
              <marker id="arrow-red" viewBox="0 0 10 10" refX="18" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#EF4444" />
              </marker>
              <marker id="arrow-amber" viewBox="0 0 10 10" refX="18" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#F59E0B" />
              </marker>
              <marker id="arrow-purple" viewBox="0 0 10 10" refX="18" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#8B5CF6" />
              </marker>
            </defs>

            {/* Render Edges */}
            <g style={{ transform: `scale(${zoom}) translate(${offset.x}px, ${offset.y}px)`, transformOrigin: 'center' }}>
              {baseEdges.map((edge) => {
                const srcNode = baseNodes.find(n => n.id === edge.source);
                const tgtNode = baseNodes.find(n => n.id === edge.target);
                if (!srcNode || !tgtNode) return null;

                const col = edgeColor(edge.type);
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
                      markerEnd={`url(#arrow-${edge.type === 'contradicts' ? 'red' : edge.type === 'duplicate' ? 'amber' : edge.type === 'depends-on' ? 'purple' : 'zinc'})`}
                    />
                    {/* Tiny edge labels */}
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

              {/* Render Nodes */}
              {filteredNodes.map((node) => {
                const colors = nodeColor(node.type);
                const isHovered = hoveredNodeId === node.id;
                const isSelected = selectedNodeId === node.id;
                const isDimmed = !isConnected(node.id);

                return (
                  <g
                    key={node.id}
                    onMouseEnter={() => setHoveredNodeId(node.id)}
                    onMouseLeave={() => setHoveredNodeId(null)}
                    onClick={() => handleNodeClick(node.id)}
                    className="cursor-pointer transition-all duration-200"
                    style={{ opacity: isDimmed ? 0.25 : 1 }}
                  >
                    {/* Glow outline on selection/hover */}
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r={isSelected ? 42 : isHovered ? 40 : 36}
                      fill="none"
                      stroke={colors.border}
                      strokeWidth={isSelected ? 3 : isHovered ? 2 : 0}
                      className="transition-all opacity-40 duration-200"
                    />

                    {/* Main Node Bubble */}
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r={26}
                      fill={colors.fill}
                      stroke={colors.border}
                      strokeWidth={2}
                    />

                    {/* Type specific icons */}
                    <g transform={`translate(${node.x - 6}, ${node.y - 14})`}>
                      {node.type === 'decision' && <Bookmark className="w-3 h-3 text-amber-500" />}
                      {node.type === 'item' && <Clipboard className="w-3 h-3 text-violet-500" />}
                      {node.type === 'area' && <Tag className="w-3 h-3 text-cyan-500" />}
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
        </div>

        {/* Informational Legends */}
        <div className="p-3 border-t border-stone-200 dark:border-stone-850 bg-stone-100/30 dark:bg-stone-900/40 flex items-center gap-4 text-[10px] font-mono justify-center flex-wrap">
          <div className="flex items-center gap-1.5 text-stone-600 dark:text-stone-300">
            <span className="w-2.5 h-2.5 rounded-full bg-violet-500 inline-block" />
            <span>Card Backlog (▢)</span>
          </div>
          <div className="flex items-center gap-1.5 text-stone-600 dark:text-stone-300">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" />
            <span>Decisions (◆)</span>
          </div>
          <div className="flex items-center gap-1.5 text-stone-600 dark:text-stone-300">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-500 inline-block" />
            <span>Areas (⬡)</span>
          </div>
          <div className="flex items-center gap-1.5 text-stone-600 dark:text-stone-300 border-l border-stone-250 dark:border-stone-800 pl-4">
            <span className="w-4 h-0.5 border-t-2 border-dashed border-red-500 inline-block" />
            <span>Contradiction Link</span>
          </div>
        </div>
      </div>

      {/* Right Explanation Column */}
      <div className="border border-stone-200 dark:border-stone-850 bg-stone-50/60 dark:bg-stone-900/60 rounded-[var(--r-lg)] p-5 flex flex-col justify-between">
        <div>
          <div className="flex items-center gap-2 mb-4">
            <AlertCircle className="w-5 h-5 text-[var(--accent)]" />
            <h2 className="text-sm font-semibold text-stone-950 dark:text-stone-50 tracking-tight">
              Selected Impact Explanation
            </h2>
          </div>

          <div className="p-4 rounded-[var(--r-md)] bg-stone-100/50 dark:bg-stone-950/40 border border-stone-200 dark:border-stone-850">
            <h4 className="font-semibold text-stone-900 dark:text-stone-100 h2 text-sm max-w-full">
              {explanation.headline}
            </h4>
            <p className="mt-2 text-stone-600 dark:text-stone-400 text-xs leading-relaxed font-sans">
              {explanation.text}
            </p>
          </div>

          <div className="mt-5 space-y-3">
            <div className="text-[11px] font-mono uppercase tracking-wider text-stone-400">
              Interactive Tips
            </div>
            <ul className="space-y-2 text-xs text-stone-500 dark:text-stone-450">
              <li>• Click on any Node component in the left canvas to target it.</li>
              <li>• Hover individual Nodes to isolate their logical neighborhood network.</li>
              <li>• Selected Card components can be double-clicked to view full editor details.</li>
            </ul>
          </div>
        </div>

        <div>
          <button
            onClick={() => alert(`Impact summary generated for node ${selectedNodeId}. Analysis confirmed clean.`)}
            className="w-full py-2 bg-[var(--accent)] hover:opacity-90 active:scale-95 transition-transform text-white rounded-[var(--r-md)] text-xs font-semibold cursor-pointer"
          >
            Explain this impact
          </button>
        </div>
      </div>
    </div>
  );
};
