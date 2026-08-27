/**
 * Typed client for the NOEMA API.
 *
 * Cookies carry the session, so every request sends credentials and every mutation
 * echoes the CSRF token the server set at login. In Phase 1 the response types below
 * are hand-written; issue #14 replaces them with types generated from `/openapi.json`
 * so a backend change fails the web typecheck instead of failing at runtime.
 */

import type { components } from '@/lib/api-schema';

/**
 * The types below are aliases of the generated schema rather than copies of it.
 *
 * They used to be hand-written, and hand-written types drift: the API renames a
 * field, the frontend keeps compiling against the old name, and the mismatch
 * surfaces as `undefined` on a screen weeks later. A change to the API surface is
 * now a type error here, at the moment it happens.
 *
 * Regenerate with `npm run api:types`; CI fails if either file is stale.
 */
type Schemas = components['schemas'];

/**
 * Where the API is, from the browser's point of view.
 *
 * Same origin in a deployed build: either the demo route handlers, or the real
 * API proxied through `next.config.mjs`. Both keep session cookies first-party,
 * which `SameSite=Lax` requires.
 *
 * `http://localhost:8000` only in development, where the API runs beside this in
 * compose. An explicit NEXT_PUBLIC_API_URL still wins over both.
 */
const BASE =
  process.env.NEXT_PUBLIC_API_URL ??
  (process.env.NEXT_PUBLIC_DEMO === '1' || process.env.NODE_ENV === 'production'
    ? ''
    : 'http://localhost:8000');
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

export type User = Schemas['UserOut'];

export type Workspace = Schemas['WorkspaceOut'];

export type Subject = Schemas['SubjectOut'];

export type Notebook = Schemas['NotebookOut'];

export type Note = Schemas['NoteOut'];

export type Provider = Schemas['ProviderOut'];

export type Credential = Schemas['CredentialOut'];

interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export type CardType = 'basic' | 'reverse' | 'cloze' | 'image' | 'concept' | 'definition' | 'code';

export type Card = Schemas['CardOut'];

export type IntervalPreview = Schemas['IntervalPreview'];

export interface DueCard extends Card {
  due_at: string | null;
  state: 'new' | 'learning' | 'review' | 'relearning';
  reps: number;
  preview: IntervalPreview;
}

export type ReviewResult = Schemas['ReviewOut'];

export type Mastery = Schemas['MasteryOut'];

export type PlanItem = Schemas['PlanItem'];

export type PlanBlock = Schemas['PlanBlockOut'];

export type SessionPlan = Schemas['PlanOut'];

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
  // `reverse: true` also creates a second card with front/back swapped, its own
  // schedule — recognising the pair one direction says nothing about the other.
  // The response is only the first card; the caller reloads the list to see both.
  createCard: (
    notebookId: string,
    front: string,
    back: string,
    reverse = false,
    conceptId?: string,
  ) =>
    request<Card>('/cards', {
      method: 'POST',
      body: JSON.stringify({
        notebook_id: notebookId,
        front_md: front,
        back_md: back,
        type: reverse ? 'reverse' : 'basic',
        concept_id: conceptId ?? null,
      }),
    }),
  // One card per {{c1::...}} deletion in `text`. `reverse` is deliberately not
  // sent — the backend field exists but create_cloze() never reads it (see
  // issue #73); sending it would promise a mirror card that never appears.
  createCloze: (notebookId: string, text: string, conceptId?: string) =>
    request<Card[]>('/cards/cloze', {
      method: 'POST',
      body: JSON.stringify({
        notebook_id: notebookId,
        text,
        concept_id: conceptId ?? null,
      }),
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
  // Applied in order server-side — each review's interval depends on the state
  // the previous one in the batch left behind. Used to flush reviews taken
  // offline; see src/lib/offlineQueue.ts.
  reviewBatch: (reviews: Schemas['ReviewIn'][]) =>
    request<ReviewResult[]>('/reviews/batch', {
      method: 'POST',
      body: JSON.stringify(reviews),
    }),

  mastery: (weak = false) => request<Mastery[]>(`/mastery?weak=${weak}`),
  concepts: (limit = 200) => request<Concept[]>(`/concepts?limit=${limit}`),
  conceptGraph: (id: string, depth = 2) =>
    request<{ nodes: Concept[]; edges: ConceptEdge[] }>(
      `/concepts/${id}/graph?depth=${depth}`,
    ),

  goals: () => request<Goal[]>('/goals'),
  createGoal: (
    notebookId: string,
    title: string,
    dueOn: string,
    minutesPerDay: number,
  ) =>
    request<Goal>('/goals', {
      method: 'POST',
      body: JSON.stringify({
        notebook_id: notebookId,
        title,
        due_on: dueOn,
        minutes_per_day: minutesPerDay,
      }),
    }),
  deleteGoal: (id: string) => request<void>(`/goals/${id}`, { method: 'DELETE' }),

  drills: (mistakeId: string) =>
    request<{ belief: string; questions: Question[] }>(
      `/mistakes/${mistakeId}/drills`,
      { method: 'POST' },
    ),

  socratic: (
    conceptId: string,
    transcript: { role: 'tutor' | 'learner'; content: string }[],
  ) =>
    request<SocraticTurn>('/socratic', {
      method: 'POST',
      body: JSON.stringify({ concept_id: conceptId, transcript }),
    }),

  explain: (conceptId: string, text: string) =>
    request<Explanation>('/explanations', {
      method: 'POST',
      body: JSON.stringify({ concept_id: conceptId, text }),
    }),

  startExam: (notebookId: string, questions: number, minutes: number) =>
    request<Exam>('/exams', {
      method: 'POST',
      body: JSON.stringify({ notebook_id: notebookId, questions, minutes }),
    }),
  exam: (id: string) => request<Exam>(`/exams/${id}`),
  submitExam: (id: string, answers: Record<string, Record<string, unknown>>) =>
    request<Exam>(`/exams/${id}/submit`, {
      method: 'POST',
      body: JSON.stringify({ answers }),
    }),

  forecast: (days = 30) => request<ForecastDay[]>(`/reviews/forecast?days=${days}`),
  calibration: () => request<Calibration>('/analytics/calibration'),
  fitSchedule: () =>
    request<{
      adopted: boolean;
      baseline_loss: number;
      candidate_loss: number;
      train_attempts: number;
      validation_attempts: number;
      summary: string;
    }>('/analytics/fit-schedule', { method: 'POST' }),

  plan: (minutes: number) =>
    request<SessionPlan>(`/learning-session/plan?minutes=${minutes}`),

  deleteAccount: () => request<Deletion>('/me', { method: 'DELETE' }),

  meta: () => request<Meta>('/meta'),

  question: (id: string) => request<Question>(`/questions/${id}`),
  questions: (notebookId: string, limit = 20) =>
    request<Question[]>(`/questions?notebook_id=${notebookId}&limit=${limit}`),
  generateQuestions: (notebookId: string, limit = 8) =>
    request<Question[]>('/questions/generate', {
      method: 'POST',
      body: JSON.stringify({ notebook_id: notebookId, limit }),
    }),
  answer: (
    questionId: string,
    response: Record<string, unknown>,
    confidence?: number,
    elapsedMs = 0,
  ) =>
    request<Answer>('/answers', {
      method: 'POST',
      body: JSON.stringify({
        question_id: questionId,
        response,
        confidence,
        elapsed_ms: elapsedMs,
      }),
    }),

  mistakes: (unresolved = true, misconceptionsOnly = false) =>
    request<Mistake[]>(
      `/mistakes?unresolved=${unresolved}&misconceptions_only=${misconceptionsOnly}`,
    ),

  sources: (notebookId: string) =>
    request<Source[]>(`/sources?notebook_id=${notebookId}`),
  source: (id: string) => request<Source>(`/sources/${id}`),
  ingest: (id: string) => request<Source>(`/sources/${id}/ingest`, { method: 'POST' }),
  deleteSource: (id: string) => request<void>(`/sources/${id}`, { method: 'DELETE' }),
};

export type SourceStatus =
  | 'pending'
  | 'parsing'
  | 'chunking'
  | 'embedding'
  | 'extracting'
  | 'ready'
  | 'failed';

export type Source = Schemas['SourceOut'];

export type QuestionType =
  | 'mcq'
  | 'true_false'
  | 'open'
  | 'fill_blank'
  | 'matching'
  | 'ordering'
  | 'code';

export type Question = Schemas['QuestionOut'];

export type Answer = Schemas['AnswerOut'];

export type Mistake = Schemas['MistakeOut'];

export type Explanation = Schemas['ExplanationOut'];

export type Concept = Schemas['ConceptOut'];

export type ConceptEdge = Schemas['EdgeOut'];

export type Milestone = Schemas['MilestoneOut'];

export type Goal = Schemas['GoalOut'];

export type SocraticTurn = Schemas['SocraticOut'];

export interface ExamConceptResult {
  concept_id: string | null;
  name: string;
  correct: number;
  total: number;
  score: number;
}

export type Exam = Schemas['ExamOut'];

export type ForecastDay = Schemas['ForecastDay'];

export type Calibration = Schemas['CalibrationOut'];

export type Meta = Schemas['MetaOut'];

export type Deletion = Schemas['DeletionOut'];

export type AnkiImport = Schemas['ImportOut'];

/**
 * Uploads one file.
 *
 * Not part of `api` because the body is multipart: `request` sets a JSON content
 * type, and letting it do that here would make the browser send the wrong
 * boundary — the server would reject a file that is perfectly fine.
 */
async function postFile<T>(path: string, body: FormData, failure: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'x-csrf-token': csrfToken() },
    credentials: 'include',
    body,
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      payload ?? {
        type: 'about:blank',
        title: failure,
        status: response.status,
        detail: response.statusText,
      },
    );
  }
  return payload as T;
}

export async function uploadSource(notebookId: string, file: File): Promise<Source> {
  const body = new FormData();
  body.append('notebook_id', notebookId);
  body.append('file', file);
  return postFile<Source>('/api/v1/sources', body, 'Upload failed');
}

/**
 * Imports an Anki deck into a notebook.
 *
 * Multipart for the same reason as the upload above, and separate from `api` for
 * the same reason too.
 */
export async function importAnki(notebookId: string, file: File): Promise<AnkiImport> {
  const body = new FormData();
  body.append('notebook_id', notebookId);
  body.append('file', file);
  return postFile<AnkiImport>('/api/v1/imports/anki', body, 'Import failed');
}

/**
 * Creates a card whose question is illustrated by an image — multipart for the
 * same reason as the upload above, and separate from `api` for the same reason.
 */
export async function createImageCard(
  notebookId: string,
  frontMd: string,
  backMd: string,
  image: File,
  conceptId?: string,
): Promise<Card> {
  const body = new FormData();
  body.append('notebook_id', notebookId);
  body.append('front_md', frontMd);
  body.append('back_md', backMd);
  body.append('image', image);
  if (conceptId) body.append('concept_id', conceptId);
  return postFile<Card>('/api/v1/cards/image', body, 'Could not create that card.');
}

/**
 * The URL of a card's front image, for direct use as an `<img src>`.
 *
 * Not part of `api` because the response is binary, not JSON — a plain `<img>`
 * tag fetches it itself and sends the session cookie automatically, since the
 * request is same-origin (see BASE above); there is nothing for `request` to do.
 */
export function cardImageUrl(cardId: string): string {
  return `${BASE}/api/v1/cards/${cardId}/image`;
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
