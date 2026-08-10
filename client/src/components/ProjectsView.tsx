import React from 'react';
import { FolderKanban, Plus, ArrowRight, Trash2, Clock } from 'lucide-react';
import { useProject } from '../context/ProjectContext.js';

export const ProjectsView: React.FC = () => {
  const { projects, activeProjectId, selectProject, startNewProjectSetup, deleteProject, loadingProjects } = useProject();

  const handleDelete = async (e: React.MouseEvent, id: string, projName: string) => {
    e.stopPropagation();
    if (confirm(`Delete project "${projName}"? This removes its board, memory, and sources.`)) {
      await deleteProject(id);
    }
  };

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    } catch (e) {
      return iso;
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-base font-bold text-stone-900 dark:text-stone-50 tracking-tight flex items-center gap-2">
            <FolderKanban className="w-5 h-5 text-[var(--accent)]" />
            <span>Projects</span>
          </h2>
          <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">
            Each project has its own board, decision memory, and connected sources. Pick one to work in, or start a new one.
          </p>
        </div>
        <button
          onClick={startNewProjectSetup}
          className="px-3 py-1.5 rounded-[var(--r-sm)] bg-[var(--accent)] text-white text-xs font-semibold hover:opacity-95 active:scale-95 transition-transform flex items-center gap-1.5 cursor-pointer shadow-sm"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>New project</span>
        </button>
      </div>

      {loadingProjects ? (
        <div className="text-center font-mono py-12 text-stone-400 animate-pulse text-xs">Loading projects…</div>
      ) : projects.length === 0 ? (
        <div className="border border-dashed border-stone-250 dark:border-stone-800 rounded-[var(--r-lg)] p-12 text-center">
          <FolderKanban className="w-8 h-8 text-stone-300 mx-auto mb-3" />
          <h3 className="font-semibold text-stone-900 dark:text-stone-100 text-sm">No projects yet</h3>
          <p className="text-xs text-stone-500 mt-1 mb-4">Start a new project — drop in your docs, calls, and whiteboards and we'll build the board.</p>
          <button
            onClick={startNewProjectSetup}
            className="px-3 py-1.5 rounded-[var(--r-sm)] bg-[var(--accent)] text-white text-xs font-semibold hover:opacity-95 active:scale-95 transition-transform inline-flex items-center gap-1.5 cursor-pointer shadow-sm"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New project</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((p) => {
            const isActive = p.id === activeProjectId;
            return (
              <div
                key={p.id}
                onClick={() => selectProject(p.id)}
                className={`group p-4 rounded-[var(--r-lg)] border bg-white dark:bg-stone-950 cursor-pointer transition-all hover:border-stone-400 dark:hover:border-stone-700 hover:shadow-[var(--shadow-1)] ${isActive ? 'border-[var(--accent)] ring-1 ring-[var(--accent)]/30' : 'border-stone-200 dark:border-stone-850'}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span className="w-9 h-9 shrink-0 grid place-items-center rounded-[var(--r-md)] bg-[var(--accent-bg)] text-[var(--accent)] font-mono font-bold text-sm uppercase">
                      {p.name.slice(0, 1)}
                    </span>
                    <div className="min-w-0">
                      <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100 truncate">{p.name}</h3>
                      <span className="text-[10px] font-mono text-stone-400 flex items-center gap-1">
                        <Clock className="w-3 h-3" /> {formatDate(p.createdAt)}
                      </span>
                    </div>
                  </div>
                  {isActive && (
                    <span className="text-[9px] font-bold uppercase tracking-wide text-[var(--accent)] bg-[var(--accent-bg)] px-1.5 py-0.5 rounded">
                      Active
                    </span>
                  )}
                </div>

                <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                  <div className="bg-stone-50 dark:bg-stone-900/60 rounded p-1.5">
                    <span className="block text-sm font-bold text-stone-800 dark:text-stone-200">{p.itemCount}</span>
                    <span className="text-[9px] uppercase tracking-wide text-stone-400 font-mono">Cards</span>
                  </div>
                  <div className="bg-stone-50 dark:bg-stone-900/60 rounded p-1.5">
                    <span className="block text-sm font-bold text-stone-800 dark:text-stone-200">{p.decisionCount}</span>
                    <span className="text-[9px] uppercase tracking-wide text-stone-400 font-mono">Decisions</span>
                  </div>
                  <div className="bg-stone-50 dark:bg-stone-900/60 rounded p-1.5">
                    <span className="block text-sm font-bold text-stone-800 dark:text-stone-200">{p.sourceCount}</span>
                    <span className="text-[9px] uppercase tracking-wide text-stone-400 font-mono">Sources</span>
                  </div>
                </div>

                <div className="mt-4 flex items-center justify-between">
                  <span className="text-xs font-semibold text-[var(--accent)] flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    Open <ArrowRight className="w-3.5 h-3.5" />
                  </span>
                  <button
                    onClick={(e) => handleDelete(e, p.id, p.name)}
                    className="p-1.5 rounded text-stone-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Delete project"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
