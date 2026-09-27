import React, { useEffect, useRef } from 'react';
import { Bot } from 'lucide-react';

export interface ChatThreadMessage {
  role: 'ai' | 'pm' | 'user';
  text: string;
  cite?: string;
}

interface ChatThreadProps {
  messages: ChatThreadMessage[];
  input: string;
  onInput: (value: string) => void;
  onSend: () => void;
  onSkip?: () => void;
  sending?: boolean;
  placeholder?: string;
  done?: boolean;
  footer?: React.ReactNode;
}

export const ChatThread: React.FC<ChatThreadProps> = ({
  messages,
  input,
  onInput,
  onSend,
  onSkip,
  sending = false,
  placeholder = 'Type your answer…',
  done = false,
  footer,
}) => {
  const logRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex flex-col min-h-0 flex-1">
      <div ref={logRef} aria-live="polite" className="flex-1 min-h-0 overflow-y-auto px-1 py-2">
        <div className="space-y-4">
          {messages.map((m, i) => (
            m.role === 'ai' ? (
              <div key={i} className="flex items-start gap-2.5">
                <span className="w-7 h-7 shrink-0 grid place-items-center rounded-full bg-[var(--accent-bg)] text-[var(--accent)] mt-0.5">
                  <Bot className="w-4 h-4" />
                </span>
                <div className="space-y-1.5">
                  <div className="inline-block bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-800 rounded-[var(--r-md)] px-3.5 py-2.5 text-sm text-stone-800 dark:text-stone-200 leading-relaxed whitespace-pre-wrap">
                    {m.text}
                  </div>
                  {m.cite && (
                    <div className="text-[10px] font-mono text-stone-400 pl-1">cited: {m.cite}</div>
                  )}
                </div>
              </div>
            ) : (
              <div key={i} className="flex justify-end">
                <div className="inline-block max-w-[80%] bg-[var(--accent)] text-white rounded-[var(--r-md)] px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap">
                  {m.text}
                </div>
              </div>
            )
          ))}
        </div>
      </div>

      <div className="pt-2 space-y-2.5 shrink-0">
        <div className="flex items-end gap-2">
          <textarea
            rows={1}
            value={input}
            onChange={(e) => onInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend(); } }}
            placeholder={done ? 'All questions answered' : placeholder}
            aria-label="Your answer"
            disabled={done || sending}
            className="flex-1 resize-none bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-800 rounded-[var(--r-md)] px-3 py-2.5 text-sm text-stone-800 dark:text-stone-100 placeholder-stone-400 focus:outline-none focus:border-[var(--accent)] max-h-32 disabled:opacity-50"
          />
          <button
            type="button"
            onClick={onSend}
            disabled={!input.trim() || done || sending}
            className="shrink-0 px-4 py-2.5 rounded-[var(--r-md)] border border-stone-200 dark:border-stone-800 text-sm font-semibold text-stone-600 dark:text-stone-300 hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            Send
          </button>
          {onSkip && !done && (
            <button
              type="button"
              onClick={onSkip}
              disabled={sending}
              className="shrink-0 px-3 py-2.5 rounded-[var(--r-md)] text-sm font-medium text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 cursor-pointer disabled:opacity-40"
            >
              Skip
            </button>
          )}
        </div>
        {footer}
      </div>
    </div>
  );
};
