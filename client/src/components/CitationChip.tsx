import React, { useState } from 'react';
import { Bookmark, Clipboard, FileText } from 'lucide-react';
import { useProject } from '../context/ProjectContext.js';

interface CitationChipProps {
  id: string; // e.g. "decision-4" or "item-71" or "src-sheet"
  type: 'item' | 'decision' | 'source';
  title: string;
  snippet?: string;
  className?: string;
}

export const CitationChip: React.FC<CitationChipProps> = ({ id, type, title, snippet, className = '' }) => {
  const { setSelectedCardId, setActiveView } = useProject();
  const [showTooltip, setShowTooltip] = useState(false);

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    const itemIdNum = parseInt(id.replace(/[^\d]/g, ''));
    if (type === 'item' && !isNaN(itemIdNum)) {
      setSelectedCardId(itemIdNum);
    } else if (type === 'decision' && !isNaN(itemIdNum)) {
      // Toggle to settings or open general memory panel
      setActiveView('settings');
    } else {
      setActiveView('sources');
    }
  };

  const getIcon = () => {
    if (type === 'decision') return <Bookmark className="w-3 h-3 text-amber-500" />;
    if (type === 'item') return <Clipboard className="w-3 h-3 text-violet-500" />;
    return <FileText className="w-3 h-3 text-sky-500" />;
  };

  return (
    <span className="relative inline-block">
      <button
        type="button"
        onClick={handleClick}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-stone-100 dark:bg-stone-850 hover:bg-[var(--accent-bg)] hover:text-[var(--accent)] text-stone-700 dark:text-stone-300 border border-stone-200 dark:border-stone-800 text-[11px] font-mono transition-colors cursor-pointer select-none vertical-middle ${className}`}
      >
        {getIcon()}
        <span>{type === 'decision' ? `◆ dec-${id.replace(/[^\d]/g, '')}` : type === 'item' ? `▢ #${id.replace(/[^\d]/g, '')}` : `⤓ source`}</span>
      </button>

      {showTooltip && (title || snippet) && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-64 p-2.5 rounded-[var(--r-sm)] bg-stone-900 text-white text-[11px] font-sans leading-normal shadow-[var(--shadow-2)] z-50 border border-stone-800 pointer-events-none">
          <div className="font-semibold text-stone-200 mb-0.5 tracking-tight truncate">
            {title}
          </div>
          {snippet && (
            <p className="text-stone-400 line-clamp-3 font-normal font-mono text-[10px]">
              “{snippet}”
            </p>
          )}
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-stone-900" />
        </div>
      )}
    </span>
  );
};
