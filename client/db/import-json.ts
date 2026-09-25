import fs from 'fs';
import type { Repo } from './repo.js';
import { defaultAgents, defaultApiConfig, freshStore } from './seed.js';
import type { StoreShape } from './types.js';

// First-run bootstrap: get the legacy client/data/database.json (or, failing that, the built-in
// seed) into an empty database exactly once. After that the JSON file is never read or written
// again — it stays in git only as the seed a fresh clone imports.

// Recognises the two shapes the old JSON store accepted. Returns null for anything else
// (the old code fell back to the built-in seed in that case too).
export function parseStoreFile(parsed: Record<string, any> | null): StoreShape | null {
  // Current multi-project format.
  if (parsed && Array.isArray(parsed.projects)) {
    return {
      apiConfig: { ...defaultApiConfig, ...parsed.apiConfig },
      agents:
        Array.isArray(parsed.agents) && parsed.agents.length
          ? parsed.agents
          : defaultAgents.map(a => ({ ...a })),
      projects: parsed.projects
    };
  }

  // Legacy single-DBState format → becomes one project.
  if (parsed && Array.isArray(parsed.items)) {
    return {
      apiConfig: { ...defaultApiConfig, ...parsed.apiConfig },
      agents:
        Array.isArray(parsed.agents) && parsed.agents.length
          ? parsed.agents
          : defaultAgents.map(a => ({ ...a })),
      projects: [
        {
          id: 'proj-core',
          name: 'Core Platform',
          createdAt: '2026-03-01T00:00:00Z',
          items: parsed.items || [],
          decisions: parsed.decisions || [],
          sources: parsed.sources || [],
          ingestQueue: parsed.ingestQueue || []
        }
      ]
    };
  }

  return null;
}

export type BootstrapResult = 'skipped' | 'imported' | 'seeded';

type Logger = Pick<Console, 'log' | 'warn'>;

export function bootstrap(repo: Repo, jsonPath: string, log: Logger = console): BootstrapResult {
  if (repo.isBootstrapped()) return 'skipped';

  if (!fs.existsSync(jsonPath)) {
    repo.importStore(freshStore());
    log.log(`[db] No ${jsonPath} to import — seeded the built-in starter project.`);
    return 'seeded';
  }

  let parsed: Record<string, any> | null;
  try {
    parsed = JSON.parse(fs.readFileSync(jsonPath, 'utf-8'));
  } catch (e) {
    // Never fall back to the seed here: that would hide the user's real data behind demo data.
    throw new Error(
      `Cannot import ${jsonPath}: it is not valid JSON (${(e as Error).message}). ` +
        `Fix it (or move it aside to start from the built-in seed) and restart.`
    );
  }

  const store = parseStoreFile(parsed);
  if (!store) {
    log.warn(`[db] ${jsonPath} isn't a recognised store format — seeding the built-in starter project instead.`);
    repo.importStore(freshStore());
    return 'seeded';
  }

  repo.importStore(store);
  const counts = store.projects.reduce(
    (acc, p) => ({
      items: acc.items + p.items.length,
      decisions: acc.decisions + p.decisions.length
    }),
    { items: 0, decisions: 0 }
  );
  log.log(
    `[db] Imported ${jsonPath}: ${store.projects.length} project(s), ${counts.items} item(s), ` +
      `${counts.decisions} decision(s), ${store.agents.length} agent(s). This file is no longer written to.`
  );
  return 'imported';
}
