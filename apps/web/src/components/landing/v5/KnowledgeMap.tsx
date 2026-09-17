/**
 * The knowledge map, as terrain.
 *
 * One learner's territory in Freud, drawn by hand: contour lines for the
 * ground, concepts as places, prerequisites as paths between them. Each
 * place carries a state — mastered, understood, learning, needs review, not
 * yet — in the brand's terrain language (docs/brand-os.md §10), never a
 * traffic light. The drawing is an illustration and the section says so;
 * the product draws the real one from the learner's concept states.
 */

import type { Locale } from '@/lib/i18n';

export type MapState = 'mastered' | 'understood' | 'learning' | 'review' | 'unknown';

interface Place {
  id: string;
  x: number;
  y: number;
  state: MapState;
  /** The next place the path leads to. */
  next?: boolean;
}

const PLACES: Place[] = [
  { id: 'unconscious', x: 150, y: 250, state: 'mastered' },
  { id: 'slip', x: 250, y: 150, state: 'mastered' },
  { id: 'repression', x: 330, y: 260, state: 'understood' },
  { id: 'preconscious', x: 120, y: 120, state: 'review' },
  { id: 'resistance', x: 430, y: 170, state: 'learning' },
  { id: 'agencies', x: 470, y: 300, state: 'learning', next: true },
  { id: 'dreams', x: 560, y: 120, state: 'unknown' },
  { id: 'desire', x: 600, y: 250, state: 'unknown' },
  { id: 'transference', x: 540, y: 370, state: 'unknown' },
];

const PATHS: [string, string][] = [
  ['preconscious', 'unconscious'],
  ['unconscious', 'slip'],
  ['unconscious', 'repression'],
  ['slip', 'resistance'],
  ['repression', 'resistance'],
  ['repression', 'agencies'],
  ['resistance', 'dreams'],
  ['agencies', 'desire'],
  ['agencies', 'transference'],
  ['dreams', 'desire'],
];

const NAMES: Record<Locale, Record<string, string>> = {
  pt: {
    unconscious: 'Inconsciente',
    slip: 'O lapso',
    repression: 'Recalque',
    preconscious: 'Pré-consciente',
    resistance: 'Resistência',
    agencies: 'Id, ego, superego',
    dreams: 'Sonhos',
    desire: 'Desejo',
    transference: 'Transferência',
  },
  en: {
    unconscious: 'The unconscious',
    slip: 'The slip',
    repression: 'Repression',
    preconscious: 'Preconscious',
    resistance: 'Resistance',
    agencies: 'Id, ego, superego',
    dreams: 'Dreams',
    desire: 'Desire',
    transference: 'Transference',
  },
  es: {
    unconscious: 'Inconsciente',
    slip: 'El lapsus',
    repression: 'Represión',
    preconscious: 'Preconsciente',
    resistance: 'Resistencia',
    agencies: 'Ello, yo, superyó',
    dreams: 'Sueños',
    desire: 'Deseo',
    transference: 'Transferencia',
  },
};

// Contours: a few closed curves around the mastered ground, drawn once.
const CONTOURS = [
  'M60,230 C80,150 180,110 260,120 C340,130 380,200 350,270 C320,340 200,360 130,330 C80,310 50,290 60,230 Z',
  'M20,250 C40,130 200,70 300,90 C420,110 470,220 420,320 C370,410 190,420 100,370 C40,340 10,310 20,250 Z',
  'M380,60 C470,40 620,80 640,180 C660,280 600,400 480,400 C400,400 360,330 380,250 C400,180 350,100 380,60 Z',
];

const STATE_LABEL_KEYS: MapState[] = ['mastered', 'understood', 'learning', 'review', 'unknown'];

function Place({ place, name, now }: { place: Place; name: string; now: string }) {
  const { x, y, state } = place;
  const r = state === 'mastered' ? 11 : state === 'understood' ? 9 : 8;
  return (
    <g transform={`translate(${x} ${y})`}>
      {state === 'review' && (
        <circle r={r + 6} fill="none" stroke="currentColor" strokeWidth={1.25} strokeDasharray="3 3" />
      )}
      {state === 'mastered' && <circle r={r} fill="currentColor" />}
      {state === 'understood' && <circle r={r} fill="currentColor" opacity={0.78} />}
      {state === 'learning' && (
        <>
          <circle r={r} fill="url(#hatch)" />
          <circle r={r} fill="none" stroke="currentColor" strokeWidth={1.25} />
        </>
      )}
      {state === 'review' && <circle r={r} fill="currentColor" opacity={0.78} />}
      {state === 'unknown' && (
        <circle r={r} fill="none" stroke="currentColor" strokeWidth={1.25} strokeDasharray="1.5 3" />
      )}
      {place.next && (
        <>
          <circle r={r + 12} fill="none" stroke="var(--accent-on)" strokeWidth={1.5} />
          <text
            y={r + 30}
            textAnchor="middle"
            fill="var(--accent-on)"
            style={{ font: '600 11px var(--font-mono)' }}
          >
            {now}
          </text>
        </>
      )}
      <text
        y={-r - 8}
        textAnchor="middle"
        fill="currentColor"
        opacity={state === 'unknown' ? 0.6 : 1}
        style={{ font: `${state === 'mastered' ? 500 : 400} 13px var(--font-ui)` }}
      >
        {name}
      </text>
    </g>
  );
}

export function KnowledgeMap({
  locale,
  labels,
  now,
  className = '',
}: {
  locale: Locale;
  labels: Record<MapState, string>;
  /** The word under the next place ("now"). */
  now: string;
  className?: string;
}) {
  const names = NAMES[locale];
  const at = (id: string) => PLACES.find((p) => p.id === id)!;
  return (
    <figure className={className}>
      <svg
        viewBox="0 0 660 420"
        role="img"
        aria-label={PLACES.map((p) => `${names[p.id] ?? p.id}: ${labels[p.state]}`).join(', ')}
        className="h-auto w-full"
      >
        <defs>
          <pattern id="hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="5" stroke="currentColor" strokeWidth="1.4" />
          </pattern>
        </defs>
        <g className="map-contour" fill="none" stroke="currentColor" strokeOpacity={0.16} strokeWidth={1}>
          {CONTOURS.map((d) => (
            <path key={d} d={d} />
          ))}
        </g>
        <g stroke="currentColor" strokeOpacity={0.35} strokeWidth={1}>
          {PATHS.map(([a, b]) => {
            const from = at(a);
            const to = at(b);
            const dashed = from.state === 'unknown' || to.state === 'unknown';
            return (
              <line
                key={`${a}-${b}`}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                strokeDasharray={dashed ? '2 4' : undefined}
              />
            );
          })}
        </g>
        {PLACES.map((place) => (
          <Place key={place.id} place={place} name={names[place.id] ?? place.id} now={now} />
        ))}
      </svg>
      <figcaption className="mt-4 flex flex-wrap gap-x-5 gap-y-2 font-mono text-xs fg-muted">
        {STATE_LABEL_KEYS.map((state) => (
          <span key={state} className="inline-flex items-center gap-2">
            <svg viewBox="0 0 20 20" className="h-4 w-4" aria-hidden="true">
              {state === 'mastered' && <circle cx="10" cy="10" r="6" fill="currentColor" />}
              {state === 'understood' && <circle cx="10" cy="10" r="6" fill="currentColor" opacity={0.78} />}
              {state === 'learning' && (
                <>
                  <circle cx="10" cy="10" r="6" fill="url(#hatch)" />
                  <circle cx="10" cy="10" r="6" fill="none" stroke="currentColor" />
                </>
              )}
              {state === 'review' && (
                <>
                  <circle cx="10" cy="10" r="5" fill="currentColor" opacity={0.78} />
                  <circle cx="10" cy="10" r="8.5" fill="none" stroke="currentColor" strokeDasharray="2 2" />
                </>
              )}
              {state === 'unknown' && (
                <circle cx="10" cy="10" r="6" fill="none" stroke="currentColor" strokeDasharray="1.5 2.5" />
              )}
            </svg>
            {labels[state]}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
