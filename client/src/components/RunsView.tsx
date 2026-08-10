import React, { useMemo, useState } from 'react';
import {
  Cog, FileCode2, Terminal, StickyNote, Ban, StopCircle, UserRoundCog,
  CornerDownLeft, ChevronRight, Activity
} from 'lucide-react';
import { useProject } from '../context/ProjectContext.js';
import { buildRuns } from '../lib/delivery.js';
import { RunStatusBadge, ACDot } from './StatusBadges.js';
import { agentKindStyle } from '../lib/assignee.js';
import { Run, RunStatus } from '../types.js';

type RunFilter = 'active' | 'done' | 'blocked' | 'all';

const activityIcon: Record<string, any> = {
  read: FileCode2, edit: FileCode2, run: Terminal, note: StickyNote, blocked: Ban,
};

function RunDetail({ run }: { run: Run }) {
  const { triggerToast } = useProject();
  const [answer, setAnswer] = useState('');
  const style = agentKindStyle(run.agentKind);
  const AgentIcon = style.icon;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-stone-200 dark:border-stone-850 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-xs text-stone-400 font-bold">#{run.itemId}</span>
          <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100 truncate">{run.itemTitle}</h3>
          <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold ${style.tint}`}>
            <AgentIcon className="w-3 h-3" /> {run.agentName}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <RunStatusBadge status={run.status} />
          {run.status === 'running' && (
            <button onClick={() => triggerToast(`Stopped run for #${run.itemId} — work-in-progress kept.`)}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 text-[11px] font-medium text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-900 cursor-pointer">
              <StopCircle className="w-3.5 h-3.5" /> Stop
            </button>
          )}
        </div>
      </div>

      {/* Progress */}
      {run.status !== 'queued' && (
        <div className="px-4 pt-3">
          <div className="flex items-center justify-between text-[11px] text-stone-500 mb-1">
            <span>{run.files.length} files · {run.commands} cmds</span>
            <span className="font-mono">{run.progress}%</span>
          </div>
          <div className="h-1.5 rounded-full bg-stone-150 dark:bg-stone-850 overflow-hidden">
            <div className="h-full rounded-full bg-[var(--accent)] transition-all" style={{ width: `${run.progress}%` }} />
          </div>
        </div>
      )}

      {/* Task context sent (collapsed disclosure per §4.12) */}
      <div className="px-4 pt-3">
        <details className="group">
          <summary className="flex items-center gap-1.5 text-[11px] text-stone-500 cursor-pointer select-none list-none">
            <ChevronRight className="w-3 h-3 transition-transform group-open:rotate-90" />
            Task context sent
          </summary>
          <p className="mt-1.5 pl-4 text-[11px] text-stone-500 dark:text-stone-400 leading-relaxed">
            requirements · acceptance criteria · related tasks · repo context · prior decisions · citations
          </p>
        </details>
      </div>

      {/* Body: activity + AC tracker */}
      <div className="flex-1 overflow-y-auto grid grid-cols-1 lg:grid-cols-[1fr_240px] gap-4 p-4">
        {/* Live activity stream */}
        <div className="space-y-2 min-w-0">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-stone-400 flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5" /> Activity {run.status === 'running' && <span className="text-[var(--accent)] normal-case font-mono lowercase">live</span>}
          </span>
          {run.activity.length === 0 ? (
            <p className="text-[11px] text-stone-400 italic py-4">Queued — waiting for a runner slot.</p>
          ) : (
            <ol className="space-y-1.5">
              {run.activity.map((a, i) => {
                const Icon = activityIcon[a.kind] || StickyNote;
                const blocked = a.kind === 'blocked';
                return (
                  <li key={i} className={`flex items-start gap-2 text-[11px] leading-relaxed ${blocked ? 'text-amber-700 dark:text-amber-400 font-medium' : 'text-stone-600 dark:text-stone-300'}`}>
                    <span className="font-mono text-stone-400 shrink-0">{a.time}</span>
                    <Icon className={`w-3.5 h-3.5 shrink-0 mt-0.5 ${blocked ? 'text-amber-500' : a.kind === 'run' ? 'text-emerald-500' : 'text-stone-400'}`} />
                    <span className="font-mono break-words">{a.text}</span>
                  </li>
                );
              })}
            </ol>
          )}
        </div>

        {/* Acceptance-criteria tracker — coverage forming in real time */}
        <div className="space-y-2 lg:border-l lg:border-stone-200 lg:dark:border-stone-850 lg:pl-4">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-stone-400">Acceptance criteria</span>
          <ul className="space-y-1.5">
            {run.criteria.map(ac => (
              <li key={ac.id} className="flex items-start gap-2 text-[11px]">
                <span className="mt-0.5"><ACDot state={ac.state} /></span>
                <div className="min-w-0">
                  <span className="font-mono text-stone-400">{ac.id}</span>{' '}
                  <span className={`${ac.state === 'blocked' ? 'text-amber-700 dark:text-amber-400' : 'text-stone-600 dark:text-stone-300'}`}>{ac.label}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Blocking question — first-class (§4.12) */}
      {run.status === 'blocked' && run.blockingQuestion && (
        <div className="mx-4 mb-3 p-3 rounded-[var(--r-md)] border border-amber-300 dark:border-amber-900 bg-amber-50/50 dark:bg-amber-950/20">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold text-amber-800 dark:text-amber-300 mb-1.5">
            <Ban className="w-3.5 h-3.5" /> Blocked — needs your call
          </div>
          <p className="text-xs text-stone-700 dark:text-stone-200 mb-2">“{run.blockingQuestion}”</p>
          <div className="flex gap-2">
            <input value={answer} onChange={e => setAnswer(e.target.value)} placeholder="Answer inline…"
              className="flex-1 bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-800 rounded-[var(--r-sm)] px-2 py-1.5 text-xs focus:outline-none focus:border-[var(--accent)]" />
            <button onClick={() => { if (answer.trim()) { triggerToast(`Answered — run #${run.itemId} resuming.`); setAnswer(''); } }}
              className="inline-flex items-center gap-1 px-3 rounded-[var(--r-sm)] bg-[var(--accent)] text-white text-xs font-semibold hover:opacity-95 cursor-pointer">
              <CornerDownLeft className="w-3.5 h-3.5" /> Continue
            </button>
          </div>
        </div>
      )}

      {/* Self-assessment + controls */}
      <div className="p-4 border-t border-stone-200 dark:border-stone-850 bg-stone-50/50 dark:bg-stone-900/40">
        <p className="text-[11px] text-stone-500 dark:text-stone-400 mb-2">
          <span className="font-semibold text-stone-600 dark:text-stone-300">Agent self-assessment:</span> “{run.selfAssessment}”
          <span className="block mt-0.5 text-stone-400 italic">The agent's own claim — independently checked in Reviews (§4.13).</span>
        </p>
        <div className="flex items-center gap-2 flex-wrap">
          {run.status === 'done' ? (
            <span className="text-[11px] text-[var(--verdict-new-txt)] font-medium">✓ Done · review ready</span>
          ) : (
            <>
              <button onClick={() => triggerToast('Handed to a human — run context carried over.')}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 text-[11px] font-medium text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-900 cursor-pointer">
                <UserRoundCog className="w-3.5 h-3.5" /> Hand to human
              </button>
              <button onClick={() => triggerToast(`Stopped run for #${run.itemId}.`)}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 text-[11px] font-medium text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-900 cursor-pointer">
                <StopCircle className="w-3.5 h-3.5" /> Stop
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export const RunsView: React.FC = () => {
  const { state, setActiveView } = useProject();
  const [filter, setFilter] = useState<RunFilter>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const runs = useMemo(() => buildRuns(state?.items || [], state?.agents || []), [state?.items, state?.agents]);

  const filtered = runs.filter(r => {
    if (filter === 'all') return true;
    if (filter === 'active') return r.status === 'running' || r.status === 'queued';
    if (filter === 'blocked') return r.status === 'blocked';
    return r.status === 'done';
  });

  const selected = runs.find(r => r.id === selectedId) || filtered[0] || null;

  if (runs.length === 0) {
    return (
      <div className="border border-dashed border-stone-250 dark:border-stone-800 rounded-[var(--r-lg)] p-12 text-center text-stone-400 max-w-2xl mx-auto mt-6">
        <Cog className="w-8 h-8 text-stone-300 mx-auto mb-3" />
        <h3 className="font-semibold text-stone-900 dark:text-stone-100 text-sm">No runs yet</h3>
        <p className="text-xs text-stone-500 mt-1 max-w-sm mx-auto leading-relaxed">
          Assign a card to an AI agent (Claude Code in the MVP) and move it forward to launch a run. Live activity, acceptance-criteria coverage, and blocking questions show up here.
        </p>
        <button onClick={() => setActiveView('board')} className="mt-4 px-3 py-1.5 rounded-[var(--r-sm)] bg-[var(--accent)] text-white text-xs font-semibold cursor-pointer">Go to board</button>
      </div>
    );
  }

  const counts = {
    active: runs.filter(r => r.status === 'running' || r.status === 'queued').length,
    blocked: runs.filter(r => r.status === 'blocked').length,
    done: runs.filter(r => r.status === 'done').length,
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-base font-bold text-stone-900 dark:text-stone-50 tracking-tight">Runs</h2>
          <p className="text-xs text-stone-500 dark:text-stone-400">Agent execution, in the open — files, commands, tests, and coverage forming live.</p>
        </div>
        <div className="flex items-center gap-1 text-xs">
          {(['all', 'active', 'blocked', 'done'] as RunFilter[]).map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-2.5 py-1 rounded-[var(--r-sm)] capitalize font-medium cursor-pointer transition-colors ${filter === f ? 'bg-[var(--accent-bg)] text-[var(--accent)]' : 'text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-900'}`}>
              {f}{f !== 'all' && counts[f as keyof typeof counts] > 0 ? ` (${counts[f as keyof typeof counts]})` : ''}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-4 items-start">
        {/* Queue */}
        <div className="space-y-2">
          {filtered.map(run => {
            const style = agentKindStyle(run.agentKind);
            const Icon = style.icon;
            const active = selected?.id === run.id;
            return (
              <button key={run.id} onClick={() => setSelectedId(run.id)}
                className={`w-full text-left p-3 rounded-[var(--r-md)] border transition-colors cursor-pointer ${active ? 'border-[var(--accent)] bg-[var(--accent-bg)]' : 'border-stone-200 dark:border-stone-850 bg-white dark:bg-stone-950 hover:border-stone-300 dark:hover:border-stone-700'}`}>
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <span className="font-mono text-[11px] text-stone-400 font-bold">#{run.itemId}</span>
                  <RunStatusBadge status={run.status} />
                </div>
                <p className="text-[13px] font-semibold text-stone-900 dark:text-stone-100 leading-snug truncate">{run.itemTitle}</p>
                <div className="mt-1.5 flex items-center justify-between text-[10px] text-stone-400">
                  <span className={`inline-flex items-center gap-1 px-1 py-0.5 rounded ${style.tint}`}><Icon className="w-2.5 h-2.5" /> {run.agentName}</span>
                  {run.status !== 'queued' && <span className="font-mono">{run.files.length}f · {run.commands}c</span>}
                </div>
              </button>
            );
          })}
        </div>

        {/* Detail */}
        <div className="border border-stone-200 dark:border-stone-850 rounded-[var(--r-lg)] bg-white dark:bg-stone-950 min-h-[520px] overflow-hidden">
          {selected ? <RunDetail run={selected} /> : (
            <div className="h-full grid place-items-center text-xs text-stone-400 p-8">Select a run to see its live detail.</div>
          )}
        </div>
      </div>
    </div>
  );
};
