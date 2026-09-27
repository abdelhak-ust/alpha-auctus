import React, { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { useProject } from '../context/ProjectContext.js';
import { ChatThread, ChatThreadMessage } from './ChatThread.js';
import { BackendError } from '../lib/backend.js';

export const FeatureClarification: React.FC<{ onClose?: () => void; featureId?: string }> = ({ onClose, featureId }) => {
  const { clarification, answerClarification, skipClarification, skipRemainingQuestions, refreshFeatures } = useProject();
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [changes, setChanges] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void refreshFeatures();
  }, [refreshFeatures]);

  const messages: ChatThreadMessage[] = (clarification?.history || [])
    .filter(m => !featureId || !m.featureId || m.featureId === featureId)
    .map(m => ({
      role: m.role === 'ai' ? 'ai' : 'pm',
      text: m.text,
    }));
  const next = clarification?.next && (!featureId || clarification.next.featureId === featureId)
    ? clarification.next
    : null;
  const remaining = featureId
    ? (clarification?.history ? (clarification.remaining ?? 0) : 0)
    : (clarification?.remaining ?? 0);
  const done = !next && remaining === 0 && (clarification?.history.length || 0) > 0;

  if (done && messages.length && messages[messages.length - 1].text !== 'All questions answered') {
    messages.push({ role: 'ai', text: 'All questions answered.' });
  }

  const send = async () => {
    if (!next || !input.trim()) return;
    setSending(true);
    setError(null);
    try {
      const res = await answerClarification(next.questionId, input.trim());
      setChanges(res.changes || []);
      setInput('');
    } catch (e) {
      setError(e instanceof BackendError ? e.toDisplay() : 'Could not send the answer.');
    } finally {
      setSending(false);
    }
  };

  const skip = async () => {
    if (!next) return;
    setSending(true);
    setError(null);
    try {
      const res = await skipClarification(next.questionId);
      setChanges(res.changes || ['Skipped']);
    } catch (e) {
      setError(e instanceof BackendError ? e.toDisplay() : 'Could not skip.');
    } finally {
      setSending(false);
    }
  };

  const skipRemaining = async () => {
    if (!featureId) return;
    setSending(true);
    setError(null);
    try {
      const res = await skipRemainingQuestions(featureId);
      setChanges(res.changes || ['Skipped remaining questions']);
    } catch (e) {
      setError(e instanceof BackendError ? e.toDisplay() : 'Could not skip remaining.');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex flex-col h-full min-h-[320px] border border-stone-200 dark:border-stone-800 rounded-[var(--r-lg)] bg-white dark:bg-stone-950 p-4">
      <div className="flex items-center justify-between mb-3 shrink-0">
        <h3 className="text-sm font-semibold text-stone-800 dark:text-stone-100">
          Clarification
          {remaining > 0 && (
            <span className="ml-2 text-[11px] font-mono font-normal text-stone-400">{remaining} left</span>
          )}
        </h3>
        {onClose && (
          <button type="button" onClick={onClose} className="text-xs text-stone-400 hover:text-stone-700 cursor-pointer">
            Close
          </button>
        )}
      </div>
      {sending && (
        <div className="flex items-center gap-2 text-[11px] text-stone-400 mb-2">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Clarifier is updating the feature…
        </div>
      )}
      {changes.length > 0 && (
        <ul className="mb-2 text-[11px] text-stone-500 dark:text-stone-400 space-y-0.5">
          {changes.map((c, i) => <li key={i}>{c}</li>)}
        </ul>
      )}
      {error && <p role="alert" className="text-[11px] text-[var(--verdict-conf-txt)] mb-2">{error}</p>}
      <ChatThread
        messages={messages}
        input={input}
        onInput={setInput}
        onSend={send}
        onSkip={next ? skip : undefined}
        sending={sending}
        done={done || !next}
        placeholder={next ? 'Type your answer…' : 'No open questions'}
        footer={featureId && next ? (
          <button
            type="button"
            onClick={() => { void skipRemaining(); }}
            disabled={sending}
            className="text-[11px] font-medium text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 cursor-pointer disabled:opacity-40"
          >
            Skip remaining questions
          </button>
        ) : undefined}
      />
    </div>
  );
};
