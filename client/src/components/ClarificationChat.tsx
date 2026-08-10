import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Bot, ArrowRight, Sparkles, Check, Loader2, FileText, Video, Image as ImageIcon } from 'lucide-react';
import { useProject } from '../context/ProjectContext.js';
import { ClarificationTurn, DraftSourceKind } from '../types.js';

interface ChatMsg {
  role: 'ai' | 'user';
  text: string;
  cite?: string; // source name referenced by the AI
}

const kindIcon: Record<DraftSourceKind, React.ComponentType<{ className?: string }>> = {
  file: FileText,
  video: Video,
  image: ImageIcon
};

// Build a small, bounded set of clarification questions grounded in the draft.
function buildQuestions(desc: string, github: string, mediaCount: number): string[] {
  const qs: string[] = [];
  qs.push("Who's the primary decision-maker on this project?");
  qs.push('What single outcome matters most for the first milestone?');
  if (github) qs.push('Should I treat the existing repo as the source of truth for what’s already built?');
  if (mediaCount > 0) qs.push('For the calls and whiteboards you added — which one is the most current source of truth?');
  return qs.slice(0, 4);
}

export const ClarificationChat: React.FC = () => {
  const { setupDraft, finishSetupAndGenerate } = useProject();

  const questions = useMemo(
    () => buildQuestions(setupDraft.description, setupDraft.github, setupDraft.sources.filter(s => s.kind !== 'file').length),
    [setupDraft]
  );

  const firstSource = setupDraft.sources[0];
  const [messages, setMessages] = useState<ChatMsg[]>(() => [
    {
      role: 'ai',
      text: setupDraft.sources.length
        ? "I'm reading your sources now. While I do, a couple of quick questions so the tasks land right."
        : "Thanks — a couple of quick questions so the tasks land right.",
      cite: firstSource?.name
    },
    { role: 'ai', text: questions[0] }
  ]);
  const [qIndex, setQIndex] = useState(0);
  const [input, setInput] = useState('');
  const [answers, setAnswers] = useState<ClarificationTurn[]>([]);
  const [generating, setGenerating] = useState(false);

  // Simulated background ingest: flip each source reading → ready on a timer.
  const [readyCount, setReadyCount] = useState(0);
  const total = setupDraft.sources.length;
  useEffect(() => {
    if (total === 0) return;
    const timers = setupDraft.sources.map((_, i) =>
      setTimeout(() => setReadyCount(c => Math.max(c, i + 1)), 900 * (i + 1))
    );
    return () => timers.forEach(clearTimeout);
  }, [total]);

  const logRef = useRef<HTMLDivElement>(null);
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' }); }, [messages]);

  const questionsDone = qIndex >= questions.length - 1 && answers.length >= questions.length;
  const canGenerate = answers.length >= 1; // completes the flow once core questions are answered

  const send = () => {
    if (!input.trim()) return;
    const answered = questions[qIndex];
    const nextAnswers = [...answers, { question: answered, answer: input.trim() }];
    setAnswers(nextAnswers);

    const newMsgs: ChatMsg[] = [{ role: 'user', text: input.trim() }];
    const next = qIndex + 1;
    if (next < questions.length) {
      newMsgs.push({ role: 'ai', text: questions[next] });
      setQIndex(next);
    } else {
      newMsgs.push({ role: 'ai', text: "Got it — that's enough to draft your board. Generate the tasks whenever you're ready." });
    }
    setMessages(prev => [...prev, ...newMsgs]);
    setInput('');
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      await finishSetupAndGenerate(answers);
    } catch (e) {
      setGenerating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-[var(--bg-app)] text-[var(--text-primary)] flex flex-col">
      {/* Header + background-ingest indicator */}
      <header className="border-b border-stone-200/60 dark:border-stone-850/60 px-6 py-3.5 shrink-0">
        <div className="max-w-[720px] mx-auto flex items-center justify-between gap-4">
          <h1 className="text-sm font-semibold text-stone-800 dark:text-stone-100 truncate">
            Setting up: <span className="text-[var(--accent)]">"{setupDraft.name}"</span>
          </h1>
          {total > 0 && (
            <div className="flex items-center gap-2 shrink-0">
              <span className="text-[11px] font-mono text-stone-400">
                {readyCount < total ? `reading sources ${readyCount}/${total}` : 'sources ready'}
              </span>
              <div className="w-24 h-1.5 rounded-full bg-stone-200 dark:bg-stone-800 overflow-hidden">
                <div className="h-full bg-[var(--accent)] transition-all duration-500" style={{ width: `${(readyCount / total) * 100}%` }} />
              </div>
            </div>
          )}
        </div>
        {total > 0 && (
          <div className="max-w-[720px] mx-auto mt-2 flex flex-wrap gap-1.5">
            {setupDraft.sources.map((s, i) => {
              const Icon = kindIcon[s.kind];
              const ready = i < readyCount;
              return (
                <span key={s.name} className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-stone-100 dark:bg-stone-900 text-[10px] font-mono text-stone-500 dark:text-stone-400">
                  <Icon className="w-3 h-3" />
                  <span className="max-w-[140px] truncate">{s.name}</span>
                  {ready ? <Check className="w-3 h-3 text-emerald-500" /> : <Loader2 className="w-3 h-3 animate-spin text-stone-400" />}
                </span>
              );
            })}
          </div>
        )}
      </header>

      {/* Chat log */}
      <div ref={logRef} aria-live="polite" className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-[720px] mx-auto space-y-4">
          {messages.map((m, i) => (
            m.role === 'ai' ? (
              <div key={i} className="flex items-start gap-2.5">
                <span className="w-7 h-7 shrink-0 grid place-items-center rounded-full bg-[var(--accent-bg)] text-[var(--accent)] mt-0.5">
                  <Bot className="w-4 h-4" />
                </span>
                <div className="space-y-1.5">
                  <div className="inline-block bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-800 rounded-[var(--r-md)] px-3.5 py-2.5 text-sm text-stone-800 dark:text-stone-200 leading-relaxed">
                    {m.text}
                  </div>
                  {m.cite && (
                    <div className="text-[10px] font-mono text-stone-400 pl-1">cited: {m.cite}</div>
                  )}
                </div>
              </div>
            ) : (
              <div key={i} className="flex justify-end">
                <div className="inline-block max-w-[80%] bg-[var(--accent)] text-white rounded-[var(--r-md)] px-3.5 py-2.5 text-sm leading-relaxed">
                  {m.text}
                </div>
              </div>
            )
          ))}
        </div>
      </div>

      {/* Composer + generate */}
      <footer className="border-t border-stone-200/60 dark:border-stone-850/60 px-6 py-4 shrink-0">
        <div className="max-w-[720px] mx-auto space-y-2.5">
          <div className="flex items-end gap-2">
            <textarea
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
              placeholder={questionsDone ? 'Add anything else…' : 'Type your answer…'}
              aria-label="Your answer"
              className="flex-1 resize-none bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-800 rounded-[var(--r-md)] px-3 py-2.5 text-sm text-stone-800 dark:text-stone-100 placeholder-stone-400 focus:outline-none focus:border-[var(--accent)] max-h-32"
            />
            <button
              onClick={send}
              disabled={!input.trim()}
              className="shrink-0 px-4 py-2.5 rounded-[var(--r-md)] border border-stone-200 dark:border-stone-800 text-sm font-semibold text-stone-600 dark:text-stone-300 hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            >
              Send
            </button>
          </div>
          <button
            onClick={handleGenerate}
            disabled={!canGenerate || generating}
            className="w-full py-2.5 rounded-[var(--r-md)] bg-[var(--accent)] text-white text-sm font-semibold hover:opacity-95 active:scale-[0.99] transition-transform disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer flex items-center justify-center gap-2"
          >
            {generating ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Generating tasks…</>
            ) : (
              <><Sparkles className="w-4 h-4" /> Generate tasks <ArrowRight className="w-4 h-4" /></>
            )}
          </button>
        </div>
      </footer>
    </div>
  );
};
