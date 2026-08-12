/**
 * Typed client for the NOEMA API.
 *
 * Cookies carry the session, so every request sends credentials and every mutation
 * echoes the CSRF token the server set at login. In Phase 1 the response types below
 * are hand-written; issue #14 replaces them with types generated from `/openapi.json`
 * so a backend change fails the web typecheck instead of failing at runtime.
 */

// In demo mode the API is this same deployment's route handlers, so requests go
// to the current origin. Deriving that from the demo flag rather than from an
// empty NEXT_PUBLIC_API_URL: a platform that drops empty environment variables
// would silently send a deployed preview at localhost:8000.
const BASE =
  process.env.NEXT_PUBLIC_DEMO === '1'
    ? ''
    : (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000');
const CSRF_COOKIE = 'noema_csrf';

export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance?: string;
  errors?: { field: string; message: string }[];
}

function asText(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value == null) return '';
  return JSON.stringify(value);
}

export class ApiError extends Error {
  constructor(readonly problem: ProblemDetail) {
    // Coerced, because `detail` is only a string by NOEMA's convention. Anything
    // else in front of the API — a proxy, a gateway — can return a body whose
    // detail is an object, and `super(object)` puts a literal "[object Object]"
    // on the screen.
    super(asText(problem.detail) || asText(problem.title) || 'Request failed');
    this.name = 'ApiError';
  }

  get isUnauthorized() {
    return this.problem.status === 401;
  }
}

function csrfToken(): string {
  if (typeof document === 'undefined') return '';
  const match = document.cookie.match(new RegExp(`(?:^|; )${CSRF_COOKIE}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : '';
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = init.method ?? 'GET';
  const headers = new Headers(init.headers);
  headers.set('content-type', 'application/json');
  if (method !== 'GET' && method !== 'HEAD') {
    headers.set('x-csrf-token', csrfToken());
  }

  const response = await fetch(`${BASE}/api/v1${path}`, {
    ...init,
    method,
    headers,
    credentials: 'include',
  });

  if (response.status === 204) return undefined as T;

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      body ?? {
        type: 'about:blank',
        title: 'Request failed',
        status: response.status,
        detail: response.statusText,
      },
    );
  }
  return body as T;
}

// ── Types ────────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  display_name: string;
  settings: Record<string, unknown>;
  created_at: string;
}

export interface Workspace {
  id: string;
  title: string;
  slug: string;
  position: number;
  created_at: string;
}

export interface Subject {
  id: string;
  workspace_id: string;
  title: string;
  slug: string;
  position: number;
  created_at: string;
}

export interface Notebook {
  id: string;
  subject_id: string;
  title: string;
  slug: string;
  description: string | null;
  ai_provider_override: string | null;
  retrieval_settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Note {
  id: string;
  notebook_id: string;
  title: string;
  content_md: string;
  links: string[];
  created_at: string;
  updated_at: string;
}

export interface Provider {
  name: string;
  configured: boolean;
  capabilities: Record<string, unknown>;
  is_default: boolean;
}

export interface Credential {
  id: string;
  provider: string;
  label: string;
  last4: string;
  created_at: string;
  last_used_at: string | null;
  last_verified_at: string | null;
  verification_error: string | null;
}

interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export type CardType = 'basic' | 'reverse' | 'cloze' | 'image' | 'concept' | 'definition' | 'code';

export interface Card {
  id: string;
  notebook_id: string;
  concept_id: string | null;
  type: CardType;
  front_md: string;
  back_md: string;
  origin: 'user' | 'ai';
  approved_at: string | null;
  created_at: string;
}

export interface IntervalPreview {
  again: number;
  hard: number;
  good: number;
  easy: number;
}

export interface DueCard extends Card {
  due_at: string | null;
  state: 'new' | 'learning' | 'review' | 'relearning';
  reps: number;
  preview: IntervalPreview;
}

export interface ReviewResult {
  card_id: string;
  due_at: string;
  scheduled_days: number;
  state: string;
  mastery: number | null;
}

export interface Mastery {
  concept_id: string;
  concept_name: string;
  mastery: number;
  provisional: boolean;
  components: Record<string, number | boolean>;
  last_evidence_at: string | null;
}

export interface PlanItem {
  ref_id: string;
  kind: string;
  concept_id: string | null;
  concept_name: string;
  estimated_seconds: number;
}

export interface PlanBlock {
  kind: 'warmup' | 'repair' | 'practice' | 'cooldown';
  why: string;
  minutes: number;
  items: PlanItem[];
}

export interface SessionPlan {
  rationale: string;
  estimated_minutes: number;
  blocks: PlanBlock[];
}

export type TutorMode = 'explain' | 'socratic' | 'examiner' | 'study_partner' | 'feynman';

// ── Endpoints ────────────────────────────────────────────────────────────────

export const api = {
  register: (email: string, password: string, displayName: string) =>
    request<{ user: User; csrf_token: string }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, display_name: displayName }),
    }),

  login: (email: string, password: string) =>
    request<{ user: User; csrf_token: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  me: () => request<User>('/auth/me'),

  workspaces: () => request<Page<Workspace>>('/workspaces'),
  createWorkspace: (title: string) =>
    request<Workspace>('/workspaces', { method: 'POST', body: JSON.stringify({ title }) }),

  subjects: (workspaceId?: string) =>
    request<Page<Subject>>(`/subjects${workspaceId ? `?workspace_id=${workspaceId}` : ''}`),
  createSubject: (workspaceId: string, title: string) =>
    request<Subject>('/subjects', {
      method: 'POST',
      body: JSON.stringify({ workspace_id: workspaceId, title }),
    }),

  notebooks: (subjectId?: string) =>
    request<Page<Notebook>>(`/notebooks${subjectId ? `?subject_id=${subjectId}` : ''}`),
  notebook: (id: string) => request<Notebook>(`/notebooks/${id}`),
  createNotebook: (subjectId: string, title: string, description?: string) =>
    request<Notebook>('/notebooks', {
      method: 'POST',
      body: JSON.stringify({ subject_id: subjectId, title, description }),
    }),
  deleteNotebook: (id: string) => request<void>(`/notebooks/${id}`, { method: 'DELETE' }),

  notes: (notebookId: string) => request<Page<Note>>(`/notes?notebook_id=${notebookId}`),
  note: (id: string) => request<Note>(`/notes/${id}`),
  createNote: (notebookId: string, title: string, contentMd = '') =>
    request<Note>('/notes', {
      method: 'POST',
      body: JSON.stringify({ notebook_id: notebookId, title, content_md: contentMd }),
    }),
  updateNote: (id: string, patch: Partial<Pick<Note, 'title' | 'content_md'>>) =>
    request<Note>(`/notes/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteNote: (id: string) => request<void>(`/notes/${id}`, { method: 'DELETE' }),

  providers: () => request<Provider[]>('/ai/providers'),
  credentials: () => request<Credential[]>('/ai/credentials'),
  addCredential: (provider: string, label: string, apiKey: string) =>
    request<Credential>('/ai/credentials', {
      method: 'POST',
      body: JSON.stringify({ provider, label, api_key: apiKey }),
    }),
  deleteCredential: (id: string) =>
    request<void>(`/ai/credentials/${id}`, { method: 'DELETE' }),

  dueCards: (notebookId?: string, limit = 50) =>
    request<DueCard[]>(
      `/cards?due=true&limit=${limit}${notebookId ? `&notebook_id=${notebookId}` : ''}`,
    ),
  pendingCards: (notebookId: string) =>
    request<DueCard[]>(`/cards?pending_approval=true&notebook_id=${notebookId}`),
  createCard: (notebookId: string, front: string, back: string) =>
    request<Card>('/cards', {
      method: 'POST',
      body: JSON.stringify({ notebook_id: notebookId, front_md: front, back_md: back }),
    }),
  generateCards: (notebookId: string, limit = 20) =>
    request<Card[]>('/cards/generate', {
      method: 'POST',
      body: JSON.stringify({ notebook_id: notebookId, limit }),
    }),
  approveCard: (id: string) => request<Card>(`/cards/${id}/approve`, { method: 'POST' }),
  updateCard: (id: string, patch: Partial<Pick<Card, 'front_md' | 'back_md'>>) =>
    request<Card>(`/cards/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteCard: (id: string) => request<void>(`/cards/${id}`, { method: 'DELETE' }),

  review: (cardId: string, rating: 1 | 2 | 3 | 4, elapsedMs: number, confidence?: number) =>
    request<ReviewResult>('/reviews', {
      method: 'POST',
      body: JSON.stringify({
        card_id: cardId,
        rating,
        elapsed_ms: elapsedMs,
        confidence,
      }),
    }),

  mastery: (weak = false) => request<Mastery[]>(`/mastery?weak=${weak}`),

  plan: (minutes: number) =>
    request<SessionPlan>(`/learning-session/plan?minutes=${minutes}`),

  deleteAccount: () => request<Deletion>('/me', { method: 'DELETE' }),

  meta: () => request<Meta>('/meta'),
};

export interface Meta {
  mode: string;
  /** True when this deployment cannot reach the internet at all. */
  local: boolean;
  allow_signups: boolean;
  default_provider: string;
  embedding_model: string;
  version: string;
}

export interface Deletion {
  deleted_at: string;
  purge_after: string;
  grace_days: number;
  detail: string;
}

/**
 * Downloads the account export.
 *
 * Not part of `api` because the response is a zip, not JSON — `request` would try
 * to parse it and throw on the first byte.
 */
export async function downloadExport(): Promise<void> {
  const response = await fetch(`${BASE}/api/v1/me/export`, {
    method: 'POST',
    headers: { 'x-csrf-token': csrfToken() },
    credentials: 'include',
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => null);
    throw new ApiError(
      problem ?? {
        type: 'about:blank',
        title: 'Export failed',
        status: response.status,
        detail: response.statusText,
      },
    );
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `noema-export-${new Date().toISOString().slice(0, 10)}.zip`;
  link.click();
  // Revoking immediately can cancel the download in some browsers; a tick is enough.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ── Streaming chat ───────────────────────────────────────────────────────────

export interface ChatCallbacks {
  onToken: (text: string) => void;
  onDone?: (usage: { prompt_tokens: number; completion_tokens: number }) => void;
  onError?: (message: string) => void;
}

/**
 * Consumes an SSE stream, dispatching each frame to the callbacks.
 *
 * Uses fetch rather than EventSource throughout because these requests are POSTs
 * with bodies that need the CSRF header — EventSource supports neither.
 */
async function consumeSse(response: Response, callbacks: ChatCallbacks): Promise<void> {
  if (!response.ok || !response.body) {
    const problem = await response.json().catch(() => null);
    throw new ApiError(
      problem ?? {
        type: 'about:blank',
        title: 'Stream failed',
        status: response.status,
        detail: response.statusText,
      },
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() ?? '';

    for (const frame of frames) {
      const lines = frame.split('\n');
      const eventLine = lines.find((l) => l.startsWith('event: '));
      const dataLine = lines.find((l) => l.startsWith('data: '));
      if (!eventLine || !dataLine) continue;

      const event = eventLine.slice(7).trim();
      const data = JSON.parse(dataLine.slice(6));

      if (event === 'token') callbacks.onToken(data.text as string);
      else if (event === 'done') callbacks.onDone?.(data);
      else if (event === 'error') callbacks.onError?.(data.message as string);
    }
  }
}

/**
 * Runs a selection action on a note. The result streams back and is never written
 * into the note — that is the endpoint's contract, not just this client's habit.
 */
export async function streamNoteAction(
  noteId: string,
  action: 'explain' | 'simplify' | 'expand',
  text: string,
  callbacks: ChatCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${BASE}/api/v1/notes/${noteId}/actions/${action}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-csrf-token': csrfToken() },
    credentials: 'include',
    body: JSON.stringify({ text }),
    signal,
  });
  await consumeSse(response, callbacks);
}

export async function streamChat(
  body: { notebook_id?: string; mode: TutorMode; messages: { role: 'user' | 'assistant'; content: string }[] },
  callbacks: ChatCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${BASE}/api/v1/ai/chat`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-csrf-token': csrfToken() },
    credentials: 'include',
    body: JSON.stringify(body),
    signal,
  });
  await consumeSse(response, callbacks);
}
