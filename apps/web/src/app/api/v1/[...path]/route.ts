/**
 * Demo data, for a deployment with no backend behind it.
 *
 * NOEMA needs Postgres, Redis and a worker to run. That is fine for someone
 * self-hosting it and useless for someone who just wants to see what the thing
 * looks like — the interface was, until this existed, invisible unless you ran
 * Docker. This serves the same shapes the real API serves so the actual screens
 * can be looked at.
 *
 * Inert unless `NOEMA_DEMO=1`. Without that it 404s, so a real deployment that
 * points the client at its own origin by mistake gets an obvious failure instead
 * of quietly showing fabricated study data as if it were the user's own.
 */

import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const DEMO = process.env.NOEMA_DEMO === '1';

const WS = '00000000-0000-4000-8000-000000000001';
const SUBJECTS = [
  { id: 'aaaaaaaa-0000-4000-8000-000000000001', title: 'Fisiologia' },
  { id: 'aaaaaaaa-0000-4000-8000-000000000002', title: 'Farmacologia' },
  { id: 'aaaaaaaa-0000-4000-8000-000000000003', title: 'Bioquímica' },
];

const NOTEBOOKS = [
  ['bbbbbbbb-0000-4000-8000-000000000001', 0, 'Sistema cardiovascular', 'Ciclo cardíaco, débito, pressão arterial'],
  ['bbbbbbbb-0000-4000-8000-000000000002', 0, 'Sistema respiratório', 'Ventilação, difusão, transporte de gases'],
  ['bbbbbbbb-0000-4000-8000-000000000003', 1, 'Farmacocinética', 'Absorção, distribuição, metabolismo, excreção'],
  ['bbbbbbbb-0000-4000-8000-000000000004', 1, 'Antibióticos', 'Betalactâmicos, macrolídeos, resistência'],
  ['bbbbbbbb-0000-4000-8000-000000000005', 2, 'Metabolismo energético', 'Glicólise, ciclo de Krebs, cadeia respiratória'],
] as const;

const NOTE_MD = `## Ciclo cardíaco

O ciclo tem duas fases: **sístole** (contração) e **diástole** (relaxamento).
Em repouso a diástole ocupa cerca de dois terços do ciclo — é nela que os
ventrículos se enchem e que as coronárias são perfundidas.

> Consequência prática: taquicardia encurta a diástole antes da sístole, então
> reduz o enchimento *e* a perfusão coronariana ao mesmo tempo.

### Débito cardíaco

\`DC = volume sistólico × frequência cardíaca\`

Três determinantes do volume sistólico:

1. **Pré-carga** — volume ao final da diástole (Frank-Starling)
2. **Pós-carga** — resistência que o ventrículo precisa vencer
3. **Contratilidade** — força independente de pré e pós-carga

Ver [[Lei de Frank-Starling]] e [[Resistência vascular periférica]].`;

const NOTES = [
  ['cccccccc-0000-4000-8000-000000000001', 'Ciclo cardíaco e débito', NOTE_MD],
  ['cccccccc-0000-4000-8000-000000000002', 'Regulação da pressão arterial', 'Barorreceptores respondem em segundos; o sistema renina-angiotensina-aldosterona em horas.'],
  ['cccccccc-0000-4000-8000-000000000003', 'Eletrofisiologia — potencial de ação', 'Fase 0 (sódio), fase 2 (platô de cálcio), fase 3 (potássio), fase 4 (repouso).'],
] as const;

const CARDS = [
  ['Quais são os três determinantes do volume sistólico?', 'Pré-carga, pós-carga e contratilidade.', 'review', 14],
  ['O que a taquicardia encurta primeiro, sístole ou diástole?', 'A diástole — reduz enchimento ventricular e perfusão coronariana ao mesmo tempo.', 'review', 9],
  ['Defina pré-carga.', 'Volume ao final da diástole: o estiramento das fibras antes da contração (Frank-Starling).', 'learning', 2],
  ['Meia-vida de eliminação de primeira ordem — o que é constante?', 'A fração eliminada por unidade de tempo, não a quantidade. Por isso a meia-vida independe da dose.', 'new', 0],
  ['Por que betalactâmicos não agem em micoplasma?', 'Micoplasma não tem parede celular, que é exatamente o alvo dos betalactâmicos.', 'review', 21],
] as const;

const ago = (days: number) => new Date(Date.now() - days * 86_400_000).toISOString();

const PAYLOADS: Record<string, unknown> = {
  meta: {
    mode: 'demo',
    local: false,
    allow_signups: false,
    default_provider: 'anthropic',
    embedding_model: 'text-embedding-3-small',
    version: '0.1.0',
  },
  'auth/me': {
    id: '00000000-0000-4000-8000-0000000000ff',
    email: 'ana@example.com',
    display_name: 'Ana',
    settings: {},
    created_at: ago(64),
  },
  workspaces: {
    items: [{ id: WS, title: 'Medicina', slug: 'medicina', position: 0, created_at: ago(64) }],
    next_cursor: null,
  },
  subjects: {
    items: SUBJECTS.map((s, i) => ({
      ...s,
      workspace_id: WS,
      slug: s.title.toLowerCase(),
      position: i,
      created_at: ago(60),
    })),
    next_cursor: null,
  },
  notebooks: {
    items: NOTEBOOKS.map(([id, subject, title, description]) => ({
      id,
      subject_id: SUBJECTS[subject]?.id ?? SUBJECTS[0]!.id,
      title,
      slug: title.toLowerCase().replace(/\s+/g, '-'),
      description,
      ai_provider_override: null,
      retrieval_settings: {},
      created_at: ago(40),
      updated_at: ago(1),
    })),
    next_cursor: null,
  },
  notes: {
    items: NOTES.map(([id, title, content_md], i) => ({
      id,
      notebook_id: NOTEBOOKS[0][0],
      title,
      content_md,
      links: ['Lei de Frank-Starling'],
      created_at: ago(20),
      updated_at: ago(i),
    })),
    next_cursor: null,
  },
  cards: CARDS.map(([front_md, back_md, state, reps], i) => ({
    id: `dddddddd-0000-4000-8000-00000000000${i}`,
    notebook_id: NOTEBOOKS[0][0],
    concept_id: null,
    type: 'basic',
    front_md,
    back_md,
    origin: i % 2 ? 'user' : 'ai',
    approved_at: ago(10),
    created_at: ago(10),
    due_at: ago(0.1),
    state,
    reps,
    preview: { again: 0.02, hard: 3.4, good: 8.6, easy: 21.0 },
  })),
  'learning-session/plan': {
    rationale:
      'Você errou pré-carga e pós-carga nas últimas duas revisões, então a sessão começa ' +
      'reparando essa confusão antes de avançar. O resto é a fila do dia, intercalada para ' +
      'você não responder no piloto automático.',
    estimated_minutes: 30,
    blocks: [
      {
        kind: 'warmup',
        why: 'Duas cartas que você acertou com folga, para entrar no ritmo.',
        minutes: 3,
        items: [
          { ref_id: '1', kind: 'card', concept_id: null, concept_name: 'Débito cardíaco', estimated_seconds: 40 },
          { ref_id: '2', kind: 'card', concept_id: null, concept_name: 'Sístole e diástole', estimated_seconds: 45 },
        ],
      },
      {
        kind: 'repair',
        why: 'Você trocou pré-carga por pós-carga duas vezes seguidas. Isso vem antes de qualquer coisa nova.',
        minutes: 8,
        items: [
          { ref_id: '3', kind: 'question', concept_id: null, concept_name: 'Pré-carga', estimated_seconds: 120 },
          { ref_id: '4', kind: 'question', concept_id: null, concept_name: 'Pós-carga', estimated_seconds: 120 },
          { ref_id: '5', kind: 'card', concept_id: null, concept_name: 'Frank-Starling', estimated_seconds: 60 },
        ],
      },
      {
        kind: 'practice',
        why: 'Fila do dia. Farmacocinética entra intercalada com cardiovascular de propósito.',
        minutes: 12,
        items: [
          { ref_id: '6', kind: 'card', concept_id: null, concept_name: 'Meia-vida de eliminação', estimated_seconds: 50 },
          { ref_id: '7', kind: 'card', concept_id: null, concept_name: 'Resistência vascular', estimated_seconds: 55 },
          { ref_id: '8', kind: 'question', concept_id: null, concept_name: 'Clearance renal', estimated_seconds: 150 },
        ],
      },
      {
        kind: 'cooldown',
        why: 'Uma carta madura para fechar com um acerto.',
        minutes: 2,
        items: [
          { ref_id: '9', kind: 'card', concept_id: null, concept_name: 'Betalactâmicos', estimated_seconds: 40 },
        ],
      },
    ],
  },
  mastery: [
    ['Ciclo cardíaco', 84], ['Débito cardíaco', 78], ['Frank-Starling', 71],
    ['Pré-carga', 46], ['Pós-carga', 41], ['Farmacocinética', 62], ['Clearance renal', 33],
  ].map(([concept_name, mastery], i) => ({
    concept_id: `eeeeeeee-0000-4000-8000-00000000000${i}`,
    concept_name,
    mastery,
    provisional: (mastery as number) < 50,
    components: { correctness: (mastery as number) / 100, retention: 0.82, recency_days: 3 },
    last_evidence_at: ago(2),
  })),
  'ai/providers': [
    { name: 'anthropic', configured: true, capabilities: {}, is_default: true },
    { name: 'openai', configured: true, capabilities: {}, is_default: false },
    { name: 'gemini', configured: false, capabilities: {}, is_default: false },
    { name: 'ollama', configured: true, capabilities: {}, is_default: false },
  ],
  'ai/credentials': [
    {
      id: 'ffffffff-0000-4000-8000-000000000001',
      provider: 'anthropic',
      label: 'default',
      last4: '7Kd2',
      created_at: ago(30),
      last_used_at: ago(0.2),
      last_verified_at: ago(30),
      verification_error: null,
    },
  ],
};

const TUTOR_REPLY =
  'A diástole. Em repouso ela ocupa cerca de dois terços do ciclo, então é ela que ' +
  'encurta primeiro quando a frequência sobe — e como as coronárias são perfundidas ' +
  'justamente na diástole, o coração perde enchimento e irrigação ao mesmo tempo. ' +
  'É por isso que taquicardia é mal tolerada em quem já tem doença coronariana.';

function stream(): Response {
  const encoder = new TextEncoder();
  const words = TUTOR_REPLY.split(' ');

  return new Response(
    new ReadableStream({
      async start(controller) {
        for (const word of words) {
          controller.enqueue(
            encoder.encode(`event: token\ndata: ${JSON.stringify({ text: `${word} ` })}\n\n`),
          );
          // Paced, because a reply that lands instantly is not what the real one
          // looks like and the point of a preview is to look like the thing.
          await new Promise((r) => setTimeout(r, 28));
        }
        controller.enqueue(
          encoder.encode(
            `event: done\ndata: ${JSON.stringify({ prompt_tokens: 812, completion_tokens: 74 })}\n\n`,
          ),
        );
        controller.close();
      },
    }),
    { headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-store' } },
  );
}

function resolve(path: string[]): unknown {
  const key = path.join('/');
  if (key in PAYLOADS) return PAYLOADS[key];

  // `/notebooks/{id}` and `/notes/{id}` — one item out of the list above.
  if (path[0] === 'notebooks' && path.length === 2) {
    const list = (PAYLOADS.notebooks as { items: { id: string }[] }).items;
    return list.find((n) => n.id === path[1]) ?? list[0];
  }
  if (path[0] === 'notes' && path.length === 2) {
    const list = (PAYLOADS.notes as { items: { id: string }[] }).items;
    return list.find((n) => n.id === path[1]) ?? list[0];
  }
  if (path[0] === 'reviews' && path[1] === 'forecast') {
    return [12, 8, 19, 4, 22, 15, 7, 11, 26, 9, 14, 6, 18, 21].map((due, i) => ({
      date: new Date(Date.now() + i * 86_400_000).toISOString().slice(0, 10),
      due,
    }));
  }
  return null;
}

function guard(): Response | null {
  return DEMO
    ? null
    : NextResponse.json(
        {
          type: 'https://noema.dev/errors/not-found',
          title: 'Not found',
          status: 404,
          detail: 'This deployment has no demo data and no API behind it.',
        },
        { status: 404 },
      );
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const blocked = guard();
  if (blocked) return blocked;

  const { path } = await params;
  const body = resolve(path);
  return body === null
    ? NextResponse.json({ items: [], next_cursor: null })
    : NextResponse.json(body);
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const blocked = guard();
  if (blocked) return blocked;

  const { path } = await params;
  const key = path.join('/');

  if (key === 'ai/chat') return stream();

  if (key === 'reviews') {
    // The scheduler's answer, so the review screen advances and shows a real
    // next-due date rather than an error.
    return NextResponse.json({
      card_id: 'dddddddd-0000-4000-8000-000000000000',
      due_at: ago(-8.6),
      scheduled_days: 8.6,
      state: 'review',
      mastery: 79,
    });
  }

  return NextResponse.json(
    {
      type: 'https://noema.dev/errors/forbidden',
      title: 'Read-only preview',
      status: 403,
      detail: 'This is a demo deployment. Nothing you do here is saved.',
    },
    { status: 403 },
  );
}

export async function PATCH(): Promise<Response> {
  return (
    guard() ??
    NextResponse.json(
      {
        type: 'https://noema.dev/errors/forbidden',
        title: 'Read-only preview',
        status: 403,
        detail: 'This is a demo deployment. Nothing you do here is saved.',
      },
      { status: 403 },
    )
  );
}

export async function DELETE(): Promise<Response> {
  return (
    guard() ??
    NextResponse.json(
      {
        type: 'https://noema.dev/errors/forbidden',
        title: 'Read-only preview',
        status: 403,
        detail: 'This is a demo deployment. Nothing you do here is saved.',
      },
      { status: 403 },
    )
  );
}
