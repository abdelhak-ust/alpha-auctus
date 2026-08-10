import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check, Search, Plus } from 'lucide-react';

interface SearchableSelectProps {
  value: string;
  options: string[];
  onChange: (value: string) => void;
  allowCreate?: boolean;
  placeholder?: string;
  /** Render option/value text in uppercase + bold (e.g. assignee initials). */
  uppercase?: boolean;
  className?: string;
}

export const SearchableSelect: React.FC<SearchableSelectProps> = ({
  value,
  options,
  onChange,
  allowCreate = false,
  placeholder = 'Select…',
  uppercase = false,
  className = ''
}) => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [highlight, setHighlight] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery('');
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery('');
      setHighlight(0);
      const t = setTimeout(() => inputRef.current?.focus(), 0);
      return () => clearTimeout(t);
    }
  }, [open]);

  const q = query.trim().toLowerCase();
  const filtered = options.filter(o => o.toLowerCase().includes(q));
  const exact = options.some(o => o.toLowerCase() === q);
  const showCreate = allowCreate && q.length > 0 && !exact;

  const rows: Array<{ type: 'option' | 'create'; value: string }> = [
    ...filtered.map(o => ({ type: 'option' as const, value: o })),
    ...(showCreate ? [{ type: 'create' as const, value: query.trim() }] : [])
  ];

  const choose = (val: string) => {
    onChange(val);
    setOpen(false);
    setQuery('');
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlight(h => Math.min(h + 1, rows.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight(h => Math.max(h - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const r = rows[highlight];
      if (r) choose(r.value);
    } else if (e.key === 'Escape') {
      setOpen(false);
      setQuery('');
    }
  };

  const valueClass = uppercase ? 'uppercase font-bold' : 'font-medium';

  return (
    <div className={`relative ${className}`} ref={ref}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between gap-1 bg-white dark:bg-stone-950 p-1.5 rounded border border-stone-200 dark:border-stone-800 focus:outline-none focus:border-[var(--accent)] cursor-pointer"
      >
        <span className={`truncate ${value ? `text-stone-800 dark:text-stone-200 ${valueClass}` : 'text-stone-400'}`}>
          {value || placeholder}
        </span>
        <ChevronDown className={`w-3.5 h-3.5 text-stone-400 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 rounded-[var(--r-md)] shadow-[var(--shadow-2)] overflow-hidden">
          <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-stone-150 dark:border-stone-850">
            <Search className="w-3.5 h-3.5 text-stone-400 shrink-0" />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => { setQuery(e.target.value); setHighlight(0); }}
              onKeyDown={onKeyDown}
              placeholder="Search…"
              className="w-full bg-transparent text-xs text-stone-800 dark:text-stone-200 placeholder-stone-400 dark:placeholder-stone-500 focus:outline-none"
            />
          </div>
          <div className="max-h-44 overflow-y-auto py-1">
            {rows.length === 0 && (
              <div className="px-2.5 py-2 text-[11px] text-stone-400">No matches</div>
            )}
            {rows.map((r, idx) => (
              <button
                type="button"
                key={r.type + '-' + r.value}
                onMouseEnter={() => setHighlight(idx)}
                onClick={() => choose(r.value)}
                className={`w-full flex items-center justify-between gap-2 px-2.5 py-1.5 text-left text-xs cursor-pointer ${idx === highlight ? 'bg-[var(--accent-bg)]' : 'hover:bg-stone-100 dark:hover:bg-stone-850'}`}
              >
                {r.type === 'create' ? (
                  <span className="flex items-center gap-1.5 text-[var(--accent)] font-medium">
                    <Plus className="w-3.5 h-3.5" /> Add “{r.value}”
                  </span>
                ) : (
                  <span className={`${valueClass} ${idx === highlight ? 'text-[var(--accent)]' : 'text-stone-700 dark:text-stone-300'}`}>
                    {r.value}
                  </span>
                )}
                {r.type === 'option' && r.value === value && <Check className="w-3.5 h-3.5 text-[var(--accent)] shrink-0" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
