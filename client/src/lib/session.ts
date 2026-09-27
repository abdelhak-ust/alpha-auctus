export type SessionKind = 'guest' | 'user';

export interface SessionProfile {
  id: string;
  name: string;
  email: string;
  kind: SessionKind;
}

export const SESSION_KEY = 'nexus-session';
export const AUTH_KEY = 'nexus-authed';

/** Old clients that are already authed but have no session JSON. */
export const LEGACY_SESSION: SessionProfile = {
  id: 'legacy-user',
  name: 'You',
  email: '',
  kind: 'user',
};

export function createGuestProfile(now = Date.now()): SessionProfile {
  return {
    id: `guest-${now}`,
    name: 'Guest',
    email: `guest-${now}@nexus.local`,
    kind: 'guest',
  };
}

export function createUserProfile(email: string, now = Date.now()): SessionProfile {
  const trimmed = email.trim();
  const local = trimmed.split('@')[0] || trimmed || 'You';
  return {
    id: `user-${now}`,
    name: local,
    email: trimmed,
    kind: 'user',
  };
}

export function readSession(): SessionProfile | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<SessionProfile>;
    if (
      typeof parsed.id !== 'string' ||
      typeof parsed.name !== 'string' ||
      typeof parsed.email !== 'string' ||
      (parsed.kind !== 'guest' && parsed.kind !== 'user')
    ) {
      return null;
    }
    return { id: parsed.id, name: parsed.name, email: parsed.email, kind: parsed.kind };
  } catch {
    return null;
  }
}

export function writeSession(profile: SessionProfile): void {
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify(profile));
  } catch {
    // Private mode / quota — enter the app anyway; name falls back on next read.
  }
}

export function isAuthed(): boolean {
  try {
    return localStorage.getItem(AUTH_KEY) === '1';
  } catch {
    return false;
  }
}

export function writeAuthFlag(): void {
  try {
    localStorage.setItem(AUTH_KEY, '1');
  } catch {
    // Same as today: enter even if storage is blocked.
  }
}

export function clearAuth(): void {
  try {
    localStorage.removeItem(AUTH_KEY);
    localStorage.removeItem(SESSION_KEY);
  } catch {
    // Still flip in-memory authed in the caller.
  }
}

/** Guest shows "Guest"; signed-in users show email (or name if email is empty). */
export function sessionDisplayName(profile: SessionProfile): string {
  if (profile.kind === 'guest') return profile.name;
  return profile.email || profile.name;
}

export function resolveSession(): SessionProfile {
  return readSession() ?? LEGACY_SESSION;
}
