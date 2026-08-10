import React from 'react';
import { RotateCcw, X, CheckCircle } from 'lucide-react';
import { useProject } from '../context/ProjectContext.js';

export const Toast: React.FC = () => {
  const { toast, triggerToast } = useProject();

  if (!toast || !toast.visible) return null;

  return (
    <div
      className="fixed bottom-5 left-5 bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 text-stone-800 dark:text-stone-100 rounded-lg p-3.5 pr-4 shadow-[var(--shadow-2)] z-60 animate-in fade-in slide-in-from-bottom-4 duration-350 max-w-sm flex items-center justify-between gap-4 font-sans text-xs border-l-4 border-l-[var(--accent)]"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-2.5 min-w-0">
        <CheckCircle className="w-4 h-4 text-emerald-500 shrink-0" />
        <span className="font-medium truncate">{toast.message}</span>
      </div>

      {toast.undo && (
        <button
          onClick={() => {
            if (toast.undo) toast.undo();
            triggerToast("Action undone.");
          }}
          className="flex items-center gap-1.5 px-2 py-1 rounded bg-stone-100 dark:bg-stone-800 hover:bg-stone-200 dark:hover:bg-stone-750 text-stone-600 dark:text-stone-300 hover:text-stone-900 dark:hover:text-white font-semibold cursor-pointer shrink-0"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>Undo</span>
        </button>
      )}
    </div>
  );
};
