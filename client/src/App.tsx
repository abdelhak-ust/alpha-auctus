import React, { useState, useEffect, useTransition, useMemo, useRef } from 'react';
import {
  ProjectProvider,
  useProject
} from './context/ProjectContext.js';
import {
  VerdictBadge
} from './components/VerdictBadge.js';
import {
  VerdictRow
} from './components/VerdictRow.js';
import {
  CitationChip
} from './components/CitationChip.js';
import {
  CommandBar
} from './components/CommandBar.js';
import {
  ImpactGraph
} from './components/ImpactGraph.js';
import {
  Drawer
} from './components/Drawer.js';
import {
  Toast
} from './components/Toast.js';
import {
  LandingPage
} from './components/LandingPage.js';
import {
  ProjectsView
} from './components/ProjectsView.js';
import {
  ProjectSwitcher
} from './components/ProjectSwitcher.js';
import {
  NewProjectSetup
} from './components/NewProjectSetup.js';
import {
  ClarificationChat
} from './components/ClarificationChat.js';
import {
  RunsView
} from './components/RunsView.js';
import {
  ReviewsView
} from './components/ReviewsView.js';
import {
  DeliveryView
} from './components/DeliveryView.js';
import {
  RunChip
} from './components/StatusBadges.js';
import {
  buildRuns,
  buildReviews
} from './lib/delivery.js';
import {
  LayoutDashboard,
  Bell,
  MessageSquare,
  Network,
  BookOpen,
  FolderInput,
  FolderKanban,
  Trash2,
  Settings,
  Plus,
  Moon,
  Sun,
  HelpCircle,
  Database,
  ArrowRight,
  Sparkles,
  Search,
  Check,
  CheckCircle2,
  ChevronRight,
  Undo2,
  Lock,
  BookmarkPlus,
  AlertTriangle,
  Bot,
  LogOut,
  Cog,
  Rocket
} from 'lucide-react';
import Markdown from 'react-markdown';
import { motion, AnimatePresence } from 'motion/react';
import { IngestItem, Item, Status, Priority, AgentKind } from './types.js';
import { resolveAssignee, agentKindStyle } from './lib/assignee.js';
import { BackendError, INGEST_ACCEPT, isIngestibleFile, withPeriod } from './lib/backend.js';

function DashboardView() {
  const { state, addItem, updateItem, setSelectedCardId, refreshState, triggerToast } = useProject();
  const [inlineAddingStatus, setInlineAddingStatus] = useState<Status | null>(null);
  const [newCardTitle, setNewCardTitle] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [filterArea, setFilterArea] = useState("all");
  const [isPending, startTransition] = useTransition();

  const handleCreateInlineCard = async (status: Status) => {
    if (!newCardTitle.trim()) {
      setInlineAddingStatus(null);
      return;
    }
    const titleVal = newCardTitle;
    setNewCardTitle("");
    setInlineAddingStatus(null);

    await addItem({
      title: titleVal,
      status: status,
      description: "Proposed backlog card specifications.",
      area: "auth",
      priority: "P2"
    });
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = async (e: React.DragEvent, status: Status) => {
    e.preventDefault();
    const itemId = e.dataTransfer.getData("itemId");
    if (itemId) {
      await updateItem(parseInt(itemId), { status });
      triggerToast(`Moved card #${itemId} to ${status.replace('_', ' ')}.`);
    }
  };

  const handleDragStart = (e: React.DragEvent, id: number) => {
    e.dataTransfer.setData("itemId", id.toString());
  };

  const statuses: { value: Status; label: string; icon: string }[] = [
    { value: 'inbox', label: 'Inbox', icon: '📥' },
    { value: 'next', label: 'Next Up', icon: '🎯' },
    { value: 'in_progress', label: 'In Progress', icon: '⚡' },
    { value: 'done', label: 'Done', icon: '✓' }
  ];

  const getFilteredItems = () => {
    if (!state) return [];
    return state.items.filter(item => {
      const matchSearch = item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.description.toLowerCase().includes(searchQuery.toLowerCase());
      const matchArea = filterArea === 'all' || item.area === filterArea;
      return matchSearch && matchArea;
    });
  };

  const filteredItems = getFilteredItems();

  const areas = state ? Array.from(new Set(state.items.map(i => i.area))) : [];

  // Runs/reviews are derived from the board so a card can show its live run status
  // (spec §4.1: the board doubles as an at-a-glance execution dashboard).
  const runByItem = useMemo(() => {
    const runs = buildRuns(state?.items || [], state?.agents || []);
    return new Map(runs.map(r => [r.itemId, r]));
  }, [state?.items, state?.agents]);
  const reviewByItem = useMemo(() => {
    const reviews = buildReviews(state?.items || [], state?.agents || []);
    return new Map(reviews.map(r => [r.itemId, r]));
  }, [state?.items, state?.agents]);

  return (
    <div className="space-y-6">
      {/* Board Controls Bar */}
      <div className="flex items-center justify-between flex-wrap gap-4 py-1.5 px-4 bg-stone-100/50 dark:bg-stone-900/50 border border-stone-200 dark:border-stone-850 rounded-[var(--r-md)]">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="relative">
            <input
              type="text"
              placeholder="Filter cards..."
              value={searchQuery}
              onChange={(e) => startTransition(() => setSearchQuery(e.target.value))}
              className="pl-8 pr-3 py-1.5 w-48 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-950 text-xs text-stone-800 dark:text-stone-200 focus:outline-none focus:border-[var(--accent)]"
            />
            <Search className="w-4 h-4 text-stone-400 absolute left-2.5 top-2.5" />
          </div>

          <div className="flex items-center gap-2 text-xs">
            <span className="text-stone-400">Area:</span>
            <select
              value={filterArea}
              onChange={(e) => startTransition(() => setFilterArea(e.target.value))}
              className="bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-850 px-2 py-1.5 rounded text-xs select-none"
            >
              <option value="all">All subsystems</option>
              {areas.map(ar => <option key={ar} value={ar}>{ar}</option>)}
            </select>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setInlineAddingStatus('inbox')}
            className="px-3 py-1.5 rounded-[var(--r-sm)] bg-[var(--accent)] text-white text-xs font-semibold hover:opacity-95 active:scale-95 transition-transform flex items-center gap-1 cursor-pointer shadow-sm"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New Card</span>
          </button>
        </div>
      </div>

      {/* Main Column Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 items-start pb-10">
        {statuses.map(col => {
          const colItems = filteredItems.filter(i => i.status === col.value);
          const isAdding = inlineAddingStatus === col.value;

          return (
            <div
              key={col.value}
              onDragOver={handleDragOver}
              onDrop={(e) => handleDrop(e, col.value)}
              className="bg-stone-50/60 dark:bg-stone-900/40 p-3 rounded-[var(--r-lg)] border border-stone-200 dark:border-stone-850 flex flex-col min-h-[480px] w-full"
            >
              {/* Status Header */}
              <div className="flex items-center justify-between gap-2 mb-3 px-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs">{col.icon}</span>
                  <h3 className="text-xs font-bold text-stone-700 dark:text-stone-300 uppercase tracking-wider">
                    {col.label} <span className="opacity-40 ml-1">({colItems.length})</span>
                  </h3>
                </div>

                <button
                  onClick={() => setInlineAddingStatus(col.value)}
                  className="p-1 rounded hover:bg-stone-200 dark:hover:bg-stone-800 text-stone-450 hover:text-stone-700 cursor-pointer"
                  title="Inline Card Entry"
                >
                  <Plus className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Backlog cards list */}
              <div className="space-y-2.5 flex-1 select-none">
                
                {/* Inline Addition row */}
                {isAdding && (
                  <div className="p-3 rounded-[var(--r-md)] border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-950 space-y-2.5 shadow-sm">
                    <input
                      type="text"
                      autoFocus
                      placeholder="Add card title... (Enter)"
                      value={newCardTitle}
                      onChange={(e) => setNewCardTitle(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleCreateInlineCard(col.value);
                        if (e.key === 'Escape') setInlineAddingStatus(null);
                      }}
                      className="w-full bg-transparent text-xs text-stone-800 dark:text-stone-200 p-1 border-b border-stone-200 dark:border-stone-800 focus:outline-none focus:border-[var(--accent)] font-sans"
                    />
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[9px] font-mono text-stone-400">Esc to dismiss</span>
                      <button
                        onClick={() => handleCreateInlineCard(col.value)}
                        className="p-1 px-2.5 rounded bg-stone-900 dark:bg-stone-100 text-white dark:text-stone-900 text-[10px] font-bold hover:opacity-90 cursor-pointer"
                      >
                        Add
                      </button>
                    </div>
                  </div>
                )}

                {colItems.map(item => {
                  const hasFlag = item.verdict && item.verdict.type !== 'net-new';

                  return (
                    <div
                      key={item.id}
                      draggable
                      onDragStart={(e) => handleDragStart(e, item.id)}
                      onClick={() => setSelectedCardId(item.id)}
                      className={`p-3.5 rounded-[var(--r-md)] bg-white dark:bg-stone-950 border transition-all cursor-pointer hover:border-stone-400 dark:hover:border-stone-700 hover:shadow-xs hover:transform hover:-translate-y-0.5 active:cursor-grabbing select-none ${hasFlag && item.verdict?.type === 'conflict' ? 'border-red-200 bg-red-50/10 dark:border-red-950 dark:bg-red-950/5' : 'border-stone-200 dark:border-stone-850'}`}
                    >
                      <div className="flex items-start justify-between gap-1.5">
                        <span className="font-mono text-[11px] text-stone-400 dark:text-stone-500 font-bold shrink-0 leading-none mt-[2px]">
                          #{item.id}
                        </span>
                        <div className="flex items-center gap-1.5 text-[10px] font-mono shrink-0 uppercase">
                          <span className={`px-1 py-0.2 rounded font-bold ${item.priority === 'P0' || item.priority === 'P1' ? 'text-red-500 bg-red-100 dark:bg-red-950/40' : 'text-stone-450 bg-stone-100 dark:bg-stone-800'}`}>
                            {item.priority}
                          </span>
                          {(() => {
                            const a = resolveAssignee(item.assignee, state?.agents || []);
                            if (a.kind === 'agent') {
                              const style = agentKindStyle(a.agent?.kind || 'custom');
                              const Icon = style.icon;
                              return (
                                <span
                                  className={`flex items-center gap-0.5 px-1 py-0.2 rounded font-semibold font-sans normal-case max-w-[110px] ${style.tint}`}
                                  title={`AI agent: ${a.label}`}
                                >
                                  <Icon className="w-2.5 h-2.5 shrink-0" />
                                  <span className="truncate">{a.label}</span>
                                </span>
                              );
                            }
                            return (
                              <span className="px-1 py-0.2 rounded bg-indigo-50 dark:bg-indigo-950/40 text-[var(--accent)] font-semibold font-sans">
                                {a.label}
                              </span>
                            );
                          })()}
                        </div>
                      </div>

                      <h4 className="mt-2 text-[13px] font-semibold text-stone-900 dark:text-stone-100 leading-snug tracking-tight">
                        {item.title}
                      </h4>

                      {/* Quiet verdict notification badge */}
                      {item.verdict && item.verdict.type !== 'net-new' && (
                        <div className="mt-3 flex items-center justify-between">
                          <VerdictBadge type={item.verdict.type} confidence={item.verdict.confidence} className="scale-90 origin-left" />
                        </div>
                      )}
                      
                      {item.verdict && item.verdict.type === 'checking' && (
                        <div className="mt-3">
                          <VerdictBadge type="checking" className="scale-90 origin-left" />
                        </div>
                      )}

                      {/* Run-status chip — appears once a card is agent work in flight (§4.1) */}
                      {(() => {
                        const run = runByItem.get(item.id);
                        if (!run) return null;
                        const review = reviewByItem.get(item.id);
                        return (
                          <div className="mt-2.5">
                            <RunChip status={run.status} met={review?.metCount} total={review?.totalCount} />
                          </div>
                        );
                      })()}

                      <div className="mt-3.5 pt-2 border-t border-stone-100 dark:border-stone-900 flex items-center justify-between text-[10px] text-stone-400 font-medium">
                        <span className="bg-stone-50 dark:bg-stone-900 px-1.5 py-0.5 rounded font-mono uppercase">
                          ⬡ {item.area}
                        </span>
                        {item.source && (
                          <span className="text-[11px] font-sans text-stone-455">
                            {item.source.type === 'sheet' ? '⊞' : item.source.type === 'call' ? '🎙' : item.source.type === 'ticket' ? '🎫' : '✉'} source
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}

                {colItems.length === 0 && !isAdding && (
                  <div className="py-8 text-center text-[10px] font-mono text-stone-400 border border-dashed border-stone-200 dark:border-stone-800 rounded">
                    + Drag / Add Card here
                  </div>
                )}

              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function VerdictsView() {
  const { state } = useProject();

  const flaggedItems = state?.items.filter(i => i.verdict && i.verdict.type !== 'net-new') || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-stone-900 dark:text-stone-50 tracking-tight">
            Conflicts & Duplicates Inbox
          </h2>
          <p className="text-xs text-stone-500 dark:text-stone-400">
            Verify automated items matching existing requirements and architectural principles.
          </p>
        </div>
        <span className="bg-red-100 dark:bg-red-950/40 text-red-700 dark:text-red-400 text-xs px-2.5 py-1 rounded-full font-bold">
          {flaggedItems.length} Waiting Review
        </span>
      </div>

      <div className="space-y-4">
        {flaggedItems.map(item => (
          <VerdictRow key={item.id} item={item} />
        ))}

        {flaggedItems.length === 0 && (
          <div className="border border-dashed border-stone-250 dark:border-stone-800 rounded-[var(--r-lg)] p-12 text-center text-stone-400">
            <Check className="w-8 h-8 text-emerald-500 mx-auto mb-3" />
            <h3 className="font-semibold text-stone-900 dark:text-stone-100 h2 text-sm max-w-full">
              Memory completely aligned.
            </h3>
            <p className="text-xs text-stone-550 mt-1">
              No conflicts or overlaps detected between your cards and past architectural decisions.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function AskView() {
  const { askQuestion } = useProject();
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setAnswer("");
    setCitations([]);

    try {
      const data = await askQuestion(query);
      setAnswer(data.answer);
      setCitations(data.citations || []);
    } catch (e) {
      setAnswer("Couldn't reach the AI provider. Check your key in Settings ▸ Data & AI.");
    } finally {
      setLoading(false);
    }
  };

  const samplePrompts = [
    "Why did we decide against building SSO?",
    "What is the state of auth?",
    "What breaks if we change CSV?"
  ];

  return (
    <div className="max-w-3xl mx-auto space-y-6 py-4">
      <div>
        <h2 className="text-base font-bold text-stone-900 dark:text-stone-50 tracking-tight flex items-center gap-2">
          <MessageSquare className="w-5 h-5 text-[var(--accent)]" />
          <span>Ask Decision Memory Layer</span>
        </h2>
        <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">
          Perform a semantic query across all past meetings, emails, backlog tickets, and board choices.
        </p>
      </div>

      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          type="text"
          id="memory-query-input"
          placeholder="Ask anything about the system configuration or historical rationale..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="flex-1 bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-800 rounded-[var(--r-md)] p-3 text-sm focus:outline-none focus:border-[var(--accent)] text-stone-800 dark:text-stone-200 shadow-xs"
        />
        <button
          type="submit"
          id="memory-query-submit"
          className="px-5 bg-[var(--accent)] text-white text-xs font-semibold rounded-[var(--r-md)] hover:opacity-95 active:scale-95 transition-transform flex items-center gap-1.5 cursor-pointer shadow-sm"
        >
          <Sparkles className="w-4 h-4" />
          <span>Ask</span>
        </button>
      </form>

      {/* Suggested prompts */}
      {answer === "" && !loading && (
        <div className="space-y-3 pt-2">
          <span className="text-[11px] font-mono text-stone-400 uppercase tracking-wider">Example queries</span>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {samplePrompts.map(pr => (
              <button
                key={pr}
                onClick={() => { setQuery(pr); }}
                className="p-3 text-left border border-stone-200 dark:border-stone-800 hover:border-[var(--accent)] rounded-[var(--r-md)] bg-stone-50/20 dark:bg-stone-900/10 text-xs text-stone-600 dark:text-stone-300 hover:text-[var(--accent)] transition-colors cursor-pointer"
              >
                {pr}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Loading bar */}
      {loading && (
        <div className="p-8 border rounded-[var(--r-lg)] border-stone-200 dark:border-stone-800 bg-stone-50/20 dark:bg-stone-900/10 text-center space-y-3">
          <div className="w-6 h-6 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-xs font-mono text-stone-400 animate-pulse">
            Searching memory…
          </p>
        </div>
      )}

      {/* Answer Pane */}
      {answer !== "" && (
        <div className="border border-stone-150 dark:border-stone-800 rounded-[var(--r-lg)] p-5 space-y-4 bg-white dark:bg-stone-950 shadow-sm leading-normal">
          <div className="flex items-center gap-2 border-b border-stone-200 dark:border-stone-850 pb-3">
            <Sparkles className="w-4 h-4 text-amber-500" />
            <span className="text-[11px] font-mono text-stone-450 uppercase tracking-wider">Automated synthesis</span>
          </div>

          <div className="text-sm text-stone-800 dark:text-stone-200 font-sans whitespace-pre-line leading-relaxed markdown-body">
            <Markdown>{answer}</Markdown>
          </div>

          {citations.length > 0 && (
            <div className="pt-3.5 border-t border-stone-200 dark:border-stone-850 flex items-center gap-2 flex-wrap">
              <span className="text-[10px] font-mono text-stone-400 uppercase">Citations in memory:</span>
              {citations.map((cit, idx) => (
                <CitationChip
                  key={idx}
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
  );
}

function AuthorView() {
  const { generateDocument, triggerToast } = useProject();
  const [area, setArea] = useState("auth");
  const [type, setType] = useState<'brd' | 'spec' | 'tree'>('brd');
  const [time, setTime] = useState("30");
  const [docMarkdown, setDocMarkdown] = useState("");
  const [unresolvedCount, setUnresolvedCount] = useState(0);
  const [loading, setLoading] = useState(false);

  const handleGenerate = async () => {
    setLoading(true);
    setDocMarkdown("");
    setUnresolvedCount(0);

    try {
      const resp = await generateDocument(type, area, time);
      setDocMarkdown(resp.document);
      setUnresolvedCount(resp.unresolvedConflictsCount);
    } catch (e) {
      setDocMarkdown("Couldn't reach the AI provider. Check your key in Settings ▸ Data & AI.");
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(docMarkdown);
    triggerToast("Copied generated document to clipboard.");
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[calc(100vh-140px)]">
      {/* Parameters Panel */}
      <div className="border border-stone-200 dark:border-stone-850 bg-stone-50/60 dark:bg-stone-900/60 p-5 rounded-[var(--r-lg)] space-y-5 flex flex-col justify-between">
        <div className="space-y-4">
          <div>
            <h3 className="text-sm font-semibold text-stone-950 dark:text-stone-50 flex items-center gap-2">
              <BookOpen className="w-5 h-5 text-[var(--accent)]" />
              <span>Document Engine parameters</span>
            </h3>
            <p className="text-[11px] text-stone-500 mt-1">
              Select variables to compile a document completely synchronized with decision history.
            </p>
          </div>

          {/* Doc type */}
          <div>
            <label className="text-xs font-semibold text-stone-400 uppercase tracking-wider block mb-2">Document Type</label>
            <div className="grid grid-cols-3 gap-2">
              {(['brd', 'spec', 'tree'] as const).map(dt => (
                <button
                  key={dt}
                  onClick={() => setType(dt)}
                  className={`p-2.5 rounded text-xs select-none font-bold capitalize transition-colors border cursor-pointer ${type === dt ? 'bg-[var(--accent)] text-white border-transparent' : 'bg-white dark:bg-stone-950 border-stone-200 dark:border-stone-850 text-stone-600 dark:text-stone-300'}`}
                >
                  {dt === 'brd' ? 'BRD' : dt === 'spec' ? 'Tech Spec' : 'Task Tree'}
                </button>
              ))}
            </div>
          </div>

          {/* Area boundary */}
          <div>
            <label className="text-xs font-semibold text-stone-400 uppercase tracking-wider block mb-1">Functional Subsystem</label>
            <select
              value={area}
              onChange={(e) => setArea(e.target.value)}
              className="w-full bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-850 px-2.5 py-1.5 rounded text-xs text-stone-800 dark:text-stone-100 select-none focus:outline-none"
            >
              <option value="auth">🔑 Authentication (auth)</option>
              <option value="reporting">📊 Reporting Exporter (reporting)</option>
              <option value="general">💼 General Systems</option>
            </select>
          </div>

          {/* Time scale */}
          <div>
            <label className="text-xs font-semibold text-stone-400 uppercase tracking-wider block mb-1">Memory Timeline scope</label>
            <select
              value={time}
              onChange={(e) => setTime(e.target.value)}
              className="w-full bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-850 px-2.5 py-1.5 rounded text-xs text-stone-800 dark:text-stone-100 select-none focus:outline-none"
            >
              <option value="30">Last 30 Days (Recommended)</option>
              <option value="90">Last 90 Days</option>
              <option value="365">Entire Project History</option>
            </select>
          </div>
        </div>

        <div>
          <button
            onClick={handleGenerate}
            className="w-full py-2 bg-[var(--accent)] text-white hover:opacity-95 active:scale-95 transition-transform text-xs font-semibold rounded-[var(--r-sm)] cursor-pointer"
          >
            Generate document
          </button>
        </div>
      </div>

      {/* Preview Output Panel */}
      <div className="lg:col-span-2 border border-stone-200 dark:border-stone-850 bg-white dark:bg-stone-950 rounded-[var(--r-lg)] flex flex-col relative overflow-hidden">
        
        {/* Document Actions header */}
        <div className="p-3.5 border-b border-stone-200 dark:border-stone-850 bg-stone-50 dark:bg-stone-900/60 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase text-stone-400 tracking-wider">
            Document Workspace Editor
          </span>
          {docMarkdown !== "" && (
            <button
              onClick={handleCopy}
              className="p-1 px-3 border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-950 hover:bg-stone-100 text-stone-700 dark:text-stone-300 rounded text-xs font-bold cursor-pointer"
            >
              Copy Markdown
            </button>
          )}
        </div>

        {/* Dynamic doc area */}
        <div className="flex-1 p-6 overflow-y-auto max-h-[500px]">
          {loading ? (
            <div className="h-full flex flex-col items-center justify-center space-y-2 text-stone-400">
              <div className="w-5 h-5 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
              <p className="font-mono text-xs animate-pulse">Generating…</p>
            </div>
          ) : docMarkdown !== "" ? (
            <div className="text-sm text-stone-800 dark:text-stone-200 space-y-4 markdown-body font-sans leading-normal">
              {unresolvedCount > 0 && (
                <div className="p-3 border border-red-200 bg-red-50/20 text-red-700 dark:border-red-950/40 rounded flex items-center gap-2 mb-4 text-xs">
                  <AlertTriangle className="w-4 h-4 text-red-500 shrink-0" />
                  <span>
                    Heads up: There is <strong>{unresolvedCount} unresolved conflict</strong> inside this subsystem scope. It is recommended to resolve it first!
                  </span>
                </div>
              )}
              <Markdown>{docMarkdown}</Markdown>
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center p-8 text-center text-stone-400 space-y-2">
              <BookOpen className="w-8 h-8 text-stone-300" />
              <p className="text-xs font-sans">
                Pick a type and scope, then generate a cited BRD, tech spec, or task tree from your decision history.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SourcesView() {
  const { state, uploadDocument, connectSource, activeProject, triggerToast } = useProject();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sending, setSending] = useState(false);
  const [uploadError, setUploadError] = useState<BackendError | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [connecting, setConnecting] = useState<string | null>(null);

  const connectedTypes = new Set((state?.sources || []).map(s => s.type));
  const isNewProject = (state?.sources?.length || 0) === 0;

  const connectorCatalog: { type: 'sheet' | 'transcript' | 'email' | 'ticket'; name: string; icon: string }[] = [
    { type: 'sheet', name: 'Google Sheet', icon: '⊞' },
    { type: 'transcript', name: 'Meeting transcripts', icon: '🎙' },
    { type: 'email', name: 'Feedback inbox', icon: '✉' },
    { type: 'ticket', name: 'Jira tickets', icon: '🎫' }
  ];

  const handleConnect = async (type: 'sheet' | 'transcript' | 'email' | 'ticket', name: string) => {
    setConnecting(type);
    try {
      await connectSource(type, name);
    } finally {
      setConnecting(null);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    const files = e.dataTransfer.files;
    if (files && files[0]) pickFile(files[0]);
  };

  // v1 ingests PDF/DOCX/MD/TXT only (plans/ingestion.md §9) — refuse others up front.
  const pickFile = (file: File) => {
    setUploadError(null);
    if (!isIngestibleFile(file.name)) {
      setSelectedFile(null);
      triggerToast(`Can't ingest ${file.name} (unsupported file type). Upload a PDF, DOCX, Markdown or TXT file.`);
      return;
    }
    setSelectedFile(file);
  };

  const handleSubmit = async () => {
    if (!selectedFile) return;
    setSending(true);
    setUploadError(null);
    try {
      await uploadDocument(selectedFile);
      setSelectedFile(null);
    } catch (e) {
      // Keep the file selected so Retry is one click; show problem + cause + fix inline (§7).
      setUploadError(e instanceof BackendError
        ? e
        : new BackendError(`Couldn't upload ${selectedFile.name}`, 'unexpected client error', 'Retry, or check the browser console', 0));
      if (!(e instanceof BackendError)) console.error(e);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* New-project onboarding: sources are the first setup step */}
      {isNewProject && (
        <div className="p-4 rounded-[var(--r-lg)] border border-[var(--accent)]/30 bg-[var(--accent-bg)] flex items-start gap-3">
          <span className="w-7 h-7 shrink-0 grid place-items-center rounded-full bg-[var(--accent)] text-white text-xs font-bold">1</span>
          <div>
            <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">
              Set up {activeProject ? `“${activeProject.name}”` : 'your project'} — start with your sources
            </h3>
            <p className="text-xs text-stone-600 dark:text-stone-300 mt-0.5 leading-relaxed max-w-2xl">
              Nexus builds memory from your existing inputs. Connect a source or drop in a file below — extracted
              items are dedup/conflict-checked before they ever reach your board.
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Connectors and manual Area */}
        <div className="space-y-4">
          <div>
            <h2 className="text-base font-bold text-stone-900 dark:text-stone-50 tracking-tight">
              Ingestion Channels & Webhooks
            </h2>
            <p className="text-xs text-stone-500 dark:text-stone-400">
              Sync developer planning channels, transcripts, or spreadsheets into Decision Memory.
            </p>
          </div>

          {/* Connect a source catalog */}
          <div className="space-y-2">
            <span className="text-[11px] font-mono uppercase tracking-wider text-stone-400">Connect a source</span>
            <div className="grid grid-cols-2 gap-2.5">
              {connectorCatalog.map((c) => {
                const already = connectedTypes.has(c.type);
                return (
                  <button
                    key={c.type}
                    onClick={() => !already && handleConnect(c.type, c.name)}
                    disabled={already || connecting === c.type}
                    className={`p-2.5 rounded-[var(--r-md)] border text-xs text-left flex items-center gap-2 transition-colors ${already ? 'border-stone-200 dark:border-stone-850 bg-stone-50/40 dark:bg-stone-900/20 text-stone-400 cursor-default' : 'border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-950 hover:border-[var(--accent)] text-stone-700 dark:text-stone-300 cursor-pointer'}`}
                  >
                    <span className="text-sm">{c.icon}</span>
                    <span className="font-medium flex-1">{c.name}</span>
                    {already ? (
                      <span className="text-[9px] uppercase font-bold text-emerald-600 dark:text-emerald-400">✓</span>
                    ) : connecting === c.type ? (
                      <span className="text-[9px] uppercase font-mono text-stone-400">…</span>
                    ) : (
                      <Plus className="w-3.5 h-3.5 text-[var(--accent)]" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {state && state.sources.length > 0 && (
            <span className="text-[11px] font-mono uppercase tracking-wider text-stone-400 block">Connected</span>
          )}
          <div className="grid grid-cols-2 gap-3.5">
            {state?.sources.map((src, idx) => (
              <div key={idx} className="p-3.5 border border-stone-200 dark:border-stone-850 bg-white dark:bg-stone-950 rounded-[var(--r-md)] text-xs flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="font-semibold block">{src.name}</span>
                    <span className={`px-1 rounded text-[9px] uppercase font-bold ${src.status === 'synced' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400' : 'bg-red-100 text-red-700'}`}>
                      {src.status === 'synced' ? 'Online' : 'Needs Config'}
                    </span>
                  </div>
                  {src.lastSynced && <span className="text-stone-400 font-mono text-[10px] block">Last Sync: {src.lastSynced}</span>}
                </div>
                {src.pendingCount > 0 && (
                  <span className="mt-3 inline-block font-bold text-amber-600 dark:text-amber-400">
                    {src.pendingCount} Review elements wait
                  </span>
                )}
              </div>
            ))}
          </div>

          {/* Drag & Drop Upload Zone */}
          <div
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(e) => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); fileInputRef.current?.click(); } }}
            role="button"
            tabIndex={0}
            aria-label="Upload files: documents and PDFs"
            className="border-2 border-dashed border-stone-250 dark:border-stone-800 rounded-[var(--r-lg)] p-8 text-center cursor-pointer hover:border-[var(--accent)] transition-colors select-none bg-stone-50/20 dark:bg-stone-900/15"
          >
            <FolderInput className="w-8 h-8 text-stone-400 mx-auto mb-2" />
            <h4 className="text-xs font-semibold text-stone-800 dark:text-stone-300">
              Drag & Drop file transcript
            </h4>
            <p className="text-[10px] text-stone-500 mt-1">
              Supports PDF, DOCX, Markdown or TXT.
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept={INGEST_ACCEPT}
              className="hidden"
              aria-hidden="true"
              tabIndex={-1}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) pickFile(f); e.target.value = ''; }}
            />

            {selectedFile && (
              <div onClick={(e) => e.stopPropagation()} className="mt-4 p-2.5 rounded bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-800 text-left cursor-default">
                <span className="font-mono text-xs font-bold font-sans">{selectedFile.name}</span>
                <span className="ml-2 font-mono text-[10px] text-stone-400">{Math.max(1, Math.round(selectedFile.size / 1024))} KB</span>
                <button
                  type="button"
                  onClick={handleSubmit}
                  disabled={sending}
                  className="w-full mt-2.5 bg-[var(--accent)] text-white font-semibold rounded p-1.5 text-xs hover:opacity-90 disabled:opacity-40"
                >
                  {sending ? 'Extracting…' : uploadError ? 'Retry' : 'Parse & dedupe'}
                </button>
                {uploadError && (
                  <div role="alert" className="mt-2.5 p-2.5 rounded-[var(--r-sm)] border border-[var(--border)] bg-[var(--verdict-conf-bg)] text-[11px] leading-relaxed text-[var(--text-primary)] space-y-0.5">
                    <p className="font-semibold text-[var(--verdict-conf-txt)]">{withPeriod(uploadError.problem)}</p>
                    <p><span className="text-[var(--text-secondary)]">Cause:</span> {withPeriod(uploadError.cause)}</p>
                    <p><span className="text-[var(--text-secondary)]">Fix:</span> {withPeriod(uploadError.fix)}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Review Extraction Timeline (Section 4.3 Triage queue) */}
        <div className="space-y-4">
          <div>
            <h2 className="text-base font-bold text-stone-900 dark:text-stone-50 tracking-tight flex items-center gap-1.5">
              <span>Ingested Triage Review Queue</span>
            </h2>
            <p className="text-xs text-stone-500 dark:text-stone-400">
              Dedupe planning card extractions before they impact active Kanban boards.
            </p>
          </div>

          <div className="space-y-3.5 max-h-[500px] overflow-y-auto pr-2 pb-14">
            {state?.ingestQueue.map((item) => (
              <VerdictRow key={item.id} item={item} isIngest={true} />
            ))}

            {state?.ingestQueue.length === 0 && (
              <div className="p-8 border rounded-[var(--r-lg)] border-stone-200 dark:border-stone-800 text-center text-stone-400 leading-normal">
                <Check className="w-6 h-6 text-emerald-500 mx-auto mb-2" />
                <h4 className="font-semibold text-[13px] text-stone-900 dark:text-stone-200 h2 text-sm max-w-full">
                  All channels processed.
                </h4>
                <p className="text-[10px] text-stone-500 mt-1">
                  Connected sources are quiet. New transcript uploads will feed the queue.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function DeprecateView() {
  const { getDeprecations, updateItem, deleteItem, triggerToast } = useProject();
  const [sus, setSus] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getDeprecations().then(data => {
      setSus(data);
      setLoading(false);
    });
  }, []);

  const handleRetire = async (id: string, name: string) => {
    setSus(prev => prev.filter(s => s.id !== id));
    triggerToast(`Retired legacy entity: "${name}"`);
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="text-base font-bold text-stone-900 dark:text-stone-50 tracking-tight">
          Suggested to retire
        </h2>
        <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">
          Items and decisions that look superseded, dormant, or contradicted. Each is cited — nothing is retired automatically.
        </p>
      </div>

      {loading ? (
        <div className="text-center font-mono py-12 text-stone-400 animate-pulse text-xs">
          Scanning for dormant and superseded items…
        </div>
      ) : (
        <div className="space-y-4">
          {sus.map((su, idx) => (
            <div key={idx} className="p-4 border rounded-[var(--r-md)] border-stone-200 dark:border-stone-850 bg-stone-50/20 dark:bg-stone-900/10 flex items-center justify-between gap-4">
              <div className="space-y-1">
                <span className="bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400 text-[10px] uppercase font-bold px-1.5 py-0.5 rounded">
                  {su.type} warning ({su.confidence}% confidence)
                </span>
                <h4 className="text-xs font-semibold text-stone-900 dark:text-stone-100 tracking-tight font-mono">
                  {su.title}
                </h4>
                <p className="text-xs text-stone-500 dark:text-stone-400">
                  {su.reason}
                </p>
                <div className="pt-1 select-none">
                  <span className="text-[10px] font-mono text-stone-400 font-semibold uppercase">Citing dependency:</span>{' '}
                  <span className="font-mono text-[10px] text-stone-400 bg-stone-100 dark:bg-stone-800 rounded px-1">{su.citation}</span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleRetire(su.id, su.title)}
                  className="px-3 py-1.5 rounded-[var(--r-sm)] bg-stone-900 border border-stone-850 dark:bg-stone-100 dark:text-stone-900 text-xs font-semibold cursor-pointer shadow-xs hover:opacity-95"
                >
                  Retire
                </button>
                <button
                  onClick={() => handleRetire(su.id, su.title)}
                  className="px-3 py-1.5 rounded-[var(--r-sm)] border border-stone-250 text-stone-600 dark:text-stone-300 text-xs font-medium bg-white dark:bg-stone-950 cursor-pointer"
                >
                  Snooze 30d
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SettingsView() {
  const { state, updateConfig, addDecision, triggerToast, createAgent, deleteAgent } = useProject();
  const [provider, setProvider] = useState<'managed' | 'byok'>('managed');
  const [apiKey, setApiKey] = useState("");
  const [noRetention, setNoRetention] = useState(true);

  // New custom agent form
  const [agentName, setAgentName] = useState("");
  const [agentKind, setAgentKind] = useState<AgentKind>("custom");

  const handleAddAgent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!agentName.trim()) return;
    await createAgent(agentName.trim(), agentKind);
    setAgentName("");
    setAgentKind("custom");
  };

  // Custom decision submission
  const [decTitle, setDecTitle] = useState("");
  const [decDesc, setDecDesc] = useState("");
  const [decArea, setDecArea] = useState("auth");

  useEffect(() => {
    if (state) {
      setProvider(state.apiConfig.provider);
      setApiKey(state.apiConfig.apiKey);
      setNoRetention(state.apiConfig.noRetention);
    }
  }, [state]);

  const handleConfigSave = async () => {
    await updateConfig({ provider, apiKey, noRetention });
  };

  const handleDecisionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!decTitle.trim()) return;

    await addDecision({
      title: decTitle,
      description: decDesc,
      area: decArea,
      createdBy: "AM"
    });

    setDecTitle("");
    setDecDesc("");
    triggerToast("Decision seeded successfully.");
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pb-12">
      
      {/* Decision management block */}
      <div className="space-y-4">
        <div>
          <h2 className="text-sm font-bold text-stone-900 dark:text-stone-50 uppercase tracking-wide">
            Add past architectural alignment decision
          </h2>
          <p className="text-[11px] text-stone-500">
            Write past design consensus parameters to enforce alignment checking across upcoming cards.
          </p>
        </div>

        <form onSubmit={handleDecisionSubmit} className="space-y-3.5 bg-white dark:bg-stone-950 p-5 rounded-[var(--r-lg)] border border-stone-150 dark:border-stone-850">
          <div>
            <label className="text-[11px] font-mono text-stone-400 block mb-1">Decision Headline</label>
            <input
              type="text"
              placeholder="e.g. Enforce client IdP models instead of custom secure tables"
              value={decTitle}
              onChange={(e) => setDecTitle(e.target.value)}
              className="w-full bg-stone-50 dark:bg-stone-900 border border-stone-200 dark:border-stone-800 text-xs rounded p-2 focus:outline-none focus:border-[var(--accent)] text-stone-800 dark:text-stone-100"
            />
          </div>

          <div>
            <label className="text-[11px] font-mono text-stone-400 block mb-1">Rationale & guidelines</label>
            <textarea
              rows={3}
              placeholder="Detailed rule context..."
              value={decDesc}
              onChange={(e) => setDecDesc(e.target.value)}
              className="w-full bg-stone-50 dark:bg-stone-900 border border-stone-200 dark:border-stone-800 text-xs rounded p-2 focus:outline-none focus:border-[var(--accent)] text-stone-800 dark:text-stone-100"
            />
          </div>

          <div>
            <label className="text-[11px] font-mono text-stone-400 block mb-1">Access System area</label>
            <select
              value={decArea}
              onChange={(e) => setDecArea(e.target.value)}
              className="w-full bg-stone-50 dark:bg-stone-900 border border-stone-200 dark:border-stone-800 text-xs rounded p-2 focus:outline-none focus:border-[var(--accent)]"
            >
              <option value="auth">🔑 Authentication (auth)</option>
              <option value="reporting">📊 Reporting Exporter (reporting)</option>
              <option value="database">🗄 Storage Database (database)</option>
            </select>
          </div>

          <button
            type="submit"
            className="px-4 py-2 bg-[var(--accent)] hover:opacity-95 text-white text-xs font-semibold rounded-[var(--r-sm)] flex items-center gap-1.5 cursor-pointer"
          >
            <BookmarkPlus className="w-4 h-4" />
            <span>Store Decision Rule</span>
          </button>
        </form>

        {/* List of existing decisions */}
        <div className="space-y-2">
          <span className="text-[11px] font-mono uppercase tracking-wider text-stone-400 block">Logged architectural decisions Memory</span>
          <div className="space-y-2 max-h-[300px] overflow-y-auto pr-2">
            {state?.decisions.map((dec) => (
              <div key={dec.id} className="p-3 border rounded-[var(--r-md)] border-stone-200 dark:border-stone-850 bg-stone-50/20 dark:bg-stone-900/10 text-xs">
                <div className="flex items-center justify-between font-mono text-[10px] mb-1">
                  <span className="font-bold text-[var(--accent)]">◆ DECISION #{dec.id}</span>
                  <span className="text-stone-450">{dec.date}</span>
                </div>
                <h4 className="font-semibold text-stone-850 dark:text-stone-100 font-mono tracking-tight text-xs max-w-full">
                  {dec.title}
                </h4>
                <p className="text-stone-500 dark:text-stone-450 text-[11px] mt-1 italic leading-relaxed">
                  “{dec.description}”
                </p>
              </div>
            ))}
          </div>
        </div>

      </div>

      {/* Postures and providers Block (Section 4.9 settings) */}
      <div className="space-y-4">
        <div>
          <h2 className="text-sm font-bold text-stone-900 dark:text-stone-50 uppercase tracking-wide">
            Enterprise data posture & security
          </h2>
          <p className="text-[11px] text-stone-500">
            Switch provider credentials, toggle regional data isolation, and verify active keys.
          </p>
        </div>

        <div className="p-5 bg-white dark:bg-stone-950 rounded-[var(--r-lg)] border border-stone-150 dark:border-stone-850 space-y-5 text-xs">
          {/* AI Providers */}
          <div className="space-y-2.5">
            <span className="text-stone-400 block font-semibold uppercase text-[10px] tracking-wide">AI Provider Strategy</span>
            
            <div className="space-y-2">
              <label className="flex items-start gap-2.5 p-3 rounded border hover:bg-stone-50 dark:hover:bg-stone-900 border-stone-150 dark:border-stone-850 cursor-pointer">
                <input
                  type="radio"
                  name="provider"
                  checked={provider === 'managed'}
                  onChange={() => setProvider('managed')}
                  className="mt-[3px] text-[var(--accent)] focus:ring-[var(--accent)]"
                />
                <div>
                  <span className="font-semibold block text-stone-800 dark:text-stone-200">Managed (Running on Server Keys)</span>
                  <span className="text-[11px] text-stone-500">Evaluation setup, uses system environment secrets. Zero config.</span>
                </div>
              </label>

              <label className="flex items-start gap-2.5 p-3 rounded border hover:bg-stone-50 dark:hover:bg-stone-900 border-stone-150 dark:border-stone-850 cursor-pointer">
                <input
                  type="radio"
                  name="provider"
                  checked={provider === 'byok'}
                  onChange={() => setProvider('byok')}
                  className="mt-[3px] text-[var(--accent)] focus:ring-[var(--accent)]"
                />
                <div>
                  <span className="font-semibold block text-stone-800 dark:text-stone-200">Bring Your Own Key (BYOK)</span>
                  <span className="text-[11px] text-stone-500">Sensitive tenant posture. Enforces custom workspace keys only.</span>
                </div>
              </label>
            </div>
          </div>

          {provider === 'byok' && (
            <div className="p-3 bg-stone-100 dark:bg-stone-900 rounded space-y-2">
              <label className="text-[11px] font-mono text-stone-400 block">Workspace API key credential</label>
              <input
                type="password"
                placeholder="Paste external model key here..."
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="w-full text-xs font-mono p-1.5 rounded border border-stone-200 bg-white dark:bg-stone-950 focus:outline-none"
              />
            </div>
          )}

          {/* Postures check */}
          <div className="space-y-2.5 pt-4 border-t border-stone-150 dark:border-stone-850">
            <span className="text-stone-400 block font-semibold uppercase text-[10px] tracking-wide">Postures rules checklists</span>
            <div className="space-y-2 select-none">
              <label className="flex items-center gap-2 text-stone-700 dark:text-stone-300">
                <input
                  type="checkbox"
                  checked={noRetention}
                  onChange={(e) => setNoRetention(e.target.checked)}
                  className="rounded text-[var(--accent)] focus:ring-[var(--accent)]"
                />
                <span>Enable Zero-Retention parameters in outer calls (HIPAA compliant)</span>
              </label>
              <label className="flex items-center gap-2 text-stone-700 dark:text-stone-300">
                <input
                  type="checkbox"
                  defaultChecked
                  className="rounded text-[var(--accent)] focus:ring-[var(--accent)]"
                />
                <span>Centralized regional secure sandbox (Region: us-central1)</span>
              </label>
            </div>
          </div>

          <button
            onClick={handleConfigSave}
            className="w-full py-2 bg-[var(--accent)] hover:opacity-95 text-white font-semibold rounded-[var(--r-sm)] text-center cursor-pointer"
          >
            Apply Posture Configuration
          </button>
        </div>
      </div>

      {/* AI Agents catalog (workspace-wide, assignable on any card) */}
      <div className="space-y-4 lg:col-span-2">
        <div>
          <h2 className="text-sm font-bold text-stone-900 dark:text-stone-50 uppercase tracking-wide flex items-center gap-1.5">
            <Bot className="w-4 h-4 text-violet-500" /> AI Agents
          </h2>
          <p className="text-[11px] text-stone-500">
            Workspace-wide catalog of agents you can assign cards to. Built-ins ship by default; add your own.
          </p>
        </div>

        <div className="p-5 bg-white dark:bg-stone-950 rounded-[var(--r-lg)] border border-stone-150 dark:border-stone-850 space-y-4 text-xs">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {(state?.agents || []).map((agent) => {
              const style = agentKindStyle(agent.kind);
              const Icon = style.icon;
              return (
                <div key={agent.id} className="flex items-center justify-between gap-2 p-2.5 rounded-[var(--r-md)] border border-stone-150 dark:border-stone-850 bg-stone-50/30 dark:bg-stone-900/20">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={`flex items-center justify-center w-7 h-7 rounded shrink-0 ${style.tint}`}>
                      <Icon className="w-3.5 h-3.5" />
                    </span>
                    <div className="min-w-0">
                      <div className="font-semibold text-stone-800 dark:text-stone-200 truncate">{agent.name}</div>
                      <div className="text-[10px] text-stone-400 uppercase tracking-wide">{agent.kind}</div>
                    </div>
                  </div>
                  {agent.builtin ? (
                    <span className="text-[9px] font-mono uppercase tracking-wide text-stone-400 bg-stone-100 dark:bg-stone-800 px-1.5 py-0.5 rounded shrink-0">Built-in</span>
                  ) : (
                    <button
                      onClick={() => deleteAgent(agent.id)}
                      className="p-1 rounded text-stone-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/40 cursor-pointer shrink-0"
                      title="Remove agent"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              );
            })}
          </div>

          <form onSubmit={handleAddAgent} className="flex flex-col sm:flex-row gap-2 pt-3 border-t border-stone-150 dark:border-stone-850">
            <input
              type="text"
              placeholder="New agent name (e.g. Frontend Dev Agent)"
              value={agentName}
              onChange={(e) => setAgentName(e.target.value)}
              className="flex-1 bg-stone-50 dark:bg-stone-900 border border-stone-200 dark:border-stone-800 text-xs rounded p-2 focus:outline-none focus:border-[var(--accent)] text-stone-800 dark:text-stone-100"
            />
            <select
              value={agentKind}
              onChange={(e) => setAgentKind(e.target.value as AgentKind)}
              className="bg-stone-50 dark:bg-stone-900 border border-stone-200 dark:border-stone-800 text-xs rounded p-2 focus:outline-none focus:border-[var(--accent)] text-stone-800 dark:text-stone-100"
            >
              <option value="custom">Custom</option>
              <option value="design">Design</option>
              <option value="code">Code</option>
              <option value="qa">QA</option>
              <option value="docs">Docs</option>
              <option value="test">Test</option>
              <option value="security">Security</option>
            </select>
            <button
              type="submit"
              className="px-4 py-2 bg-[var(--accent)] hover:opacity-95 text-white text-xs font-semibold rounded-[var(--r-sm)] flex items-center justify-center gap-1.5 cursor-pointer shrink-0"
            >
              <Plus className="w-4 h-4" />
              <span>Add agent</span>
            </button>
          </form>
        </div>
      </div>

    </div>
  );
}

function AppShell({ onLogout }: { onLogout: () => void }) {
  const [showCommandBar, setShowCommandBar] = useState(false);

  // Trigger command deck listener
  useEffect(() => {
    const handleGlobalKeys = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setShowCommandBar(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleGlobalKeys);
    return () => window.removeEventListener('keydown', handleGlobalKeys);
  }, []);

  return (
    <ProjectProvider>
      <MainLayout showCommandBar={showCommandBar} setShowCommandBar={setShowCommandBar} onLogout={onLogout} />
    </ProjectProvider>
  );
}

export default function App() {
  const [authed, setAuthed] = useState<boolean>(() => {
    try {
      return localStorage.getItem('nexus-authed') === '1';
    } catch (e) {
      return false;
    }
  });

  const handleLogout = () => {
    try {
      localStorage.removeItem('nexus-authed');
    } catch (e) {}
    setAuthed(false);
  };

  if (!authed) {
    return (
      <LandingPage
        onEnter={() => {
          try {
            localStorage.setItem('nexus-authed', '1');
          } catch (e) {}
          setAuthed(true);
        }}
      />
    );
  }

  return <AppShell onLogout={handleLogout} />;
}

interface MainLayoutProps {
  showCommandBar: boolean;
  setShowCommandBar: (v: boolean) => void;
  onLogout: () => void;
}

function MainLayout({ showCommandBar, setShowCommandBar, onLogout }: MainLayoutProps) {
  const { theme, setTheme, activeView, setActiveView, state, loading, activeProjectId, setupPhase } = useProject();

  // Guided New Project flow is a full-screen takeover — no nav/board chrome.
  if (setupPhase === 'setup') return <NewProjectSetup />;
  if (setupPhase === 'chat') return <ClarificationChat />;

  const toggleTheme = () => {
    setTheme(theme === 'dark' ? 'light' : 'dark');
  };

  const getTriageCount = () => {
    if (!state) return 0;
    // Count backlog items flagged as conflict/duplicate waiting review
    return state.items.filter(i => i.verdict && i.verdict.type !== 'net-new').length + state.ingestQueue.length;
  };

  // The Reviews queue: agent implementations awaiting requirement validation (§4.13).
  const getReviewCount = () => {
    if (!state) return 0;
    return buildReviews(state.items, state.agents).filter(r => r.overall !== 'all-met').length;
  };

  // Left nav grouped by lifecycle phase (spec §3): PLAN → BUILD → VERIFY → KNOWLEDGE.
  type NavView = 'projects' | 'board' | 'verdicts' | 'runs' | 'reviews' | 'delivery' | 'memory' | 'impact' | 'author' | 'sources' | 'deprecate' | 'settings';
  type NavItem = { view: NavView; label: string; icon: any; count?: number };
  const navGroups: Array<{ phase: string | null; items: NavItem[] }> = [
    { phase: null, items: [
      { view: 'projects', label: 'Projects', icon: FolderKanban },
    ]},
    { phase: 'Plan', items: [
      { view: 'board', label: 'Board', icon: LayoutDashboard },
      { view: 'verdicts', label: 'Verdicts', icon: Bell, count: getTriageCount() },
    ]},
    { phase: 'Build', items: [
      { view: 'runs', label: 'Runs', icon: Cog },
    ]},
    { phase: 'Verify', items: [
      { view: 'reviews', label: 'Reviews', icon: CheckCircle2, count: getReviewCount() },
      { view: 'delivery', label: 'Delivery', icon: Rocket },
    ]},
    { phase: 'Knowledge', items: [
      { view: 'memory', label: 'Memory', icon: MessageSquare },
      { view: 'impact', label: 'Trace', icon: Network },
      { view: 'author', label: 'Author', icon: BookOpen },
      { view: 'sources', label: 'Sources', icon: FolderInput },
      { view: 'deprecate', label: 'Deprecate', icon: Trash2 },
    ]},
  ];

  return (
    <div className="min-h-screen bg-[var(--bg-app)] text-[var(--text-primary)] flex">
      {/* Side collapsible nav */}
      <aside className="w-64 border-r border-stone-200/50 dark:border-stone-850/50 flex flex-col justify-between shrink-0 bg-stone-50/50 dark:bg-stone-950/40 select-none hidden md:flex">
        <div className="p-4 space-y-6">
          {/* Logo Brand */}
          <div className="flex items-center gap-2 px-1">
            <span className="p-1.5 px-2 bg-[var(--accent)] text-white font-mono text-sm rounded font-bold">
              N
            </span>
            <div>
              <span className="font-sans font-semibold tracking-tight block text-base text-stone-900 dark:text-white leading-none">Nexus</span>
              <span className="text-[9px] text-stone-400 font-mono block tracking-widest mt-0.5">SOFTWARE DELIVERY</span>
            </div>
          </div>

          <nav className="space-y-3">
            {navGroups.map((group, gi) => (
              <div key={gi} className="space-y-0.5">
                {/* Quiet phase label — a section header, not clickable (spec §3) */}
                {group.phase && (
                  <div className="px-2 pt-1.5 pb-0.5 text-[9px] font-bold uppercase tracking-[0.12em] text-stone-400 dark:text-stone-500 select-none">
                    {group.phase}
                  </div>
                )}
                {group.items.map(item => {
                  const Icon = item.icon;
                  const isActive = activeView === item.view;
                  return (
                    <button
                      key={item.view}
                      onClick={() => { setActiveView(item.view); }}
                      className={`w-full flex items-center justify-between p-2 rounded-[var(--r-sm)] text-[12.5px] font-medium transition-colors cursor-pointer ${isActive ? 'bg-[var(--accent-bg)] text-[var(--accent)] font-bold' : 'text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-900'}`}
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <Icon className="w-4 h-4 shrink-0" />
                        <span className="truncate">{item.label}</span>
                      </div>
                      {item.count !== undefined && item.count > 0 && (
                        <span className="bg-red-500 text-white rounded-full text-[9px] font-bold px-1.5 py-0.2 shrink-0">
                          {item.count}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            ))}

            {/* Settings sits below the phase groups */}
            <div className="pt-2 mt-2 border-t border-stone-200 dark:border-stone-850">
              <button
                onClick={() => setActiveView('settings')}
                className={`w-full flex items-center gap-2.5 p-2 rounded-[var(--r-sm)] text-[12.5px] font-medium transition-colors cursor-pointer ${activeView === 'settings' ? 'bg-[var(--accent-bg)] text-[var(--accent)] font-bold' : 'text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-900'}`}
              >
                <Settings className="w-4 h-4 shrink-0" />
                <span className="truncate">Settings</span>
              </button>
            </div>
          </nav>
        </div>

        {/* Audit Lock posture info */}
        <div className="p-4 border-t border-stone-200 dark:border-stone-850 space-y-2.5">
          <div className="p-2.5 rounded bg-amber-500/10 text-amber-500 border border-amber-500/20 text-[10px] leading-snug font-sans flex items-start gap-1.5">
            <Lock className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            <span>
              Tenant isolated local sandbox environment. Data zero-retention active.
            </span>
          </div>

          <div className="flex items-center justify-between text-xs text-stone-550 border-t border-stone-150 dark:border-stone-850 pt-3">
            <span>Theme toggle</span>
            <button
              onClick={toggleTheme}
              className="p-1 rounded bg-stone-100 dark:bg-stone-850 hover:bg-stone-200 border cursor-pointer border-stone-200 dark:border-stone-800 text-stone-600 dark:text-stone-300"
            >
              {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
          </div>

          <button
            onClick={onLogout}
            className="w-full flex items-center justify-center gap-2 p-2 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 text-xs font-medium text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-900 hover:text-red-600 dark:hover:text-red-400 cursor-pointer transition-colors"
          >
            <LogOut className="w-4 h-4" />
            <span>Log out</span>
          </button>
        </div>
      </aside>

      {/* Main Workspace Frame */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden">
        
        {/* Global master header */}
        <header className="border-b border-stone-200/50 dark:border-stone-850/50 px-6 py-4 flex items-center justify-between shrink-0 bg-[var(--bg-app)] z-10 backdrop-blur-md">
          <div className="flex items-center gap-2 min-w-0">
            <ProjectSwitcher />
            {activeView !== 'projects' && activeProjectId && (
              <>
                <span className="text-stone-300 dark:text-stone-700">/</span>
                <h1 className="text-sm font-medium text-stone-500 dark:text-stone-400 capitalize tracking-tight">
                  {activeView}
                </h1>
              </>
            )}
          </div>

          <div className="flex items-center gap-3">
            {/* Global keyboard prompt search mockup */}
            <button
              onClick={() => setShowCommandBar(true)}
              className="px-3 py-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 hover:border-stone-400 bg-stone-50/50 dark:bg-stone-900/60 hidden md:flex items-center gap-4 text-xs text-stone-400 cursor-pointer"
            >
              <span className="font-sans">⌘K Command & query memory</span>
              <kbd className="text-[10px] font-mono bg-stone-100 dark:bg-stone-800 p-0.5 px-1 rounded uppercase">
                ⌘K
              </kbd>
            </button>

            {/* The product's two triage queues (spec §3): task Verdicts + agent Reviews */}
            <button
              onClick={() => setActiveView('verdicts')}
              className="p-1 px-2.5 rounded border border-stone-200 dark:border-stone-800 hover:bg-stone-150 dark:hover:bg-stone-800 text-stone-600 dark:text-stone-300 relative text-xs flex items-center gap-1.5 cursor-pointer"
              title="Task verdicts — conflicts & duplicates awaiting confirmation"
            >
              <Bell className="w-4 h-4" />
              <span className="hidden lg:inline">Verdicts</span>
              {getTriageCount() > 0 && (
                <span className="ml-0.5 min-w-[16px] text-center bg-red-500 text-white rounded-full text-[9px] font-bold px-1 py-0.2">
                  {getTriageCount()}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveView('reviews')}
              className="p-1 px-2.5 rounded border border-stone-200 dark:border-stone-800 hover:bg-stone-150 dark:hover:bg-stone-800 text-stone-600 dark:text-stone-300 relative text-xs flex items-center gap-1.5 cursor-pointer"
              title="Reviews — agent implementations awaiting requirement validation"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span className="hidden lg:inline">Reviews</span>
              {getReviewCount() > 0 && (
                <span className="ml-0.5 min-w-[16px] text-center bg-[var(--accent)] text-white rounded-full text-[9px] font-bold px-1 py-0.2">
                  {getReviewCount()}
                </span>
              )}
            </button>
            
            <button
              onClick={toggleTheme}
              className="md:hidden p-1 rounded border cursor-pointer border-stone-200 dark:border-stone-800 text-stone-600 dark:text-stone-300"
            >
              {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
          </div>
        </header>

        {/* Master Content View Port */}
        <div className="flex-1 overflow-y-auto p-6 max-h-[calc(100vh-64px)] relative">
          
          {activeView === 'projects' || !activeProjectId ? (
            <ProjectsView />
          ) : loading ? (
            <div className="h-full flex flex-col items-center justify-center space-y-2 text-stone-400">
              <div className="w-6 h-6 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
              <p className="font-mono text-xs">Loading your board…</p>
            </div>
          ) : (
            <AnimatePresence mode="wait">
              <motion.div
                key={activeView}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.15 }}
                className="h-full"
              >
                {activeView === 'board' && <DashboardView />}
                {activeView === 'verdicts' && <VerdictsView />}
                {activeView === 'runs' && <RunsView />}
                {activeView === 'reviews' && <ReviewsView />}
                {activeView === 'delivery' && <DeliveryView />}
                {activeView === 'memory' && <AskView />}
                {activeView === 'impact' && <ImpactGraph />}
                {activeView === 'author' && <AuthorView />}
                {activeView === 'sources' && <SourcesView />}
                {activeView === 'deprecate' && <DeprecateView />}
                {activeView === 'settings' && <SettingsView />}
              </motion.div>
            </AnimatePresence>
          )}

        </div>
      </main>

      {/* Floating Detailed Drawer */}
      <Drawer />

      {/* Quick universal command deck */}
      {showCommandBar && (
        <CommandBar onClose={() => setShowCommandBar(false)} />
      )}

      {/* Bottom notifications overlay */}
      <Toast />

    </div>
  );
}
