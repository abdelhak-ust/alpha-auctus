import React, { useState, useEffect, useRef } from 'react';
import { Search, Plus, MessageSquare, ArrowRight, CornerDownLeft, Sparkles } from 'lucide-react';
import { useProject } from '../context/ProjectContext.js';

interface CommandBarProps {
  onClose: () => void;
}

export const CommandBar: React.FC<CommandBarProps> = ({ onClose }) => {
  const { state, addItem, setActiveView, setSelectedCardId, triggerToast } = useProject();
  const [input, setInput] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Determine actions based on user input
  const getActions = () => {
    const trimmed = input.trim();
    if (!trimmed) {
      return [
        { type: 'nav', label: 'Go to Chat (workflow)', action: () => { setActiveView('chat'); onClose(); }, shortcut: 'g c' },
        { type: 'nav', label: 'Go to Kanban Board', action: () => { setActiveView('board'); onClose(); }, shortcut: 'g b' },
        { type: 'nav', label: 'Go to Verdicts Inbox', action: () => { setActiveView('verdicts'); onClose(); }, shortcut: 'g v' },
        { type: 'nav', label: 'Go to Runs (agent execution)', action: () => { setActiveView('runs'); onClose(); }, shortcut: 'g u' },
        { type: 'nav', label: 'Go to Reviews (requirement validation)', action: () => { setActiveView('reviews'); onClose(); }, shortcut: 'g e' },
        { type: 'nav', label: 'Go to Delivery (PR & deploy)', action: () => { setActiveView('delivery'); onClose(); }, shortcut: 'g y' },
        { type: 'nav', label: 'Go to Memory (Ask Questions)', action: () => { setActiveView('memory'); onClose(); }, shortcut: 'g m' },
        { type: 'nav', label: 'Go to Impact Graph', action: () => { setActiveView('impact'); onClose(); }, shortcut: 'g i' },
        { type: 'nav', label: 'Go to BRD/Spec Authoring', action: () => { setActiveView('author'); onClose(); }, shortcut: 'g a' },
        { type: 'nav', label: 'Go to Sources', action: () => { setActiveView('sources'); onClose(); }, shortcut: 'g s' },
        { type: 'nav', label: 'Go to Features', action: () => { setActiveView('features'); onClose(); }, shortcut: 'g f' },
        { type: 'nav', label: 'Go to Settings & BYOK config', action: () => { setActiveView('settings'); onClose(); }, shortcut: 'g d' }
      ];
    }

    const lower = trimmed.toLowerCase();
    const actions = [];

    // 1. Create card option
    actions.push({
      type: 'create',
      label: `Create card: "${trimmed}"`,
      action: async () => {
        const newItem = await addItem({ title: trimmed, description: "Created via ⌘K command bar." });
        setSelectedCardId(newItem.id);
        onClose();
      }
    });

    // 2. Ask question option (highly prioritised if why/what/how or "?")
    const isQuestion = lower.startsWith('why') || lower.startsWith('what') || lower.startsWith('how') || lower.startsWith('is') || lower.endsWith('?');
    actions.push({
      type: 'ask',
      label: `Ask Decision Memory: "${trimmed}"`,
      action: () => {
        // Redirect to memory tab, preset prompt
        setActiveView('memory');
        // Let state transition happen
        setTimeout(() => {
          const queryInput = document.getElementById('memory-query-input') as HTMLInputElement;
          if (queryInput) {
            queryInput.value = trimmed;
            const submitBtn = document.getElementById('memory-query-submit') as HTMLButtonElement;
            if (submitBtn) submitBtn.click();
          }
        }, 100);
        onClose();
      },
      preferred: isQuestion
    });

    // 3. Search matching cards or decisions
    if (state) {
      const matchCards = state.items.filter(i => i.title.toLowerCase().includes(lower) || i.description.toLowerCase().includes(lower));
      matchCards.forEach(card => {
        actions.push({
          type: 'search',
          label: `Open Backlog Card #${card.id}: "${card.title}"`,
          action: () => {
            setSelectedCardId(card.id);
            onClose();
          }
        });
      });

      const matchDecs = state.decisions.filter(d => d.title.toLowerCase().includes(lower) || d.description.toLowerCase().includes(lower));
      matchDecs.forEach(dec => {
        actions.push({
          type: 'search',
          label: `View Decision #${dec.id}: "${dec.title}"`,
          action: () => {
            setActiveView('settings'); // Decisions list lives in unified context settings or panel
            onClose();
          }
        });
      });
    }

    // Sort such that if it is a question, "Ask" is at the top, otherwise "Create card"
    if (isQuestion) {
      actions.sort((a, b) => (a.type === 'ask' ? -1 : b.type === 'ask' ? 1 : 0));
    }

    return actions;
  };

  const actions = getActions();

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex(prev => (prev + 1) % actions.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex(prev => (prev - 1 + actions.length) % actions.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (actions[selectedIndex]) {
        actions[selectedIndex].action();
      }
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-start justify-center pt-[15vh] px-4">
      <div
        ref={containerRef}
        onKeyDown={handleKeyDown}
        className="w-full max-w-xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 text-stone-800 dark:text-stone-100 rounded-xl shadow-[var(--shadow-2)] overflow-hidden transition-all duration-200"
      >
        {/* Input area */}
        <div className="flex items-center gap-3 px-4 py-3.5 border-b border-stone-200 dark:border-stone-850">
          <Search className="w-5 h-5 text-stone-400 dark:text-stone-500 shrink-0" />
          <input
            type="text"
            autoFocus
            placeholder="Type 'Why did we rely on custom IdP?' or create, search, run commands..."
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              setSelectedIndex(0);
            }}
            className="w-full bg-transparent text-sm focus:outline-none text-stone-800 dark:text-stone-100 placeholder-stone-400 dark:placeholder-stone-500 font-sans"
          />
          <button
            onClick={onClose}
            className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-stone-100 dark:bg-stone-800 text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200"
          >
            Esc
          </button>
        </div>

        {/* Action indices */}
        <div className="max-h-[350px] overflow-y-auto py-2">
          {actions.length === 0 ? (
            <div className="p-4 text-center text-xs text-stone-500">
              No matching actions found
            </div>
          ) : (
            actions.map((act, idx) => {
              const isSelected = idx === selectedIndex;
              return (
                <div
                  key={idx}
                  onClick={() => act.action()}
                  className={`px-4 py-2.5 flex items-center justify-between gap-3 text-xs cursor-pointer transition-colors ${isSelected ? 'bg-[var(--accent-bg)] text-[var(--accent)]' : 'text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-850'}`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    {act.type === 'create' && <Plus className="w-4 h-4 text-emerald-500 shrink-0" />}
                    {act.type === 'ask' && <MessageSquare className="w-4 h-4 text-amber-500 shrink-0" />}
                    {act.type === 'nav' && <ArrowRight className="w-4 h-4 text-cyan-500 shrink-0" />}
                    {act.type === 'search' && <Sparkles className="w-4 h-4 text-indigo-400 shrink-0" />}
                    <span className="font-medium truncate">{act.label}</span>
                  </div>

                  {/* Accompany helper tips */}
                  <div className="flex items-center gap-1.5 shrink-0">
                    {isSelected && (
                      <span className="inline-flex items-center gap-0.5 text-[9px] font-mono select-none px-1 rounded bg-[var(--accent)]/15 text-[var(--accent)] leading-none">
                        <span>Enter</span>
                        <CornerDownLeft className="w-2.5 h-2.5" />
                      </span>
                    )}
                    {act.shortcut && (
                      <span className="text-[10px] font-mono text-stone-500 uppercase">{act.shortcut}</span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footing tips */}
        <div className="bg-stone-50 dark:bg-stone-950 px-4 py-2 border-t border-stone-200 dark:border-stone-900 flex items-center justify-between text-[10px] font-mono text-stone-400 dark:text-stone-500">
          <span>↑↓ to navigate · Enter to choose</span>
          <span>⌘K Command deck</span>
        </div>
      </div>
    </div>
  );
};
