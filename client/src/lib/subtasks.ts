export interface ParsedSubtask {
  text: string;
  checked: boolean;
  /** Preserve `- [ ]` vs plain `- ` so save does not rewrite the stored list style. */
  style: 'checkbox' | 'plain';
}

export interface SubtasksParse {
  subtasks: ParsedSubtask[];
  /** Description with the ## Subtasks / ## Subtask section removed. */
  body: string;
  hadSection: boolean;
}

const SUBTASK_HEADING = /^##\s+Subtasks?\s*$/i;
const ANY_H2 = /^##\s+\S/;
const ACCEPTANCE = /^##\s+Acceptance criteria\s*$/i;
const DEFINITION = /^##\s+Definition of done\s*$/i;
const CHECKBOX_ITEM = /^\s*-\s+\[([ xX])\]\s*(.*)$/;
const PLAIN_ITEM = /^\s*-\s+(.*)$/;

function splitLines(text: string): { lines: string[]; nl: '\n' | '\r\n' } {
  const source = text ?? '';
  return {
    lines: source.split(/\r?\n/),
    nl: source.includes('\r\n') ? '\r\n' : '\n',
  };
}

function joinTrimmed(lines: string[], nl: string): string {
  return lines.join(nl).replace(/^\s+|\s+$/g, '');
}

function parseItem(line: string): ParsedSubtask | null {
  const box = line.match(CHECKBOX_ITEM);
  if (box) {
    const text = box[2].trim();
    if (!text) return null;
    return { text, checked: box[1].toLowerCase() === 'x', style: 'checkbox' };
  }
  const plain = line.match(PLAIN_ITEM);
  if (plain) {
    const text = plain[1].trim();
    if (!text) return null;
    return { text, checked: false, style: 'plain' };
  }
  return null;
}

/** Pull `- [ ]` / `- [x]` / `- ` items under a ## Subtasks or ## Subtask heading. */
export function parseBoardSubtasks(description: string): SubtasksParse {
  const { lines, nl } = splitLines(description ?? '');
  const start = lines.findIndex(line => SUBTASK_HEADING.test(line));
  if (start < 0) {
    return { subtasks: [], body: description ?? '', hadSection: false };
  }

  const subtasks: ParsedSubtask[] = [];
  let end = start + 1;
  while (end < lines.length) {
    const line = lines[end];
    if (ANY_H2.test(line)) break;
    if (line.trim() === '') {
      end += 1;
      continue;
    }
    if (CHECKBOX_ITEM.test(line) || PLAIN_ITEM.test(line)) {
      const item = parseItem(line);
      if (item) subtasks.push(item);
      end += 1;
      continue;
    }
    break;
  }

  const before = lines.slice(0, start);
  const after = lines.slice(end);
  while (before.length && before[before.length - 1].trim() === '') before.pop();
  while (after.length && after[0].trim() === '') after.shift();

  const joined = before.length && after.length
    ? [...before, '', ...after]
    : [...before, ...after];

  return { subtasks, body: joinTrimmed(joined, nl), hadSection: true };
}

export function formatSubtaskLine(item: ParsedSubtask): string {
  if (item.style === 'plain') return `- ${item.text}`;
  return `- [${item.checked ? 'x' : ' '}] ${item.text}`;
}

function insertIndex(lines: string[]): number {
  const ac = lines.findIndex(line => ACCEPTANCE.test(line));
  if (ac >= 0) return ac;
  const done = lines.findIndex(line => DEFINITION.test(line));
  if (done >= 0) return done;
  return lines.length;
}

/**
 * Put a ## Subtasks block back into an edited body (before Acceptance criteria /
 * Definition of done, else at the end) so stripping it from the textarea is reversible.
 */
export function recomposeBoardDescription(body: string, subtasks: ParsedSubtask[]): string {
  const stripped = parseBoardSubtasks(body);
  const source = stripped.hadSection ? stripped.body : (body ?? '');
  const { lines, nl } = splitLines(source);
  const at = insertIndex(lines);

  const before = lines.slice(0, at);
  const after = lines.slice(at);
  while (before.length && before[before.length - 1].trim() === '') before.pop();
  while (after.length && after[0].trim() === '') after.shift();

  const block = ['## Subtasks', ...subtasks.map(formatSubtaskLine)];
  const parts = [
    ...before,
    ...(before.length ? [''] : []),
    ...block,
    ...(after.length ? [''] : []),
    ...after,
  ];
  return joinTrimmed(parts, nl);
}

export function subtasksFromGenerated(steps: string[] | undefined): ParsedSubtask[] {
  return (steps ?? [])
    .map(text => text.trim())
    .filter(Boolean)
    .map(text => ({ text, checked: false, style: 'checkbox' as const }));
}
