import { Bot, PenTool, Code2, Bug, FileText, FlaskConical, ShieldCheck, LucideIcon } from 'lucide-react';
import { Agent, AgentKind } from '../types.js';

const AGENT_PREFIX = 'agent:';

export function isAgentRef(value: string): boolean {
  return typeof value === 'string' && value.startsWith(AGENT_PREFIX);
}

export function agentRef(id: string): string {
  return AGENT_PREFIX + id;
}

export function agentIdFromRef(value: string): string {
  return isAgentRef(value) ? value.slice(AGENT_PREFIX.length) : value;
}

export interface ResolvedAssignee {
  kind: 'human' | 'agent';
  label: string;        // human: initials; agent: short name
  raw: string;          // the stored value
  agent?: Agent;
}

/** Resolve a stored assignee value (human initials, or `agent:<id>`) for display. */
export function resolveAssignee(value: string, agents: Agent[]): ResolvedAssignee {
  if (isAgentRef(value)) {
    const id = agentIdFromRef(value);
    const agent = agents.find(a => a.id === id);
    return {
      kind: 'agent',
      // Fall back to the id if the agent was deleted from the catalog.
      label: agent ? agent.name : id,
      raw: value,
      agent
    };
  }
  return { kind: 'human', label: value, raw: value };
}

interface KindStyle {
  icon: LucideIcon;
  /** Tailwind classes for the agent badge tint (light + dark). */
  tint: string;
}

const KIND_STYLES: Record<AgentKind, KindStyle> = {
  design:   { icon: PenTool,      tint: 'bg-pink-50 text-pink-600 dark:bg-pink-950/40 dark:text-pink-300' },
  code:     { icon: Code2,        tint: 'bg-violet-50 text-violet-600 dark:bg-violet-950/40 dark:text-violet-300' },
  qa:       { icon: Bug,          tint: 'bg-amber-50 text-amber-600 dark:bg-amber-950/40 dark:text-amber-300' },
  docs:     { icon: FileText,     tint: 'bg-sky-50 text-sky-600 dark:bg-sky-950/40 dark:text-sky-300' },
  test:     { icon: FlaskConical, tint: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-300' },
  security: { icon: ShieldCheck,  tint: 'bg-red-50 text-red-600 dark:bg-red-950/40 dark:text-red-300' },
  custom:   { icon: Bot,          tint: 'bg-violet-50 text-violet-600 dark:bg-violet-950/40 dark:text-violet-300' }
};

export function agentKindStyle(kind: AgentKind): KindStyle {
  return KIND_STYLES[kind] || KIND_STYLES.custom;
}
