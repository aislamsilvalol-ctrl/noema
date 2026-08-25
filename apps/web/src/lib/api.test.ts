import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  api,
  ApiError,
  cardImageUrl,
  createImageCard,
  importAnki,
  streamChat,
  streamNoteAction,
  uploadSource,
} from '@/lib/api';

function jsonResponse(body: unknown, init: { status?: number } = {}): Response {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'content-type': 'application/json' },
  });
}

function sseResponse(...frames: string[]): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const frame of frames) controller.enqueue(encoder.encode(frame));
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
}

describe('ApiError', () => {
  it('uses the problem detail as its message', () => {
    const error = new ApiError({
      type: 'about:blank',
      title: 'Bad request',
      status: 400,
      detail: 'The title cannot be empty.',
    });

    expect(error.message).toBe('The title cannot be empty.');
  });

  it('falls back to the title when detail is empty', () => {
    const error = new ApiError({
      type: 'about:blank',
      title: 'Not found',
      status: 404,
      detail: '',
    });

    expect(error.message).toBe('Not found');
  });

  it('stringifies a non-string detail rather than showing "[object Object]"', () => {
    const error = new ApiError({
      type: 'about:blank',
      title: 'Validation failed',
      status: 422,
      // A proxy or gateway in front of the API can shape this differently than
      // NOEMA's own convention of a string detail.
      detail: { field: 'email', message: 'invalid' } as unknown as string,
    });

    expect(error.message).toContain('"field":"email"');
  });

  it('flags 401s as unauthorized and nothing else', () => {
    const unauthorized = new ApiError({
      type: 'about:blank',
      title: 'x',
      status: 401,
      detail: 'x',
    });
    const forbidden = new ApiError({
      type: 'about:blank',
      title: 'x',
      status: 403,
      detail: 'x',
    });

    expect(unauthorized.isUnauthorized).toBe(true);
    expect(forbidden.isUnauthorized).toBe(false);
  });
});

describe('request plumbing', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends no CSRF header on a GET', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: '1', email: 'a@b.com' }));

    await api.me();

    const [, init] = vi.mocked(fetch).mock.calls[0] ?? [];
    const headers = new Headers(init?.headers);
    expect(headers.has('x-csrf-token')).toBe(false);
  });

  it('sends the CSRF cookie value as a header on a mutation', async () => {
    vi.stubGlobal('document', { cookie: 'noema_csrf=secret-token; other=1' });
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: '1', title: 'Physics' }));

    await api.createWorkspace('Physics');

    const [, init] = vi.mocked(fetch).mock.calls[0] ?? [];
    const headers = new Headers(init?.headers);
    expect(headers.get('x-csrf-token')).toBe('secret-token');
    expect(JSON.parse(init?.body as string)).toEqual({ title: 'Physics' });
  });

  it('treats a 204 as success with no body', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }));

    await expect(api.deleteNotebook('nb-1')).resolves.toBeUndefined();
  });

  it('throws ApiError with the response problem on failure', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(
        { type: 'about:blank', title: 'Not found', status: 404, detail: 'Notebook not found' },
        { status: 404 },
      ),
    );

    await expect(api.notebook('missing')).rejects.toMatchObject({
      message: 'Notebook not found',
      problem: { status: 404 },
    });
  });

  it('falls back to status text when the failure body is not JSON', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response('<html>gateway down</html>', {
        status: 502,
        statusText: 'Bad Gateway',
      }),
    );

    await expect(api.notebook('x')).rejects.toMatchObject({
      problem: { status: 502, detail: 'Bad Gateway' },
    });
  });
});

describe('reviewBatch', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    vi.stubGlobal('document', { cookie: 'noema_csrf=secret-token' });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('posts the whole queue to /reviews/batch in one request', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse([
        { card_id: 'card-1', due_at: null, scheduled_days: 1, state: 'review', mastery: null },
      ]),
    );

    await api.reviewBatch([{ card_id: 'card-1', rating: 3, elapsed_ms: 900 }]);

    const [url, init] = vi.mocked(fetch).mock.calls[0] ?? [];
    expect(url).toContain('/api/v1/reviews/batch');
    expect(JSON.parse(init?.body as string)).toEqual([
      { card_id: 'card-1', rating: 3, elapsed_ms: 900 },
    ]);
    expect(new Headers(init?.headers).get('x-csrf-token')).toBe('secret-token');
  });
});

describe('createCard', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    vi.stubGlobal('document', { cookie: 'noema_csrf=secret-token' });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('defaults to a basic card', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: '1' }));

    await api.createCard('nb-1', 'Q', 'A');

    const [, init] = vi.mocked(fetch).mock.calls[0] ?? [];
    expect(JSON.parse(init?.body as string)).toMatchObject({ type: 'basic' });
  });

  it('sends type: reverse when asked to also make the mirror card', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: '1' }));

    await api.createCard('nb-1', 'Q', 'A', true);

    const [, init] = vi.mocked(fetch).mock.calls[0] ?? [];
    expect(JSON.parse(init?.body as string)).toMatchObject({ type: 'reverse' });
  });
});

describe('createCloze', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    vi.stubGlobal('document', { cookie: 'noema_csrf=secret-token' });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('posts the text as JSON and never sends the dead reverse field', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse([]));

    await api.createCloze('nb-1', 'The {{c1::mitochondria}} is the powerhouse.');

    const [url, init] = vi.mocked(fetch).mock.calls[0] ?? [];
    expect(url).toContain('/api/v1/cards/cloze');
    const body = JSON.parse(init?.body as string) as Record<string, unknown>;
    expect(body).toEqual({
      notebook_id: 'nb-1',
      text: 'The {{c1::mitochondria}} is the powerhouse.',
    });
    expect(body).not.toHaveProperty('reverse');
  });
});

describe('cardImageUrl', () => {
  it('points at the card image endpoint for direct use as an <img src>', () => {
    expect(cardImageUrl('card-1')).toContain('/api/v1/cards/card-1/image');
  });
});

describe('multipart uploads', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    vi.stubGlobal('document', { cookie: 'noema_csrf=secret-token' });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('uploads a source as multipart form data, not JSON', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: 'src-1', status: 'pending' }));
    const file = new File(['contents'], 'notes.pdf', { type: 'application/pdf' });

    await uploadSource('nb-1', file);

    const [url, init] = vi.mocked(fetch).mock.calls[0] ?? [];
    expect(url).toContain('/api/v1/sources');
    expect(init?.body).toBeInstanceOf(FormData);
    const body = init?.body as FormData;
    expect(body.get('notebook_id')).toBe('nb-1');
    expect(body.get('file')).toBe(file);
    expect(new Headers(init?.headers).get('x-csrf-token')).toBe('secret-token');
  });

  it('imports an Anki deck the same way', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ added: 3, unchanged: 0, scheduled: 3, skipped: {}, summary: '3 cards added.' }),
    );
    const file = new File(['pkg'], 'deck.apkg');

    const result = await importAnki('nb-1', file);

    expect(result.added).toBe(3);
    const [url] = vi.mocked(fetch).mock.calls[0] ?? [];
    expect(url).toContain('/api/v1/imports/anki');
  });

  it('creates an image card as multipart form data', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({
        id: 'card-1',
        notebook_id: 'nb-1',
        concept_id: null,
        type: 'image',
        front_md: 'What is this?',
        back_md: 'A diagram.',
        has_image: true,
        origin: 'user',
        approved_at: null,
        source_chunk_ids: [],
        created_at: '2024-01-01T00:00:00Z',
      }),
    );
    const image = new File(['bytes'], 'diagram.png', { type: 'image/png' });

    const card = await createImageCard('nb-1', 'What is this?', 'A diagram.', image);

    expect(card.has_image).toBe(true);
    const [url, init] = vi.mocked(fetch).mock.calls[0] ?? [];
    expect(url).toContain('/api/v1/cards/image');
    const body = init?.body as FormData;
    expect(body.get('notebook_id')).toBe('nb-1');
    expect(body.get('front_md')).toBe('What is this?');
    expect(body.get('back_md')).toBe('A diagram.');
    expect(body.get('image')).toBe(image);
  });
});

describe('SSE streaming', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    vi.stubGlobal('document', { cookie: '' });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('dispatches each token as it arrives', async () => {
    vi.mocked(fetch).mockResolvedValue(
      sseResponse(
        'event: token\ndata: {"text":"Hel"}\n\n',
        'event: token\ndata: {"text":"lo"}\n\n',
        'event: done\ndata: {"prompt_tokens":1,"completion_tokens":2}\n\n',
      ),
    );

    const tokens: string[] = [];
    let done: unknown;
    await streamChat({ mode: 'explain', messages: [] }, {
      onToken: (text) => tokens.push(text),
      onDone: (usage) => {
        done = usage;
      },
    });

    expect(tokens).toEqual(['Hel', 'lo']);
    expect(done).toEqual({ prompt_tokens: 1, completion_tokens: 2 });
  });

  it('reassembles a frame split across chunk boundaries', async () => {
    // The reader can hand back partial frames — SSE framing is `\n\n`-delimited,
    // not chunk-delimited, and there is no guarantee those line up.
    vi.mocked(fetch).mockResolvedValue(
      sseResponse('event: tok', 'en\ndata: {"text":"whole"}\n\n'),
    );

    const tokens: string[] = [];
    await streamNoteAction('note-1', 'explain', 'text', { onToken: (t) => tokens.push(t) });

    expect(tokens).toEqual(['whole']);
  });

  it('reports a stream error event without throwing', async () => {
    vi.mocked(fetch).mockResolvedValue(
      sseResponse('event: error\ndata: {"message":"budget exceeded"}\n\n'),
    );

    const errors: string[] = [];
    await streamChat({ mode: 'explain', messages: [] }, {
      onToken: () => {},
      onError: (message) => errors.push(message),
    });

    expect(errors).toEqual(['budget exceeded']);
  });

  it('throws ApiError when the stream never starts', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(
        { type: 'about:blank', title: 'Unavailable', status: 503, detail: 'No provider configured' },
        { status: 503 },
      ),
    );

    await expect(
      streamChat({ mode: 'explain', messages: [] }, { onToken: () => {} }),
    ).rejects.toMatchObject({ message: 'No provider configured' });
  });
});
