import React from 'react';
import { ShieldCheck, Copy, AlertTriangle, Info, RefreshCw } from 'lucide-react';
import { VerdictType } from '../types.js';

interface VerdictBadgeProps {
  type: VerdictType | 'low-confidence';
  confidence?: number;
  className?: string;
  onClick?: (e: React.MouseEvent) => void;
}

export const VerdictBadge: React.FC<VerdictBadgeProps> = ({ type, confidence, className = '', onClick }) => {
  let bgClass = '';
  let textClass = '';
  let label = '';
  let Icon = Info;

  switch (type) {
    case 'net-new':
      bgClass = 'bg-[var(--verdict-new-bg)]';
      textClass = 'text-[var(--verdict-new-txt)]';
      label = 'Net-New';
      Icon = ShieldCheck;
      break;
    case 'duplicate':
      bgClass = 'bg-[var(--verdict-dup-bg)]';
      textClass = 'text-[var(--verdict-dup-txt)]';
      label = 'Duplicate';
      Icon = Copy;
      break;
    case 'conflict':
      bgClass = 'bg-[var(--verdict-conf-bg)]';
      textClass = 'text-[var(--verdict-conf-txt)]';
      label = 'Conflict';
      Icon = AlertTriangle;
      break;
    case 'impact':
      bgClass = 'bg-[var(--verdict-impact-bg)]';
      textClass = 'text-[var(--verdict-impact-txt)]';
      label = 'Impact Risk';
      Icon = Info;
      break;
    case 'checking':
      bgClass = 'bg-stone-100 dark:bg-stone-800';
      textClass = 'text-stone-500 dark:text-stone-400';
      label = 'Checking...';
      Icon = RefreshCw;
      break;
    case 'low-confidence':
      bgClass = 'bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900';
      textClass = 'text-amber-700 dark:text-amber-400';
      label = 'Needs Review';
      Icon = AlertTriangle;
      break;
  }

  // Avoid rendering anything visible at all for empty/silent net-new during normal board rests if it is net-new, UNLESS in detail drawer
  // Actually, the spec says "Net-new confirmed clean cards show no badge (calm). ... Verdict badge shows only when verdict ∈ {duplicate, conflict, impact} or checking."
  // So if type === 'net-new' and we are doing a standard inline card badge, we return null, or can render custom if requested. Let's make a flag or just render it if clicked.
  // Wait, let's allow it to be shown when explicitly requested or inside Drawer details, and let's have a simple small format.
  
  const showPercent = confidence && confidence < 100 && type !== 'checking';

  return (
    <div
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-[var(--r-sm)] text-xs font-medium tracking-[0.01em] shadow-sm select-none ${bgClass} ${textClass} ${onClick ? 'cursor-pointer hover:opacity-90 active:scale-95 transition-transform' : ''} ${className}`}
      aria-label={`${label} verdict ${showPercent ? `, ${confidence}% confidence` : ''}`}
    >
      <Icon className={`w-3.5 h-3.5 ${type === 'checking' ? 'animate-spin' : ''}`} />
      <span>{label}</span>
      {showPercent && (
        <span className="opacity-75 text-[10px] font-mono bg-white/20 dark:bg-black/20 px-1 py-0.5 rounded ml-0.5">
          {confidence}%
        </span>
      )}
    </div>
  );
};
