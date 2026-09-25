// Built-in workspace defaults and the first-run seed project. Moved verbatim out of
// client/server.ts (plans/node-sqlite-store.md) — used when no client/data/database.json
// exists to import from.
import type { Agent } from '../src/types.js';
import type { ApiConfig, ProjectRecord, StoreShape } from './types.js';

// Workspace-wide catalog of assignable AI agents, shared across all projects.
export const defaultAgents: Agent[] = [
  { id: 'figma-ai', name: 'Figma AI', kind: 'design', description: 'Creates Figma designs and mockups.', builtin: true },
  { id: 'github-copilot', name: 'GitHub Copilot', kind: 'code', description: 'Implements and reviews code.', builtin: true },
  { id: 'frontend-dev', name: 'Frontend Dev Agent', kind: 'code', description: 'Builds UI and frontend features.', builtin: true },
  { id: 'backend-dev', name: 'Backend Dev Agent', kind: 'code', description: 'Builds APIs and backend services.', builtin: true },
  { id: 'qa-tester', name: 'QA Tester Agent', kind: 'qa', description: 'Exploratory testing and bug triage.', builtin: true },
  { id: 'docs-writer', name: 'Docs Writer Agent', kind: 'docs', description: 'Writes and updates documentation.', builtin: true },
  { id: 'unit-test-gen', name: 'Unit Test Generator Agent', kind: 'test', description: 'Generates unit tests for code.', builtin: true },
  { id: 'security-compliance', name: 'Security & Compliance Agent', kind: 'security', description: 'Reviews security and compliance.', builtin: true }
];

export const defaultApiConfig: ApiConfig = {
  provider: 'managed',
  providerType: 'gemini',
  apiKey: '',
  region: 'us-central1',
  embeddingsProvider: 'gemini',
  embeddingsKey: '',
  noRetention: true,
  isolateTenant: true
};

// The pre-seeded backlog/memory that ships as the first ("Core Platform") project.
export function seedSlice(): Pick<ProjectRecord, 'items' | 'decisions' | 'sources' | 'ingestQueue'> {
  return {
    items: [
      {
        id: 71,
        title: "Billing Authorization Security Block",
        description: "Integrate role-based authorization parameters within the core subscription and checkout invoice controllers. Validate tier-based features on both client-side and server-side.",
        status: "in_progress",
        priority: "P1",
        assignee: "AM",
        area: "auth",
        created_at: "2026-05-15T10:00:00Z",
        source: { type: "ticket", name: "JIRA-402", snippet: "Implement backend RBAC for invoice controllers." },
        verdict: null
      },
      {
        id: 88,
        title: "High-volume CSV Export Reporter",
        description: "Asynchronous backend reporting systems that stream large export data directly into structured storage and return secure expirable download URLs. Replaces old synchronous server-blocking CSV dumps.",
        status: "done",
        priority: "P1",
        assignee: "JD",
        area: "reporting",
        created_at: "2026-05-20T11:00:00Z",
        source: { type: "sheet", name: "Product Backlog Sync", snippet: "Row #88: Asynchronous background worker report generator." },
        verdict: {
          type: "net-new",
          confidence: 100,
          message: "Net-new — nothing like this yet",
          candidates: []
        }
      },
      {
        id: 120,
        title: "Post-Login Deep-Linking Redirect Flow",
        description: "Sequence router deep-linking and state recovery redirect flags once standard login validation completes successfully. Currently breaks if enterprise clients land with deep nested subroutes directly.",
        status: "inbox",
        priority: "P2",
        assignee: "AM",
        area: "auth",
        created_at: "2026-05-28T09:30:00Z",
        source: { type: "email", name: "Enterprise Workspace HelpDesk", snippet: "Deep linking redirects after nested subdomain logins fail intermittently." },
        verdict: {
          type: "impact",
          confidence: 85,
          message: "Touches the same authentication flow as Billing Authorization Security Block (#71). Ensure route protection structures are dry.",
          candidates: [
            { id: "71", type: "item", title: "Billing Authorization Security Block", reason: "Both modify global auth validation parameters.", confidence: 85 }
          ],
          citation: {
            id: "71",
            type: "item",
            title: "Billing Authorization Security Block",
            snippet: "Integrate role-based authorization parameters within core controllers."
          }
        }
      },
      {
        id: 95,
        title: "Export Billing Details directly to CSV file button",
        description: "Add a button directly on the invoice overview tab to trigger export logs into a CSV download. Needs to compile billing summaries.",
        status: "next",
        priority: "P2",
        assignee: "JD",
        area: "reporting",
        created_at: "2026-05-25T14:45:00Z",
        source: { type: "sheet", name: "Product Backlog Sync", snippet: "Row #95: Export raw tables to file outputs." },
        verdict: {
          type: "duplicate",
          confidence: 91,
          message: "Duplicate of existing card High-volume CSV Export Reporter (#88)",
          candidates: [
            { id: "88", type: "item", title: "High-volume CSV Export Reporter", reason: "Duplicates the CSV export workers and mechanisms already made in #88.", confidence: 91 }
          ],
          citation: {
            id: "88",
            type: "item",
            title: "High-volume CSV Export Reporter",
            snippet: "Asynchronous backend reporting systems that stream large export data..."
          }
        }
      }
    ],
    decisions: [
      {
        id: 4,
        title: "Rely on customer IdP instead of building built-in custom SSO",
        description: "In the 2026-03 Architecture call we decided to rely heavily on the customer's enterprise Identity Provider (IdP) via single sign-on redirect workflows instead of creating our own database-backed custom SSO models, minimizing credential management overhead and securing data flows.",
        date: "2026-03-14",
        area: "auth",
        createdBy: "AM"
      },
      {
        id: 9,
        title: "Enforce multi-factor auth (MFA) as absolute default",
        description: "To meet regulatory governance structures and compliance objectives, Multi-Factor Authentication (MFA) must be enforced statically for all high-privilege executive and administrator panels.",
        date: "2026-04-10",
        area: "auth",
        createdBy: "AM"
      },
      {
        id: 12,
        title: "Consolidate reporting CSV outputs on server side",
        description: "We decide to use a unified asynchronous exporter for CSV reports instead of spawning individual client-side scraping scripts, ensuring security limits.",
        date: "2026-05-12",
        area: "reporting",
        createdBy: "JD"
      }
    ],
    sources: [
      { id: "src-sheet", name: "Google Backlog Sync Sheet", type: "sheet", status: "synced", lastSynced: "2 minutes ago", pendingCount: 0 },
      { id: "src-transcript", name: "🎙 Arch Call Transcripts", type: "transcript", status: "synced", lastSynced: "30 minutes ago", pendingCount: 3 },
      { id: "src-email", name: "✉ Customer Feedback Inbox", type: "email", status: "synced", lastSynced: "1 hour ago", pendingCount: 4 },
      { id: "src-ticket", name: "Jira Syncing Endpoint", type: "ticket", status: "needs_auth", pendingCount: 0 }
    ],
    ingestQueue: [
      {
        id: "ingest-1",
        title: "Add custom enterprise database-level auth system for custom SSO logins",
        description: "Develop custom internal password hashes and token providers supporting on-premise custom SSO login methods directly in database tables.",
        area: "auth",
        priority: "P1",
        sourceId: "src-transcript",
        sourceSnippet: "We need custom SSO that can connect direct credentials from database tables, bypass direct IdPs if customer doesn't have an outer identity portal.",
        verdict: {
          type: "conflict",
          confidence: 82,
          message: "Conflicts with architectural Decision #4 (Rely on customer IdP instead of building built-in custom SSO)",
          candidates: [
            {
              id: "4",
              type: "decision",
              title: "Rely on customer IdP instead of building built-in custom SSO",
              reason: "Directly contradicts the decision to rely strictly on the customer's IdP to avoid creating a database SSO repository.",
              confidence: 82
            }
          ],
          citation: {
            id: "4",
            type: "decision",
            title: "Rely on customer IdP instead of building built-in custom SSO",
            snippet: "decided to rely heavily on the customer's enterprise Identity Provider ... instead of creating our own database-backed custom SSO model"
          }
        }
      },
      {
        id: "ingest-2",
        title: "Synchronous client-side report download wizard",
        description: "Create a visual wizard allowing immediate client-side table rendering and direct browser CSV compilations.",
        area: "reporting",
        priority: "P2",
        sourceId: "src-email",
        sourceSnippet: "Please add standard browser-side scraping download button for current table results directly.",
        verdict: {
          type: "conflict",
          confidence: 89,
          message: "Conflicts with architectural Decision #12 (Consolidate reporting CSV outputs on server side)",
          candidates: [
            {
              id: "12",
              type: "decision",
              title: "Consolidate reporting CSV outputs on server side",
              reason: "Directly violates the decision to utilize asynchronous server workers over browser-based scraper dumps.",
              confidence: 89
            }
          ],
          citation: {
            id: "12",
            type: "decision",
            title: "Consolidate reporting CSV outputs on server side",
            snippet: "unified asynchronous exporter for CSV reports instead of spawning individual client-side scraping scripts"
          }
        }
      }
    ]
  };
}

// What a brand-new install starts with when there is no JSON file to import.
export function freshStore(): StoreShape {
  return {
    projects: [
      {
        id: 'proj-core',
        name: 'Core Platform',
        createdAt: '2026-03-01T00:00:00Z',
        ...seedSlice()
      }
    ],
    apiConfig: { ...defaultApiConfig },
    agents: defaultAgents.map(a => ({ ...a }))
  };
}
