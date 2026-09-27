import React, { useRef, useState } from 'react';
import {
  FileText,
  Video,
  Image as ImageIcon,
  Github,
  ArrowRight,
  X,
  Check,
  UploadCloud,
  Sparkles
} from 'lucide-react';
import { useProject } from '../context/ProjectContext.js';
import { DraftSource, DraftSourceKind, NewProjectDraft } from '../types.js';
import { INGEST_ACCEPT } from '../lib/backend.js';

// Which uploaded files we can actually read client-side. Everything else is
// captured as metadata and ingested for real in a later backend pass.
const TEXT_EXT = ['txt', 'md', 'csv', 'json'];
const isTextFile = (name: string) => TEXT_EXT.includes((name.split('.').pop() || '').toLowerCase());

interface ZoneConfig {
  kind: DraftSourceKind;
  label: string;
  hint: string;
  accept: string;
  icon: React.ComponentType<{ className?: string }>;
}

const ZONES: ZoneConfig[] = [
  // Files go to the backend ingestion pipeline — v1 types only (plans/ingestion.md §9).
  { kind: 'file', label: 'Files', hint: 'docs, PDFs, specs', accept: INGEST_ACCEPT, icon: FileText },
  { kind: 'video', label: 'Videos', hint: 'meeting & client calls', accept: '.mp4,.mov,.m4a,.wav', icon: Video },
  { kind: 'image', label: 'Images', hint: 'whiteboards, diagrams', accept: '.png,.jpg,.jpeg,.svg', icon: ImageIcon }
];

const acceptsFile = (zone: ZoneConfig, name: string) =>
  zone.accept.split(',').includes(`.${(name.split('.').pop() || '').toLowerCase()}`);

const GITHUB_RE = /^(https?:\/\/)?(www\.)?github\.com\/[\w.-]+\/[\w.-]+\/?$/i;

const UploadRow: React.FC<{
  zone: ZoneConfig;
  sources: DraftSource[];
  onAdd: (files: FileList) => void;
  onRemove: (name: string) => void;
  error?: string;
}> = ({ zone, sources, onAdd, onRemove, error }) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const Icon = zone.icon;
  const mine = sources.filter(s => s.kind === zone.kind);

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); if (e.dataTransfer.files?.length) onAdd(e.dataTransfer.files); }}
      className={`rounded-[var(--r-md)] border px-3.5 py-3 transition-colors ${over ? 'border-[var(--accent)] bg-[var(--accent-bg)]' : 'border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-950'}`}
    >
      <div className="flex items-center gap-3">
        <span className="w-8 h-8 shrink-0 grid place-items-center rounded-[var(--r-sm)] bg-stone-100 dark:bg-stone-900 text-stone-500 dark:text-stone-400">
          <Icon className="w-4 h-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold text-stone-800 dark:text-stone-200">{zone.label}</div>
          <div className="text-[11px] text-stone-400">{zone.hint}</div>
        </div>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="shrink-0 px-2.5 py-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 text-[11px] font-semibold text-stone-600 dark:text-stone-300 hover:border-[var(--accent)] hover:text-[var(--accent)] cursor-pointer flex items-center gap-1.5"
        >
          <UploadCloud className="w-3.5 h-3.5" /> Browse
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={zone.accept}
          className="hidden"
          aria-label={`Upload ${zone.label.toLowerCase()}: ${zone.hint}`}
          onChange={(e) => { if (e.target.files?.length) onAdd(e.target.files); e.target.value = ''; }}
        />
      </div>

      {error && (
        <p id={`np-zone-${zone.kind}-error`} role="alert" className="mt-2 text-[11px] text-[var(--verdict-conf-txt)]">{error}</p>
      )}

      {mine.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {mine.map(s => (
            <span key={s.name} className="inline-flex items-center gap-1.5 pl-2 pr-1 py-1 rounded-full bg-stone-100 dark:bg-stone-900 text-[10px] font-mono text-stone-600 dark:text-stone-300">
              <Check className="w-3 h-3 text-emerald-500" />
              <span className="max-w-[160px] truncate">{s.name}</span>
              <button type="button" onClick={() => onRemove(s.name)} className="p-0.5 rounded-full hover:bg-stone-200 dark:hover:bg-stone-800 cursor-pointer" aria-label={`Remove ${s.name}`}>
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

export const NewProjectSetup: React.FC = () => {
  const { projects, cancelSetup, beginClarification } = useProject();
  // Inline "unsupported type" message per zone (§4.10: each zone rejects others' types inline).
  const [zoneErrors, setZoneErrors] = useState<Partial<Record<DraftSourceKind, string>>>({});
  // Real File objects for the 'file' zone, keyed by name — uploaded to backend/ on generate.
  const [fileBlobs, setFileBlobs] = useState<Record<string, File>>({});
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [github, setGithub] = useState('');
  const [githubSkipped, setGithubSkipped] = useState(false);
  const [sources, setSources] = useState<DraftSource[]>([]);

  const canContinue = name.trim().length > 0 && description.trim().length > 0;
  const githubValid = github.trim() === '' || GITHUB_RE.test(github.trim());

  const addFiles = async (kind: DraftSourceKind, files: FileList) => {
    const zone = ZONES.find(z => z.kind === kind)!;
    const incoming: DraftSource[] = [];
    const blobs: Record<string, File> = {};
    const refused: string[] = [];
    for (const file of Array.from(files)) {
      if (!acceptsFile(zone, file.name)) {
        refused.push(file.name);
        continue;
      }
      if (kind === 'file') blobs[file.name] = file;
      let content: string | undefined;
      if (kind === 'file' && isTextFile(file.name)) {
        try { content = await file.text(); } catch (e) { /* keep as metadata */ }
      }
      incoming.push({ name: file.name, kind, size: file.size, content, status: 'ready' });
    }
    setSources(prev => {
      const names = new Set(prev.map(s => s.name));
      return [...prev, ...incoming.filter(s => !names.has(s.name))];
    });
    setFileBlobs(prev => ({ ...blobs, ...prev }));
    setZoneErrors(prev => ({
      ...prev,
      [kind]: refused.length
        ? `Can't add ${refused.join(', ')} — unsupported type for ${zone.label}. Accepted: ${zone.accept.split(',').join(', ')}.`
        : undefined
    }));
  };

  const removeSource = (name: string) => {
    setSources(prev => prev.filter(s => s.name !== name));
    setFileBlobs(prev => { const next = { ...prev }; delete next[name]; return next; });
  };

  const handleContinue = () => {
    if (!canContinue || !githubValid) return;
    const draft: NewProjectDraft = {
      name: name.trim(),
      description: description.trim(),
      github: githubSkipped ? '' : github.trim(),
      sources,
      answers: []
    };
    const files = sources.filter(s => s.kind === 'file' && fileBlobs[s.name]).map(s => fileBlobs[s.name]);
    beginClarification(draft, files);
  };

  return (
    <div className="fixed inset-0 z-50 bg-[var(--bg-app)] text-[var(--text-primary)] overflow-y-auto">
      {/* Close only offered when there's an existing project to fall back to */}
      {projects.length > 0 && (
        <button
          onClick={cancelSetup}
          className="absolute top-4 right-4 p-2 rounded-[var(--r-sm)] text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-900 cursor-pointer"
          aria-label="Cancel new project"
        >
          <X className="w-5 h-5" />
        </button>
      )}

      <div className="max-w-[640px] mx-auto px-6 py-14 space-y-8">
        <header className="space-y-1.5">
          <h1 className="text-2xl font-bold tracking-tight text-stone-900 dark:text-stone-50">Start a new project</h1>
          <p className="text-sm text-stone-500 dark:text-stone-400 leading-relaxed">
            Drop in what you already have. We'll read it and ask a few questions before building your board.
          </p>
        </header>

        {/* Name */}
        <div className="space-y-1.5">
          <label htmlFor="np-name" className="text-xs font-semibold text-stone-500 dark:text-stone-400">
            Project name <span className="text-[var(--accent)]">*</span>
          </label>
          <input
            id="np-name"
            type="text"
            autoFocus
            required
            aria-required="true"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Acme redesign"
            className="w-full bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-800 rounded-[var(--r-md)] px-3 py-2 text-sm text-stone-800 dark:text-stone-100 placeholder-stone-400 focus:outline-none focus:border-[var(--accent)]"
          />
        </div>

        {/* Description (required) */}
        <div className="space-y-1.5">
          <label htmlFor="np-desc" className="text-xs font-semibold text-stone-500 dark:text-stone-400">
            Description <span className="text-[var(--accent)]">*</span>
          </label>
          <textarea
            id="np-desc"
            required
            aria-required="true"
            rows={4}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What is this project? Goals, stakeholders, context…"
            className="w-full bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-800 rounded-[var(--r-md)] px-3 py-2 text-sm text-stone-800 dark:text-stone-100 placeholder-stone-400 focus:outline-none focus:border-[var(--accent)] resize-y"
          />
        </div>

        {/* Sources (optional) — three distinct stacked inputs */}
        <div className="space-y-2.5">
          <div className="flex items-baseline justify-between">
            <span className="text-xs font-semibold text-stone-500 dark:text-stone-400">Sources</span>
            <span className="text-[11px] text-stone-400">optional</span>
          </div>
          {ZONES.map(zone => (
            <UploadRow
              key={zone.kind}
              zone={zone}
              sources={sources}
              onAdd={(files) => addFiles(zone.kind, files)}
              onRemove={removeSource}
              error={zoneErrors[zone.kind]}
            />
          ))}
        </div>

        {/* GitHub (optional, skippable) */}
        <div className="space-y-1.5">
          <div className="flex items-baseline justify-between">
            <label htmlFor="np-github" className="text-xs font-semibold text-stone-500 dark:text-stone-400">GitHub repo</label>
            <button
              type="button"
              onClick={() => { setGithubSkipped(s => !s); if (!githubSkipped) setGithub(''); }}
              className="text-[11px] text-stone-400 hover:text-[var(--accent)] cursor-pointer"
            >
              {githubSkipped ? 'Add repo' : 'Skip — add later'}
            </button>
          </div>
          {!githubSkipped && (
            <>
              <div className="relative">
                <Github className="w-4 h-4 text-stone-400 absolute left-3 top-2.5" />
                <input
                  id="np-github"
                  type="text"
                  value={github}
                  onChange={(e) => setGithub(e.target.value)}
                  placeholder="github.com/org/repo"
                  className={`w-full bg-white dark:bg-stone-950 border rounded-[var(--r-md)] pl-9 pr-3 py-2 text-sm text-stone-800 dark:text-stone-100 placeholder-stone-400 focus:outline-none ${githubValid ? 'border-stone-200 dark:border-stone-800 focus:border-[var(--accent)]' : 'border-red-300 dark:border-red-900 focus:border-red-400'}`}
                />
              </div>
              <p className={`text-[11px] ${githubValid ? 'text-stone-400' : 'text-red-500'}`}>
                {githubValid ? "We'll scan existing code and track progress here once connected." : "That doesn't look like a repo URL"}
              </p>
            </>
          )}
        </div>

        {/* Primary CTA */}
        <div className="pt-2 space-y-2">
          <button
            onClick={handleContinue}
            disabled={!canContinue || !githubValid}
            className="w-full py-2.5 rounded-[var(--r-md)] bg-[var(--accent)] text-white text-sm font-semibold hover:opacity-95 active:scale-[0.99] transition-transform disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer flex items-center justify-center gap-2"
          >
            <Sparkles className="w-4 h-4" />
            Ingest &amp; continue
            <ArrowRight className="w-4 h-4" />
          </button>
          {!canContinue && (
            <p className="text-[11px] text-center text-stone-400">Add a name and description to continue</p>
          )}
        </div>
      </div>
    </div>
  );
};
