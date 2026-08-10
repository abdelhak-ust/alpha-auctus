import React, { useState, useRef, useEffect } from 'react';
import { ChevronsUpDown, Plus, Check, FolderKanban, LayoutGrid } from 'lucide-react';
import { useProject } from '../context/ProjectContext.js';

export const ProjectSwitcher: React.FC = () => {
  const { projects, activeProject, selectProject, startNewProjectSetup, setActiveView } = useProject();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const handleNewProject = () => {
    startNewProjectSetup();
    setOpen(false);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 pl-2 pr-2.5 py-1.5 rounded-[var(--r-sm)] hover:bg-stone-100 dark:hover:bg-stone-900 border border-transparent hover:border-stone-200 dark:hover:border-stone-800 cursor-pointer transition-colors max-w-[240px]"
      >
        <span className="w-6 h-6 shrink-0 grid place-items-center rounded bg-[var(--accent-bg)] text-[var(--accent)] font-mono font-bold text-xs uppercase">
          {activeProject ? activeProject.name.slice(0, 1) : 'N'}
        </span>
        <span className="text-sm font-semibold text-stone-800 dark:text-stone-100 truncate">
          {activeProject ? activeProject.name : 'Select a project'}
        </span>
        <ChevronsUpDown className="w-3.5 h-3.5 text-stone-400 shrink-0" />
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1.5 w-72 bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 rounded-[var(--r-md)] shadow-[var(--shadow-2)] z-50 overflow-hidden">
          <div className="px-3 py-2 text-[10px] font-mono uppercase tracking-wider text-stone-400 border-b border-stone-150 dark:border-stone-850">
            Switch project
          </div>
          <div className="max-h-[280px] overflow-y-auto py-1">
            {projects.map((p) => {
              const isActive = activeProject?.id === p.id;
              return (
                <button
                  key={p.id}
                  onClick={() => { selectProject(p.id); setOpen(false); }}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 text-left cursor-pointer transition-colors ${isActive ? 'bg-[var(--accent-bg)]' : 'hover:bg-stone-100 dark:hover:bg-stone-850'}`}
                >
                  <span className="w-6 h-6 shrink-0 grid place-items-center rounded bg-stone-100 dark:bg-stone-800 text-stone-600 dark:text-stone-300 font-mono font-bold text-xs uppercase">
                    {p.name.slice(0, 1)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <span className={`block text-sm font-medium truncate ${isActive ? 'text-[var(--accent)]' : 'text-stone-800 dark:text-stone-200'}`}>
                      {p.name}
                    </span>
                    <span className="text-[10px] text-stone-400 font-mono">
                      {p.itemCount} cards · {p.sourceCount} sources
                    </span>
                  </div>
                  {isActive && <Check className="w-4 h-4 text-[var(--accent)] shrink-0" />}
                </button>
              );
            })}
            {projects.length === 0 && (
              <div className="px-3 py-3 text-xs text-stone-400">No projects yet.</div>
            )}
          </div>

          <div className="border-t border-stone-150 dark:border-stone-850 p-1.5 space-y-0.5">
            <button
              onClick={handleNewProject}
              className="w-full flex items-center gap-2 px-2.5 py-2 rounded text-xs font-medium text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-850 cursor-pointer"
            >
              <Plus className="w-4 h-4 text-[var(--accent)]" />
              <span>New project</span>
            </button>
            <button
              onClick={() => { setActiveView('projects'); setOpen(false); }}
              className="w-full flex items-center gap-2 px-2.5 py-2 rounded text-xs font-medium text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-850 cursor-pointer"
            >
              <LayoutGrid className="w-4 h-4 text-stone-400" />
              <span>View all projects</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
