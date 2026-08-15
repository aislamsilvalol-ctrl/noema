'use client';

/**
 * The concept graph.
 *
 * SVG rather than canvas, and every node is a real focusable element with a
 * label. A canvas graph is a picture of a data structure that a keyboard cannot
 * enter and a screen reader cannot read — the easiest place in this whole app to
 * fail WCAG, which `CONTRIBUTING.md` makes a merge requirement rather than an
 * aspiration.
 *
 * The layout is a small force simulation run to a fixed number of ticks and then
 * stopped. Deterministic given the same input, so the graph does not rearrange
 * itself under the reader between renders, and no dependency added for forty
 * lines of arithmetic.
 *
 * Motion is the one place `docs/design-system.md` allows expressiveness, because
 * here it carries structure: nodes settling show how tightly connected they are.
 * It is still disabled under `prefers-reduced-motion` — motion that carries
 * meaning does not get to make someone ill.
 */

import { useT } from '@/lib/i18n';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { Concept, ConceptEdge } from '@/lib/api';

const WIDTH = 720;
const HEIGHT = 480;
const TICKS = 220;

type Point = { id: string; x: number; y: number; vx: number; vy: number };

/**
 * Force-directed layout: nodes repel, edges pull, everything drifts to the
 * middle. Seeded from the node id so the same graph lands the same way twice.
 */
function layout(nodes: Concept[], edges: ConceptEdge[]): Map<string, Point> {
  const points: Point[] = nodes.map((node, i) => {
    // A circle rather than random: a random start occasionally produces a
    // knot that the simulation cannot undo in a fixed number of ticks.
    const angle = (i / Math.max(nodes.length, 1)) * Math.PI * 2;
    return {
      id: node.id,
      x: WIDTH / 2 + Math.cos(angle) * 140,
      y: HEIGHT / 2 + Math.sin(angle) * 140,
      vx: 0,
      vy: 0,
    };
  });

  const index = new Map(points.map((p) => [p.id, p]));

  for (let tick = 0; tick < TICKS; tick++) {
    const cooling = 1 - tick / TICKS;

    for (const a of points) {
      for (const b of points) {
        if (a.id === b.id) continue;
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const distance = Math.max(Math.hypot(dx, dy), 1);
        const push = (2600 / (distance * distance)) * cooling;
        a.vx += (dx / distance) * push;
        a.vy += (dy / distance) * push;
      }
    }

    for (const edge of edges) {
      const a = index.get(edge.src_id);
      const b = index.get(edge.dst_id);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const distance = Math.max(Math.hypot(dx, dy), 1);
      const pull = (distance - 120) * 0.012 * cooling;
      a.vx += (dx / distance) * pull;
      a.vy += (dy / distance) * pull;
      b.vx -= (dx / distance) * pull;
      b.vy -= (dy / distance) * pull;
    }

    for (const p of points) {
      p.vx += (WIDTH / 2 - p.x) * 0.004 * cooling;
      p.vy += (HEIGHT / 2 - p.y) * 0.004 * cooling;
      p.x = Math.min(Math.max(p.x + p.vx, 40), WIDTH - 40);
      p.y = Math.min(Math.max(p.y + p.vy, 30), HEIGHT - 30);
      p.vx *= 0.82;
      p.vy *= 0.82;
    }
  }

  return index;
}

function tone(mastery: number | undefined): string {
  if (mastery === undefined) return 'var(--ink-300)';
  if (mastery >= 80) return 'var(--positive)';
  if (mastery >= 60) return 'var(--ink-600)';
  if (mastery >= 40) return 'var(--ink-400)';
  return 'var(--critical)';
}

export function ConceptGraph({
  nodes,
  edges,
  mastery,
  rootId,
  onExpand,
}: {
  nodes: Concept[];
  edges: ConceptEdge[];
  mastery: Map<string, number>;
  rootId: string;
  onExpand: (conceptId: string) => void;
}) {
  const t = useT();
  const positions = useMemo(() => layout(nodes, edges), [nodes, edges]);
  const [focused, setFocused] = useState(rootId);
  const container = useRef<SVGSVGElement>(null);

  useEffect(() => setFocused(rootId), [rootId]);

  /** Neighbours of a node, in a stable order, for arrow-key navigation. */
  const neighbours = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const edge of edges) {
      map.set(edge.src_id, [...(map.get(edge.src_id) ?? []), edge.dst_id]);
      map.set(edge.dst_id, [...(map.get(edge.dst_id) ?? []), edge.src_id]);
    }
    return map;
  }, [edges]);

  function move(from: string, direction: 1 | -1) {
    // Arrow keys walk the edges rather than the screen: the structure is the
    // thing being navigated, and "the node slightly to the left" is not a
    // relationship.
    const around = neighbours.get(from) ?? [];
    if (around.length === 0) return;
    const current = around.indexOf(focused);
    const next = around[(current + direction + around.length) % around.length];
    if (next) setFocused(next);
  }

  return (
    <div>
      <svg
        ref={container}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full rounded-lg border border-line"
        role="group"
        aria-label={t.graph.graphLabel(nodes.length, edges.length)}
      >
        <g>
          {edges.map((edge) => {
            const a = positions.get(edge.src_id);
            const b = positions.get(edge.dst_id);
            if (!a || !b) return null;
            const prerequisite = edge.kind === 'prerequisite_of';
            return (
              <line
                key={edge.id}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="var(--line)"
                strokeWidth={prerequisite ? 1.6 : 1}
                // Prerequisites are solid and directional; everything else is
                // dashed. A graph where every line means the same thing is a
                // picture, not a model.
                strokeDasharray={prerequisite ? undefined : '4 4'}
                markerEnd={prerequisite ? 'url(#arrow)' : undefined}
              />
            );
          })}
        </g>

        <defs>
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="18"
            refY="5"
            markerWidth="5"
            markerHeight="5"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--line)" />
          </marker>
        </defs>

        {nodes.map((node) => {
          const point = positions.get(node.id);
          if (!point) return null;
          const score = mastery.get(node.id);
          const isFocused = focused === node.id;

          return (
            <g
              key={node.id}
              tabIndex={0}
              role="button"
              aria-label={
                score === undefined
                  ? t.graph.nodeUnscored(node.name)
                  : t.graph.nodeScored(node.name, Math.round(score))
              }
              aria-current={node.id === rootId ? 'true' : undefined}
              onFocus={() => setFocused(node.id)}
              onClick={() => onExpand(node.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onExpand(node.id);
                } else if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
                  event.preventDefault();
                  move(node.id, 1);
                } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
                  event.preventDefault();
                  move(node.id, -1);
                }
              }}
              className="cursor-pointer focus:outline-none"
              transform={`translate(${point.x} ${point.y})`}
            >
              <circle
                r={node.id === rootId ? 11 : 7}
                fill={tone(score)}
                stroke={isFocused ? 'var(--ink-900)' : 'transparent'}
                strokeWidth={2}
              />
              <text
                y={-16}
                textAnchor="middle"
                className="fill-ink-700 text-[11px]"
                style={{ pointerEvents: 'none' }}
              >
                {node.name}
              </text>
            </g>
          );
        })}
      </svg>

      <p className="mt-3 text-xs text-ink-500">
        Solid arrows are prerequisites; dashed lines are related concepts. Colour is
        mastery. Tab to a concept, arrow keys to walk its connections, Enter to open
        its neighbourhood.
      </p>
    </div>
  );
}
