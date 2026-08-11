/**
 * Typed client for the NOEMA API.
 *
 * Cookies carry the session, so every request sends credentials and every mutation
 * echoes the CSRF token the server set at login. In Phase 1 the response types below
 * are hand-written; issue #14 replaces them with types generated from `/openapi.json`
 * so a backend change fails the web typecheck instead of failing at runtime.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const CSRF_COOKIE = 'noema_csrf';

export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance?: string;
  errors?: { field: string; message: string }[];
}

export class ApiError extends Error {
  constructor(readonly problem: ProblemDetail) {
    super(problem.detail || problem.title);
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
};

// ── Streaming chat ───────────────────────────────────────────────────────────

export interface ChatCallbacks {
  onToken: (text: string) => void;
  onDone?: (usage: { prompt_tokens: number; completion_tokens: number }) => void;
  onError?: (message: string) => void;
}

/**
 * Consumes the SSE stream from `POST /ai/chat`.
 *
 * Uses fetch rather than EventSource because the request is a POST with a body and
 * needs the CSRF header — EventSource supports neither.
 */
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

  if (!response.ok || !response.body) {
    const problem = await response.json().catch(() => null);
    throw new ApiError(
      problem ?? {
        type: 'about:blank',
        title: 'Chat failed',
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
      const eventLine = frame.split('\n').find((l) => l.startsWith('event: '));
      const dataLine = frame.split('\n').find((l) => l.startsWith('data: '));
      if (!eventLine || !dataLine) continue;

      const event = eventLine.slice(7).trim();
      const data = JSON.parse(dataLine.slice(6));

      if (event === 'token') callbacks.onToken(data.text as string);
      else if (event === 'done') callbacks.onDone?.(data);
      else if (event === 'error') callbacks.onError?.(data.message as string);
    }
  }
}
