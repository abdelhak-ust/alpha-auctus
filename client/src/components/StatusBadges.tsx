import React from 'react';
import {
  Check, CircleSlash, AlertTriangle, Diamond, HelpCircle, Loader2,
  Cog, Ban, CheckCircle2, Circle, Minus, XCircle
} from 'lucide-react';
import { CoverageState, RunStatus, ACState, CheckState } from '../types.js';

// One hue, one meaning across both verdict families (spec §2.1): met/net-new green,
// partial/duplicate amber, unmet/conflict red, off-task/impact blue. Colour is never
// the only signal — every badge pairs an icon + a text label (spec §11 a11y).

const COVERAGE: Record<CoverageState, { bg: string; txt: string; label: string; Icon: any }> = {
  met:          { bg: 'bg-[var(--verdict-new-bg)]',    txt: 'text-[var(--verdict-new-txt)]',    label: 'met',          Icon: Check },
  partial:      { bg: 'bg-[var(--verdict-dup-bg)]',    txt: 'text-[var(--verdict-dup-txt)]',    label: 'partial',      Icon: AlertTriangle },
  unmet:        { bg: 'bg-[var(--verdict-conf-bg)]',   txt: 'text-[var(--verdict-conf-txt)]',   label: 'unmet',        Icon: CircleSlash },
  'off-task':   { bg: 'bg-[var(--verdict-impact-bg)]', txt: 'text-[var(--verdict-impact-txt)]', label: 'off-task',     Icon: Diamond },
  unverifiable: { bg: 'bg-stone-100 dark:bg-stone-800', txt: 'text-stone-500 dark:text-stone-400', label: 'unverifiable', Icon: HelpCircle },
};

export const CoverageBadge: React.FC<{ state: CoverageState; className?: string }> = ({ state, className = '' }) => {
  const c = COVERAGE[state];
  const Icon = c.Icon;
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-[var(--r-sm)] text-[10px] font-semibold uppercase tracking-[0.03em] ${c.bg} ${c.txt} ${className}`}>
      <Icon className="w-3 h-3" />
      {c.label}
    </span>
  );
};

const RUN: Record<RunStatus, { bg: string; txt: string; label: string; Icon: any; spin?: boolean }> = {
  queued:  { bg: 'bg-stone-100 dark:bg-stone-800',      txt: 'text-stone-500 dark:text-stone-400',  label: 'queued',  Icon: Circle },
  running: { bg: 'bg-[var(--accent-bg)]',               txt: 'text-[var(--accent)]',                label: 'running', Icon: Cog, spin: true },
  blocked: { bg: 'bg-amber-100 dark:bg-amber-950/40',   txt: 'text-amber-700 dark:text-amber-400',  label: 'blocked', Icon: Ban },
  done:    { bg: 'bg-[var(--verdict-new-bg)]',          txt: 'text-[var(--verdict-new-txt)]',       label: 'done',    Icon: CheckCircle2 },
  failed:  { bg: 'bg-[var(--verdict-conf-bg)]',         txt: 'text-[var(--verdict-conf-txt)]',      label: 'failed',  Icon: XCircle },
  stopped: { bg: 'bg-stone-100 dark:bg-stone-800',      txt: 'text-stone-500 dark:text-stone-400',  label: 'stopped', Icon: Minus },
};

export const RunStatusBadge: React.FC<{ status: RunStatus; className?: string }> = ({ status, className = '' }) => {
  const s = RUN[status];
  const Icon = s.Icon;
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-[var(--r-sm)] text-[10px] font-semibold uppercase tracking-[0.03em] ${s.bg} ${s.txt} ${className}`}>
      <Icon className={`w-3 h-3 ${s.spin ? 'animate-spin' : ''}`} />
      {s.label}
    </span>
  );
};

// Acceptance-criteria dot: ✓ done / ⟳ in progress / – not started / ⚠ blocked (§4.12)
export const ACDot: React.FC<{ state: ACState }> = ({ state }) => {
  if (state === 'done') return <Check className="w-3.5 h-3.5 text-[var(--verdict-new-txt)]" />;
  if (state === 'in_progress') return <Loader2 className="w-3.5 h-3.5 text-[var(--accent)] animate-spin" />;
  if (state === 'blocked') return <Ban className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />;
  return <Minus className="w-3.5 h-3.5 text-stone-400" />;
};

// CI / build / lint pill (§4.14)
export const CheckPill: React.FC<{ label: string; state: CheckState }> = ({ label, state }) => {
  const map = {
    passing: { txt: 'text-[var(--verdict-new-txt)]', Icon: Check },
    failing: { txt: 'text-[var(--verdict-conf-txt)]', Icon: XCircle },
    running: { txt: 'text-[var(--accent)]', Icon: Loader2 },
  } as const;
  const s = map[state];
  const Icon = s.Icon;
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-medium ${s.txt}`}>
      <Icon className={`w-3.5 h-3.5 ${state === 'running' ? 'animate-spin' : ''}`} />
      {label}
    </span>
  );
};

// Small run-status chip for the board card (spec §4.1: ⚙ running / ✓ 5/7 met / ⚠ blocked)
export const RunChip: React.FC<{ status: RunStatus; met?: number; total?: number }> = ({ status, met, total }) => {
  if (status === 'running') {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-[var(--accent-bg)] text-[var(--accent)]">
        <Cog className="w-2.5 h-2.5 animate-spin" /> running
      </span>
    );
  }
  if (status === 'blocked') {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400">
        <Ban className="w-2.5 h-2.5" /> blocked
      </span>
    );
  }
  if (status === 'done' && met !== undefined && total !== undefined) {
    const clean = met === total;
    return (
      <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold ${clean ? 'bg-[var(--verdict-new-bg)] text-[var(--verdict-new-txt)]' : 'bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400'}`}>
        {clean ? <Check className="w-2.5 h-2.5" /> : <AlertTriangle className="w-2.5 h-2.5" />} {met}/{total} met
      </span>
    );
  }
  if (status === 'queued') {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-stone-100 dark:bg-stone-800 text-stone-500 dark:text-stone-400">
        <Circle className="w-2.5 h-2.5" /> queued
      </span>
    );
  }
  return null;
};
