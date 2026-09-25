import Database from 'better-sqlite3';
import fs from 'fs';
import path from 'path';
import { MIGRATIONS } from './migrations.js';

export type DB = Database.Database;

// Same directory the JSON store lived in. NEXUS_DB_PATH overrides it (tests use ':memory:').
export function resolveDbPath(): string {
  return process.env.NEXUS_DB_PATH || path.join(process.cwd(), 'data', 'nexus.db');
}

export function openDatabase(file: string = resolveDbPath()): DB {
  if (file !== ':memory:') {
    fs.mkdirSync(path.dirname(file), { recursive: true });
  }
  const db = new Database(file);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON'); // per-connection in SQLite; this is what makes project deletes cascade
  migrate(db);
  return db;
}

export function migrate(db: DB): void {
  const current = db.pragma('user_version', { simple: true }) as number;
  for (let version = current; version < MIGRATIONS.length; version++) {
    // DDL is transactional in SQLite: a failed migration leaves the database at the old version.
    db.transaction(() => {
      db.exec(MIGRATIONS[version]);
      db.pragma(`user_version = ${version + 1}`);
    })();
  }
}
