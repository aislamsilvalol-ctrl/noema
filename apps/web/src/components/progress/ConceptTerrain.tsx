'use client';

/**
 * One journey's concepts, drawn as terrain.
 *
 * The landing shows an illustration of this (landing/v4/KnowledgeMap); this is
 * the real one, drawn from the learner's concept states. Same grammar
 * (docs/brand-os.md §10): places on ground, contour lines, a path between
 * them, an orange ring where the learner is now. Never a traffic light.
 *
 * The layout is deterministic on purpose: modules are regions left to right in
 * curriculum order, concepts sit on a gentle curve inside their region, and
 * the path follows the curriculum because the journey carries no
 * prerequisite edges. A map that rearranged itself between visits would not
 * be a map — the learner should recognise the place they were yesterday.
 *
 * The SVG is one image (role="img") with a summary label; the list underneath
 * is the same information as text, so keyboards and screen readers get the
 * concepts one by one without focusable nodes inside the drawing.
 */

import { useId } from 'react';
import type { Journey } from '@/lib/api';
import { useT } from '@/lib/i18n';
import type { Dict } from '@/locales/en';

/** The terrain grammar's states — what is drawn, not what the engine stores. */
export type TerrainState = 'mastered' | 'learning' | 'uncertain' | 'review' | 'unknown';

export const TERRAIN_STATES: TerrainState[] = ['mastered', 'learning', 'uncertain', 'review', 'unknown'];

/**
 * Engine state → terrain state. "introduced" is early learning, not a state
 * of its own on the ground; "uncertain" stays visible because the honest
 * thing about a guess is to say it is one.
 */
export function terrainState(engineState: string): TerrainState {
  switch (engineState) {
    case 'mastered':
      return 'mastered';
    case 'introduced':
    case 'learning':
      return 'learning';
    case 'uncertain':
      return 'uncertain';
    case 'needs_review':
      return 'review';
    default:
      return 'unknown';
  }
}

export interface TerrainPlace {
  name: string;
  state: TerrainState;
  engineState: string;
  module: number;
  now: boolean;
}

interface Region {
  title: string;
  places: TerrainPlace[];
}

/**
 * Concepts in curriculum order, grouped by module. A concept the engine knows
 * about but the plan never names goes into a final region of its own rather
 * than vanishing — the map is of what the learner knows, not of the syllabus.
 */
export function layoutRegions(journey: Journey, elsewhere: string): Region[] {
  const stateOf = new Map(journey.concepts.map((c) => [c.name, c.state]));
  const seen = new Set<string>();
  const now = journey.current?.concept ?? null;
  const place = (name: string, module: number): TerrainPlace => {
    const engineState = stateOf.get(name) ?? 'not_started';
    return { name, state: terrainState(engineState), engineState, module, now: name === now };
  };

  const regions: Region[] = journey.plan.map((module, index) => {
    const places: TerrainPlace[] = [];
    for (const lesson of module.lessons) {
      for (const name of lesson.concepts) {
        if (seen.has(name)) continue;
        seen.add(name);
        places.push(place(name, index));
      }
    }
    return { title: module.title, places };
  });

  const unplaced = journey.concepts.filter((c) => !seen.has(c.name));
  if (unplaced.length > 0) {
    regions.push({
      title: elsewhere,
      places: unplaced.map((c) => place(c.name, regions.length)),
    });
  }
  return regions.filter((r) => r.places.length > 0);
}

/** The concept after "now" in curriculum order; the first unsettled one when there is no "now". */
export function nextPlace(places: TerrainPlace[]): TerrainPlace | null {
  const at = places.findIndex((p) => p.now);
  if (at >= 0) return places[at + 1] ?? null;
  return places.find((p) => p.state !== 'mastered') ?? null;
}

// Geometry, in viewBox units. A region grows with its concepts so names have
// room; the whole thing scrolls sideways rather than shrinking past reading.
const HEIGHT = 300;
const STEP = 124;
const PAD = 52;
const MIN_REGION = 180;
const MID_Y = 168;
const WAVE = 34;
const MAX_LABEL = 20;

function regionWidth(count: number): number {
  return Math.max(MIN_REGION, count * STEP + PAD);
}

function shorten(name: string): string {
  return name.length > MAX_LABEL ? `${name.slice(0, MAX_LABEL - 1)}…` : name;
}

interface Placed extends TerrainPlace {
  x: number;
  y: number;
}

function place(regions: Region[]): { placed: Placed[]; bounds: { x: number; width: number }[] } {
  const placed: Placed[] = [];
  const bounds: { x: number; width: number }[] = [];
  let x0 = 0;
  let step = 0;
  for (const region of regions) {
    const width = regionWidth(region.places.length);
    bounds.push({ x: x0, width });
    const gap = width / (region.places.length + 1);
    for (const [i, p] of region.places.entries()) {
      // A slow sine across the whole path, so the curve is continuous from
      // one region into the next instead of restarting at every border.
      const y = MID_Y + Math.sin(step * 0.9) * WAVE;
      placed.push({ ...p, x: x0 + gap * (i + 1), y });
      step += 1;
    }
    x0 += width;
  }
  return { placed, bounds };
}

function Contours({ x, width, index }: { x: number; width: number; index: number }) {
  // Two nested rings per region, tilted a touch differently each so the
  // ground reads as drawn rather than stamped. The index makes it stable.
  const cx = x + width / 2;
  const tilt = ((index % 3) - 1) * 4;
  const rx = width / 2 - 14;
  return (
    <g fill="none" stroke="currentColor" strokeOpacity={0.16} strokeWidth={1}>
      <ellipse cx={cx} cy={MID_Y} rx={rx} ry={92} transform={`rotate(${tilt} ${cx} ${MID_Y})`} />
      <ellipse cx={cx} cy={MID_Y + 6} rx={rx * 0.7} ry={62} transform={`rotate(${-tilt} ${cx} ${MID_Y})`} />
    </g>
  );
}

function Mark({ state, hatch, r }: { state: TerrainState; hatch: string; r: number }) {
  switch (state) {
    case 'mastered':
      return <circle r={r} fill="currentColor" />;
    case 'learning':
      return (
        <>
          <circle r={r} fill={`url(#${hatch})`} />
          <circle r={r} fill="none" stroke="currentColor" strokeWidth={1.25} />
        </>
      );
    case 'uncertain':
      // The same hatching as learning, lighter: the engine is not sure, and
      // the ground should not look more settled than the evidence is.
      return (
        <>
          <circle r={r} fill={`url(#${hatch})`} opacity={0.45} />
          <circle r={r} fill="none" stroke="currentColor" strokeWidth={1.25} strokeOpacity={0.6} />
        </>
      );
    case 'review':
      return (
        <>
          <circle r={r + 6} fill="none" stroke="currentColor" strokeWidth={1.25} strokeDasharray="3 3" />
          <circle r={r} fill="currentColor" opacity={0.78} />
        </>
      );
    default:
      return <circle r={r} fill="none" stroke="currentColor" strokeWidth={1.25} strokeDasharray="1.5 3" />;
  }
}

function radius(state: TerrainState): number {
  return state === 'mastered' ? 11 : 8;
}

function Legend({ hatch, labels }: { hatch: string; labels: Dict['terrain']['states'] }) {
  return (
    <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2 font-mono text-xs text-ink-500">
      {TERRAIN_STATES.map((state) => (
        <li key={state} className="inline-flex items-center gap-2">
          <svg viewBox="-10 -10 20 20" className="h-4 w-4 text-ink-800" aria-hidden="true">
            <Mark state={state} hatch={hatch} r={state === 'review' ? 4 : 6} />
          </svg>
          {labels[state]}
        </li>
      ))}
    </ul>
  );
}

export function summarise(journey: Journey, placed: TerrainPlace[], t: Dict): string {
  const counts = Object.fromEntries(TERRAIN_STATES.map((s) => [s, 0])) as Record<TerrainState, number>;
  for (const p of placed) counts[p.state] += 1;
  const now = placed.find((p) => p.now)?.name ?? null;
  return t.terrain.summary(journey.subject, placed.length, counts, now);
}

export function ConceptTerrain({ journey, className = '' }: { journey: Journey; className?: string }) {
  const t = useT();
  const hatch = `${useId()}-hatch`;
  const regions = layoutRegions(journey, t.terrain.elsewhere);
  const { placed, bounds } = place(regions);
  const width = bounds.reduce((sum, b) => sum + b.width, 0);
  const summary = summarise(journey, placed, t);

  if (placed.length === 0) {
    return <p className={`text-sm text-ink-500 ${className}`}>{t.terrain.noConcepts}</p>;
  }

  return (
    <figure className={className}>
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${HEIGHT}`}
          role="img"
          aria-label={summary}
          className="h-auto text-ink-800"
          // Below this width the names collide; the container scrolls instead.
          style={{ width: '100%', minWidth: `${Math.round(width * 0.8)}px` }}
        >
          <defs>
            <pattern id={hatch} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="5" stroke="currentColor" strokeWidth="1.4" />
            </pattern>
          </defs>

          {bounds.map((b, i) => (
            <g key={regions[i]!.title + i}>
              <Contours x={b.x} width={b.width} index={i} />
              {i > 0 && (
                <line
                  x1={b.x}
                  y1={24}
                  x2={b.x}
                  y2={HEIGHT - 24}
                  stroke="currentColor"
                  strokeOpacity={0.12}
                  strokeDasharray="2 6"
                />
              )}
              <text
                x={b.x + 16}
                y={24}
                fill="currentColor"
                opacity={0.6}
                style={{ font: '500 11px var(--font-mono)' }}
              >
                {shorten(regions[i]!.title)}
              </text>
            </g>
          ))}

          <g stroke="currentColor" strokeOpacity={0.35} strokeWidth={1} fill="none">
            {placed.slice(1).map((to, i) => {
              const from = placed[i]!;
              // Ground not yet walked is a dotted path, as on the landing.
              const dashed = from.state === 'unknown' || to.state === 'unknown';
              return (
                <line
                  key={`${from.name}-${to.name}`}
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  strokeDasharray={dashed ? '2 4' : undefined}
                />
              );
            })}
          </g>

          {placed.map((p) => {
            const r = radius(p.state);
            return (
              <g key={p.name} transform={`translate(${p.x} ${p.y})`} data-place={p.name} data-state={p.state}>
                <Mark state={p.state} hatch={hatch} r={r} />
                {p.now && (
                  <>
                    <circle r={r + 12} fill="none" stroke="var(--signal)" strokeWidth={1.5} />
                    <text
                      y={r + 30}
                      textAnchor="middle"
                      fill="var(--signal)"
                      style={{ font: '600 11px var(--font-mono)' }}
                    >
                      {t.terrain.now}
                    </text>
                  </>
                )}
                {p.state === 'uncertain' && !p.now && (
                  <text
                    y={r + 18}
                    textAnchor="middle"
                    fill="currentColor"
                    opacity={0.55}
                    style={{ font: '400 10px var(--font-mono)' }}
                  >
                    {t.terrain.states.uncertain}
                  </text>
                )}
                <text
                  y={-r - 8}
                  textAnchor="middle"
                  fill="currentColor"
                  opacity={p.state === 'unknown' ? 0.6 : 1}
                  style={{ font: `${p.state === 'mastered' ? 500 : 400} 13px var(--font-ui)` }}
                >
                  {shorten(p.name)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <figcaption>
        {/* The swatches reuse the map's hatch pattern: `url(#id)` resolves
            document-wide, so one definition serves both drawings. */}
        <Legend hatch={hatch} labels={t.terrain.states} />
        <ul className="mt-6 divide-y divide-line border-y border-line text-sm" aria-label={t.terrain.listLabel}>
          {placed.map((p) => (
            <li key={p.name} className="flex items-baseline justify-between gap-4 py-2">
              <span className="min-w-0 text-ink-800">
                {p.name}
                {p.now && (
                  <span className="ml-2 font-mono text-xs text-signal" data-now>
                    {t.terrain.now}
                  </span>
                )}
              </span>
              <span className="shrink-0 font-mono text-xs text-ink-500">{t.terrain.states[p.state]}</span>
            </li>
          ))}
        </ul>
      </figcaption>
    </figure>
  );
}
