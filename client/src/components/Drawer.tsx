import React, { useState, useEffect } from 'react';
import { X, Maximize2, Minimize2, Trash2, HelpCircle, GitPullRequest, Bookmark, History, FileText, Check, AlertTriangle } from 'lucide-react';
import { useProject } from '../context/ProjectContext.js';
import { VerdictBadge } from './VerdictBadge.js';
import { CitationChip } from './CitationChip.js';
import { AssigneeSelect } from './AssigneeSelect.js';
import { resolveAssignee, isAgentRef, agentKindStyle } from '../lib/assignee.js';
import { Status, Priority } from '../types.js';

export const Drawer: React.FC = () => {
  const { selectedCardId, setSelectedCardId, state, updateItem, deleteItem, resolveVerdict, askQuestion } = useProject();
  const [activeTab, setActiveTab] = useState<'overview' | 'ask' | 'impact' | 'history' | 'citations'>('overview');
  const [isWide, setIsWide] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [chatHistory, setChatHistory] = useState<Array<{ sender: 'user' | 'ai'; text: string; citations?: any[] }>>([]);
  const [loadingChat, setLoadingChat] = useState(false);

  // Editing state variables
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<Status>('inbox');
  const [priority, setPriority] = useState<Priority>('P2');
  const [area, setArea] = useState("general");
  const [assignee, setAssignee] = useState("AM");

  const item = state?.items.find(i => i.id === selectedCardId);

  useEffect(() => {
    if (item) {
      setTitle(item.title);
      setDescription(item.description);
      setStatus(item.status);
      setPriority(item.priority);
      setArea(item.area);
      setAssignee(item.assignee);
      // Reset Chat History when a different item is clicked
      setChatHistory([
        { sender: 'ai', text: `I am ready. Ask me anything in-context about Backlog Card #${item.id} ("${item.title}"). I can scan dependencies, evaluate risk relative to Dec #4 or Dec #12, or draft subtasks.` }
      ]);
    }
  }, [selectedCardId, item]);

  if (!selectedCardId || !item) return null;

  const handleFieldSave = async (fieldName: string, value: any) => {
    await updateItem(item.id, { [fieldName]: value });
  };

  const handleDelete = async () => {
    if (confirm("Are you sure you want to archive this backlog card?")) {
      setSelectedCardId(null);
      await deleteItem(item.id);
    }
  };

  const handleChatSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim()) return;

    const userMsg = chatInput;
    setChatInput("");
    setChatHistory(prev => [...prev, { sender: 'user', text: userMsg }]);
    setLoadingChat(true);

    try {
      const data = await askQuestion(userMsg, item.id);
      setChatHistory(prev => [...prev, {
        sender: 'ai',
        text: data.answer,
        citations: data.citations
      }]);
    } catch (err) {
      setChatHistory(prev => [...prev, { sender: 'ai', text: "Couldn't reach the AI provider. Check your key in Settings ▸ Data & AI." }]);
    } finally {
      setLoadingChat(false);
    }
  };

  const getSourceIconName = (type: string) => {
    if (type === 'sheet') return '⊞ Sheet';
    if (type === 'call') return '🎙 Transcript';
    if (type === 'ticket') return '🎫 Ticket';
    if (type === 'email') return '✉ Email';
    return '⤓ File';
  };

  const verdict = item.verdict;

  // People suggestions: human assignees already used across this project's cards
  // (agent refs are excluded — agents come from the workspace catalog).
  const assigneeOptions = Array.from(
    new Set([...(state?.items.map(i => i.assignee) || []), assignee].filter(v => v && !isAgentRef(v)))
  );

  const resolvedAssignee = resolveAssignee(assignee, state?.agents || []);

  return (
    <div className={`fixed top-0 right-0 h-full bg-[var(--bg-card)] border-l border-stone-200 dark:border-stone-850 shadow-[var(--shadow-2)] z-45 flex flex-col transition-all duration-300 ease-out ${isWide ? 'w-full md:w-[640px]' : 'w-full md:w-[480px]'}`}>
      
      {/* Drawer Head */}
      <div className="p-4 border-b border-stone-200 dark:border-stone-850 bg-stone-100/40 dark:bg-stone-900/40 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm text-stone-400 font-bold">#{item.id}</span>
          <span className="text-stone-300">|</span>
          <span className="bg-stone-200 dark:bg-stone-800 text-stone-700 dark:text-stone-300 px-2 py-0.5 rounded text-[11px] font-mono tracking-wide uppercase">
            {area}
          </span>
        </div>

        <div className="flex items-center gap-2 text-stone-500">
          <button
            onClick={() => setIsWide(!isWide)}
            className="p-1.5 rounded-[var(--r-sm)] hover:bg-stone-100 dark:hover:bg-stone-800 hover:text-stone-800 dark:hover:text-stone-250 cursor-pointer"
            title={isWide ? "Narrow View" : "Expand View"}
          >
            {isWide ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
          <button
            onClick={handleDelete}
            className="p-1.5 rounded-[var(--r-sm)] hover:bg-red-100 dark:hover:bg-red-950 hover:text-red-500 cursor-pointer"
            title="Archive Item"
          >
            <Trash2 className="w-4 h-4" />
          </button>
          <button
            onClick={() => setSelectedCardId(null)}
            className="p-1.5 rounded-[var(--r-sm)] hover:bg-stone-100 dark:hover:bg-stone-800 hover:text-stone-800 dark:hover:text-stone-250 cursor-pointer"
            title="Close Drawer"
          >
            <X className="w-4.5 h-4.5" />
          </button>
        </div>
      </div>

      {/* Dynamic Title Input */}
      <div className="p-5 pb-2">
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={() => handleFieldSave('title', title)}
          className="w-full bg-transparent font-sans font-bold text-lg text-stone-900 dark:text-stone-50 focus:outline-none focus:border-b focus:border-stone-300 focus:pb-[2px]"
          placeholder="Card Title"
        />
      </div>

      {/* Tabs list */}
      <div className="px-5 border-b border-stone-200 dark:border-stone-850 flex items-end gap-1.5 text-xs">
        {(['overview', 'ask', 'impact', 'history', 'citations'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`py-2 px-3 border-b-2 font-medium capitalize cursor-pointer transition-colors ${activeTab === tab ? 'border-[var(--accent)] text-[var(--accent)] font-bold' : 'border-transparent text-stone-500 hover:text-stone-800 dark:hover:text-stone-300'}`}
          >
            {tab === 'ask' ? 'Ask AI' : tab}
          </button>
        ))}
      </div>

      {/* Drawer Body (Scrollable Panel) */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        
        {/* TAB 1: OVERVIEW */}
        {activeTab === 'overview' && (
          <div className="space-y-5">
            
            {/* Verdict Alert Alert */}
            {verdict && verdict.type !== 'net-new' && (
              <div className={`p-4 rounded-[var(--r-md)] border text-xs leading-normal relative ${verdict.type === 'conflict' ? 'border-red-200 bg-red-50/25 dark:border-red-950 dark:bg-red-950/10' : 'border-amber-200 bg-amber-50/20 dark:border-amber-950 dark:bg-amber-950/5'}`}>
                <div className="flex items-center gap-2 font-semibold text-stone-950 dark:text-stone-50 mb-1.5">
                  <AlertTriangle className={`w-4 h-4 ${verdict.type === 'conflict' ? 'text-red-500' : 'text-amber-500'}`} />
                  <span className="uppercase tracking-wide text-[10px] font-bold">
                    System Alert: {verdict.type} Detected ({verdict.confidence}% confidence)
                  </span>
                </div>
                
                <p className="text-stone-700 dark:text-stone-300 mb-3.5">
                  {verdict.message}
                </p>

                {verdict.citation && (
                  <div className="p-3 bg-stone-100 dark:bg-stone-900 border border-stone-200 dark:border-stone-800 text-stone-600 dark:text-stone-300 rounded font-mono text-[10px] mb-3 leading-relaxed">
                    <p className="font-sans font-bold text-stone-700 dark:text-stone-200 mb-1">
                      Cited anchor: {verdict.citation.id} ({verdict.citation.title})
                    </p>
                    “{verdict.citation.snippet}”
                  </div>
                )}

                {/* Inline Resolve Quick Options */}
                <div className="flex items-center gap-2 flex-wrap">
                  {verdict.type === 'conflict' ? (
                    <>
                      <button
                        onClick={() => resolveVerdict(item.id, 'supersede', verdict.candidates[0]?.id)}
                        className="p-1.5 px-3 rounded text-[10px] font-bold bg-stone-900 border border-stone-850 dark:bg-stone-100 dark:text-stone-900 hover:opacity-90 cursor-pointer"
                      >
                        Supersede Dec #{verdict.candidates[0]?.id}
                      </button>
                      <button
                        onClick={() => resolveVerdict(item.id, 'dismiss')}
                        className="p-1.5 px-3 rounded text-[10px] font-bold border border-stone-250 hover:bg-stone-100 dark:hover:bg-stone-850 text-stone-600 dark:text-stone-300 cursor-pointer"
                      >
                        Dismiss Flag
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={() => resolveVerdict(item.id, 'merge', verdict.candidates[0]?.id)}
                        className="p-1.5 px-3 rounded text-[10px] text-white font-bold bg-stone-900 dark:bg-stone-100 dark:text-stone-900 hover:opacity-90 cursor-pointer"
                      >
                        Merge with #{verdict.candidates[0]?.id}
                      </button>
                      <button
                        onClick={() => resolveVerdict(item.id, 'dismiss')}
                        className="p-1.5 px-3 rounded text-[10px] font-bold border border-stone-250 hover:bg-stone-100 dark:hover:bg-stone-800 text-stone-600 dark:text-stone-300 cursor-pointer"
                      >
                        Keep Both
                      </button>
                    </>
                  )}
                </div>
              </div>
            )}

            {/* Quick Metadata fields */}
            <div className="grid grid-cols-2 gap-4 p-4 border border-stone-200 dark:border-stone-850 bg-stone-50/40 dark:bg-stone-900/40 rounded-[var(--r-md)] text-xs">
              <div>
                <span className="text-stone-400 block mb-1">Status</span>
                <select
                  value={status}
                  onChange={(e) => { setStatus(e.target.value as Status); handleFieldSave('status', e.target.value); }}
                  className="w-full bg-white dark:bg-stone-950 p-1.5 rounded font-medium border border-stone-200 dark:border-stone-800 focus:outline-none focus:border-[var(--accent)] text-stone-850 dark:text-stone-200"
                >
                  <option value="inbox">📥 Inbox</option>
                  <option value="next">🎯 Next Up</option>
                  <option value="in_progress">⚡ In Progress</option>
                  <option value="done">✓ Done</option>
                </select>
              </div>

              <div>
                <span className="text-stone-400 block mb-1">Priority</span>
                <select
                  value={priority}
                  onChange={(e) => { setPriority(e.target.value as Priority); handleFieldSave('priority', e.target.value); }}
                  className="w-full bg-white dark:bg-stone-950 p-1.5 rounded font-medium border border-stone-200 dark:border-stone-800 focus:outline-none focus:border-[var(--accent)] text-stone-850 dark:text-stone-200"
                >
                  <option value="P0">★ P0 (Emergency)</option>
                  <option value="P1">★ P1 (Critical)</option>
                  <option value="P2">★ P2 (High)</option>
                  <option value="P3">★ P3 (Medium)</option>
                </select>
              </div>

              <div>
                <span className="text-stone-400 block mb-1">Area tag</span>
                <input
                  type="text"
                  value={area}
                  onChange={(e) => setArea(e.target.value)}
                  onBlur={() => handleFieldSave('area', area)}
                  className="w-full bg-white dark:bg-stone-950 p-1.5 rounded border border-stone-200 dark:border-stone-800 focus:outline-none focus:border-[var(--accent)] text-stone-800 dark:text-stone-200 font-mono text-[11px]"
                />
              </div>

              <div>
                <span className="text-stone-400 block mb-1">Assignee</span>
                <AssigneeSelect
                  value={assignee}
                  people={assigneeOptions}
                  agents={state?.agents || []}
                  placeholder="Unassigned"
                  onChange={(v) => { setAssignee(v); handleFieldSave('assignee', v); }}
                />
                {resolvedAssignee.kind === 'agent' && (
                  <span className="mt-1 flex items-center gap-1 text-[10px] text-violet-600 dark:text-violet-300">
                    {(() => {
                      const Icon = agentKindStyle(resolvedAssignee.agent?.kind || 'custom').icon;
                      return <Icon className="w-3 h-3" />;
                    })()}
                    AI agent{resolvedAssignee.agent?.description ? ` · ${resolvedAssignee.agent.description}` : ''}
                  </span>
                )}
              </div>
            </div>

            {/* Description editing area */}
            <div className="space-y-1.5">
              <span className="text-xs font-semibold text-stone-400 uppercase tracking-wider block">Description</span>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                onBlur={() => handleFieldSave('description', description)}
                rows={5}
                className="w-full bg-stone-50 dark:bg-stone-950 border border-stone-200 dark:border-stone-850 rounded-[var(--r-md)] p-3 text-xs leading-relaxed focus:outline-none focus:border-[var(--accent)] font-sans text-stone-800 dark:text-stone-250"
                placeholder="Write specific requirements / architectural briefs here..."
              />
            </div>

            {/* Ingestion trace snippet if loaded */}
            {item.source && (
              <div className="p-3 border border-stone-200 dark:border-stone-800 bg-stone-100/30 dark:bg-stone-950/20 rounded text-xs space-y-1">
                <div className="flex items-center gap-1 font-semibold text-stone-500">
                  <FileText className="w-3.5 h-3.5 text-sky-500" />
                  <span>Ingested from {getSourceIconName(item.source.type)}: "{item.source.name}"</span>
                </div>
                {item.source.snippet && (
                  <p className="font-mono text-[11px] text-stone-500 italic mt-1 bg-stone-100 dark:bg-stone-900 p-2 rounded">
                    “{item.source.snippet}”
                  </p>
                )}
              </div>
            )}

            {/* Subtask Checklists (Section 4.1 "subtsk") */}
            <div className="space-y-2">
              <span className="text-xs font-semibold text-stone-400 uppercase tracking-wider block">Subtask checklist</span>
              <div className="space-y-1 bg-stone-50/20 dark:bg-stone-900/20 border border-stone-150 dark:border-stone-850 p-3 rounded-[var(--r-md)] text-xs select-none">
                <div className="flex items-center gap-2 py-1">
                  <input type="checkbox" defaultChecked className="rounded text-[var(--accent)]" />
                  <span className="text-stone-500 line-through">Draft security schema guidelines</span>
                </div>
                <div className="flex items-center gap-2 py-1">
                  <input type="checkbox" defaultChecked className="rounded text-[var(--accent)]" />
                  <span className="text-stone-500 line-through">Run integration checking suite</span>
                </div>
                <div className="flex items-center gap-2 py-1">
                  <input type="checkbox" className="rounded text-[var(--accent)]" />
                  <span className="text-stone-800 dark:text-stone-300">Publish unified spec for controllers</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: ASK (Contextual AI chat query scoped to this card) */}
        {activeTab === 'ask' && (
          <div className="h-full flex flex-col justify-between block">
            <div className="space-y-4 max-h-[400px] overflow-y-auto pr-2 pb-14 text-xs">
              {chatHistory.map((cm, idx) => (
                <div
                  key={idx}
                  className={`p-3 rounded-[var(--r-md)] leading-relaxed space-y-2 max-w-[85%] ${cm.sender === 'user' ? 'bg-[var(--accent-bg)] text-[var(--accent)] font-medium self-end ml-auto' : 'bg-stone-100 dark:bg-stone-900 text-stone-800 dark:text-stone-250'}`}
                >
                  <p className="font-sans whitespace-pre-line">{cm.text}</p>
                  
                  {cm.citations && cm.citations.length > 0 && (
                    <div className="pt-2 border-t border-stone-200 dark:border-stone-800 flex items-center gap-1.5 flex-wrap">
                      <span className="text-[10px] text-stone-400 font-mono">Cites:</span>
                      {cm.citations.map((cc, cIdx) => (
                        <CitationChip
                          key={cIdx}
                          id={cc.id}
                          type={cc.type}
                          title={cc.title}
                          snippet={cc.snippet}
                        />
                      ))}
                    </div>
                  )}
                </div>
              ))}
              
              {loadingChat && (
                <div className="flex items-center gap-2 text-stone-450 text-[11px] italic">
                  <div className="w-2 h-2 rounded-full bg-[var(--accent)] animate-bounce" />
                  <div className="w-2 h-2 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:0.2s]" />
                  <div className="w-2 h-2 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:0.4s]" />
                  <span>Scanning memory records...</span>
                </div>
              )}
            </div>

            {/* Input form */}
            <form onSubmit={handleChatSend} className="mt-4 flex gap-2">
              <input
                type="text"
                placeholder={`Ask Dec-Memory why we built custom SSO...`}
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                className="flex-1 bg-stone-100 dark:bg-stone-950 border border-stone-200 dark:border-stone-800 p-2 py-1.5 text-xs rounded-[var(--r-sm)] focus:outline-none focus:border-[var(--accent)] placeholder-stone-400 dark:placeholder-stone-500 text-stone-800 dark:text-stone-100"
              />
              <button
                type="submit"
                className="p-1 px-3 bg-[var(--accent)] text-white text-xs font-semibold rounded-[var(--r-sm)] hover:opacity-95 cursor-pointer"
              >
                Ask
              </button>
            </form>
          </div>
        )}

        {/* TAB 3: IMPACT */}
        {activeTab === 'impact' && (
          <div className="space-y-4 text-xs">
            <h4 className="font-semibold uppercase text-stone-400">Target connections</h4>
            
            {verdict && verdict.candidates && verdict.candidates.length > 0 ? (
              <div className="space-y-3">
                <p className="text-stone-500 leading-normal">
                  The following memory nodes share functional dependencies or direct requirements with this task card:
                </p>
                {verdict.candidates.map((cand, candIdx) => (
                  <div key={candIdx} className="p-3 border rounded bg-stone-50/20 dark:bg-stone-900/10 border-stone-200 dark:border-stone-800 flex items-center justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-2">
                      <Bookmark className="w-4 h-4 text-amber-500" />
                      <div>
                        <span className="font-semibold block text-stone-850 dark:text-stone-200">
                          {cand.type === 'decision' ? `Decision #${cand.id}` : `Card #${cand.id}`}
                        </span>
                        <span className="text-stone-500 text-[11px] font-sans">{cand.title}</span>
                      </div>
                    </div>
                    <span className="font-mono text-[10px] font-extrabold text-amber-600 dark:text-amber-400 bg-amber-100/50 dark:bg-amber-950/40 px-1.5 py-0.5 rounded">
                      {cand.confidence}% overlap
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-stone-500 leading-relaxed font-sans">
                No direct conflict candidates mapped in memory. This card is currently evaluated as Net-New (clean land).
              </p>
            )}

            <div className="pt-4 border-t border-stone-200 dark:border-stone-850">
              <span className="text-stone-400 block mb-1">Access security bounds</span>
              <p className="text-stone-600 dark:text-stone-400 leading-relaxed font-sans">
                This backlog item operates in the core <strong className="font-mono text-[11px] text-[var(--accent)] font-semibold">{area}</strong> environment subsystem. Changes to password directories require architectural review of Dec #4.
              </p>
            </div>
          </div>
        )}

        {/* TAB 4: HISTORY */}
        {activeTab === 'history' && (
          <div className="space-y-4 text-xs font-sans">
            <h4 className="font-semibold uppercase text-stone-400 flex items-center gap-1.5">
              <History className="w-4 h-4 text-emerald-500" />
              <span>Card Audit Trail</span>
            </h4>
            
            <div className="border-l border-stone-200 dark:border-stone-800 pl-4 ml-2 space-y-4 relative">
              <div className="relative">
                <div className="absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full bg-emerald-500" />
                <span className="text-[11px] font-mono text-stone-400">June 2, 2026 UTC</span>
                <p className="text-stone-800 dark:text-stone-200 font-semibold mt-0.5">Card Created</p>
                <p className="text-stone-500">Proposed by AM via Web interface intake workflow.</p>
              </div>

              <div className="relative">
                <div className="absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full bg-indigo-500" />
                <span className="text-[11px] font-mono text-stone-400">June 2, 2026 UTC</span>
                <p className="text-stone-800 dark:text-stone-200 font-semibold mt-0.5">Automated Verdict check resolved</p>
                <p className="text-stone-500">Checked against existing items and past decisions in memory.</p>
              </div>
            </div>
          </div>
        )}

        {/* TAB 5: CITATIONS */}
        {activeTab === 'citations' && (
          <div className="space-y-4 text-xs leading-normal font-sans">
            <h4 className="font-semibold uppercase text-stone-400 flex items-center gap-1.5">
              <FileText className="w-4 h-4 text-sky-500" />
              <span>Source citations</span>
            </h4>
            
            {verdict && verdict.citation ? (
              <div className="space-y-3.5">
                <p className="text-stone-500">
                  Requirements in this card are directly bounded or derived from the following historical records:
                </p>
                <div className="p-4 rounded-[var(--r-md)] bg-stone-100 dark:bg-stone-900 border border-stone-200 dark:border-stone-850 text-stone-600 dark:text-stone-300 font-mono text-[11px] leading-relaxed">
                  <div className="flex items-center gap-2 text-stone-500 dark:text-stone-400 font-semibold font-sans mb-1.5">
                    <span>Target memory anchor:</span>
                    <span className="bg-stone-200 dark:bg-white/20 px-1 py-0.2 rounded text-[10px]">{verdict.citation.id}</span>
                    <span>{verdict.citation.title}</span>
                  </div>
                  <p className="text-stone-600 dark:text-stone-300">
                    “{verdict.citation.snippet}”
                  </p>
                </div>
              </div>
            ) : (
              <p className="text-stone-500 leading-relaxed font-sans">
                No external citation records synced. This represents self-contained custom requirement formulations.
              </p>
            )}
          </div>
        )}

      </div>

      {/* Drawer foot */}
      <div className="p-4 border-t border-stone-200 dark:border-stone-850 bg-stone-100/30 dark:bg-stone-900/30 flex items-center justify-between text-[11px] font-mono text-stone-500">
        <span>🔒 local tenant memory isolated</span>
        <span>Esc to close</span>
      </div>

    </div>
  );
};
