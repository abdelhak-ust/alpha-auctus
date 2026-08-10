import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check, Search, Plus, UserPlus } from 'lucide-react';
import { Agent } from '../types.js';
import { useProject } from '../context/ProjectContext.js';
import { resolveAssignee, agentRef, agentIdFromRef, isAgentRef, agentKindStyle } from '../lib/assignee.js';

interface AssigneeSelectProps {
  value: string;
  onChange: (value: string) => void;
  people: string[];
  agents: Agent[];
  placeholder?: string;
}

type Row =
  | { type: 'human'; value: string }
  | { type: 'human-create'; value: string }
  | { type: 'agent'; agent: Agent }
  | { type: 'agent-create'; value: string };

export const AssigneeSelect: React.FC<AssigneeSelectProps> = ({
  value,
  onChange,
  people,
  agents,
  placeholder = 'Unassigned'
}) => {
  const { createAgent } = useProject();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [highlight, setHighlight] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery('');
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery('');
      setHighlight(0);
      const t = setTimeout(() => inputRef.current?.focus(), 0);
      return () => clearTimeout(t);
    }
  }, [open]);

  const q = query.trim().toLowerCase();
  const filteredPeople = people.filter(p => p.toLowerCase().includes(q));
  const filteredAgents = agents.filter(a => a.name.toLowerCase().includes(q));
  const humanExact = people.some(p => p.toLowerCase() === q);
  const agentExact = agents.some(a => a.name.toLowerCase() === q);
  const showHumanCreate = q.length > 0 && !humanExact;
  const showAgentCreate = q.length > 0 && !agentExact;

  const rows: Row[] = [
    ...filteredPeople.map(p => ({ type: 'human' as const, value: p })),
    ...(showHumanCreate ? [{ type: 'human-create' as const, value: query.trim() }] : []),
    ...filteredAgents.map(a => ({ type: 'agent' as const, agent: a })),
    ...(showAgentCreate ? [{ type: 'agent-create' as const, value: query.trim() }] : [])
  ];

  const close = () => { setOpen(false); setQuery(''); };

  const choose = async (row: Row) => {
    if (row.type === 'human') {
      onChange(row.value);
      close();
    } else if (row.type === 'human-create') {
      onChange(row.value);
      close();
    } else if (row.type === 'agent') {
      onChange(agentRef(row.agent.id));
      close();
    } else if (row.type === 'agent-create') {
      const agent = await createAgent(row.value);
      onChange(agentRef(agent.id));
      close();
    }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlight(h => Math.min(h + 1, rows.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight(h => Math.max(h - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const r = rows[highlight];
      if (r) choose(r);
    } else if (e.key === 'Escape') {
      close();
    }
  };

  const resolved = resolveAssignee(value, agents);

  // Index ranges for rendering group headers in the right places.
  const peopleCount = filteredPeople.length + (showHumanCreate ? 1 : 0);

  const isCurrent = (row: Row): boolean => {
    if (row.type === 'human') return !isAgentRef(value) && value === row.value;
    if (row.type === 'agent') return isAgentRef(value) && agentIdFromRef(value) === row.agent.id;
    return false;
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between gap-1 bg-white dark:bg-stone-950 p-1.5 rounded border border-stone-200 dark:border-stone-800 focus:outline-none focus:border-[var(--accent)] cursor-pointer"
      >
        {value ? (
          resolved.kind === 'agent' ? (
            <span className="flex items-center gap-1.5 min-w-0">
              {(() => {
                const Icon = agentKindStyle(resolved.agent?.kind || 'custom').icon;
                return <Icon className="w-3.5 h-3.5 text-violet-500 shrink-0" />;
              })()}
              <span className="truncate text-stone-800 dark:text-stone-200 font-medium">{resolved.label}</span>
            </span>
          ) : (
            <span className="truncate text-stone-800 dark:text-stone-200 uppercase font-bold">{resolved.label}</span>
          )
        ) : (
          <span className="truncate text-stone-400">{placeholder}</span>
        )}
        <ChevronDown className={`w-3.5 h-3.5 text-stone-400 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 rounded-[var(--r-md)] shadow-[var(--shadow-2)] overflow-hidden">
          <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-stone-150 dark:border-stone-850">
            <Search className="w-3.5 h-3.5 text-stone-400 shrink-0" />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => { setQuery(e.target.value); setHighlight(0); }}
              onKeyDown={onKeyDown}
              placeholder="Search people & agents…"
              className="w-full bg-transparent text-xs text-stone-800 dark:text-stone-200 placeholder-stone-400 dark:placeholder-stone-500 focus:outline-none"
            />
          </div>
          <div className="max-h-60 overflow-y-auto py-1">
            {rows.length === 0 && (
              <div className="px-2.5 py-2 text-[11px] text-stone-400">No matches</div>
            )}

            {peopleCount > 0 && (
              <div className="px-2.5 pt-1 pb-0.5 text-[10px] font-semibold uppercase tracking-wider text-stone-400">People</div>
            )}

            {rows.map((r, idx) => {
              // Insert the AI Agents header right before the first agent row.
              const showAgentHeader =
                (r.type === 'agent' || r.type === 'agent-create') &&
                idx === peopleCount;

              return (
                <React.Fragment key={r.type + '-' + (r.type === 'agent' ? r.agent.id : r.value)}>
                  {showAgentHeader && (
                    <div className="px-2.5 pt-2 pb-0.5 text-[10px] font-semibold uppercase tracking-wider text-stone-400">AI Agents</div>
                  )}
                  <button
                    type="button"
                    onMouseEnter={() => setHighlight(idx)}
                    onClick={() => choose(r)}
                    className={`w-full flex items-center justify-between gap-2 px-2.5 py-1.5 text-left text-xs cursor-pointer ${idx === highlight ? 'bg-[var(--accent-bg)]' : 'hover:bg-stone-100 dark:hover:bg-stone-850'}`}
                  >
                    {r.type === 'human' && (
                      <span className={`uppercase font-bold ${idx === highlight ? 'text-[var(--accent)]' : 'text-stone-700 dark:text-stone-300'}`}>
                        {r.value}
                      </span>
                    )}
                    {r.type === 'human-create' && (
                      <span className="flex items-center gap-1.5 text-[var(--accent)] font-medium">
                        <UserPlus className="w-3.5 h-3.5" /> Add person “{r.value}”
                      </span>
                    )}
                    {r.type === 'agent' && (() => {
                      const style = agentKindStyle(r.agent.kind);
                      const Icon = style.icon;
                      return (
                        <span className="flex items-center gap-2 min-w-0">
                          <span className={`flex items-center justify-center w-5 h-5 rounded shrink-0 ${style.tint}`}>
                            <Icon className="w-3 h-3" />
                          </span>
                          <span className={`truncate font-medium ${idx === highlight ? 'text-[var(--accent)]' : 'text-stone-700 dark:text-stone-300'}`}>
                            {r.agent.name}
                          </span>
                        </span>
                      );
                    })()}
                    {r.type === 'agent-create' && (
                      <span className="flex items-center gap-1.5 text-violet-600 dark:text-violet-300 font-medium">
                        <Plus className="w-3.5 h-3.5" /> Add custom agent “{r.value}”
                      </span>
                    )}
                    {isCurrent(r) && <Check className="w-3.5 h-3.5 text-[var(--accent)] shrink-0" />}
                  </button>
                </React.Fragment>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
