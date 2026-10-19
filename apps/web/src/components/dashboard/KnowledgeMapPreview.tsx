'use client';

/**
 * The journey's concepts as places on a map, grouped the way a learner asks
 * about them — what is mine, what I am learning, what is worth firming up —
 * not as a graph with edges and scores. The full map lives on Progress.
 */

import Link from 'next/link';
import type { JourneyConcept } from '@/lib/api';
import { useT } from '@/lib/i18n';

const GROUP: Record<string, 'mastered' | 'learning' | 'shaky'> = {
  mastered: 'mastered',
  learning: 'learning',
  introduced: 'learning',
  uncertain: 'shaky',
  needs_review: 'shaky',
};

const TONE = {
  mastered: { chip: 'bg-dash-mineral-soft text-ink-900', dot: 'bg-dash-mineral' },
  learning: { chip: 'bg-dash-sky-soft text-ink-900', dot: 'bg-primary' },
  shaky: { chip: 'bg-dash-meadow-soft text-ink-900', dot: 'bg-dash-meadow' },
} as const;

export function KnowledgeMapPreview({ concepts, subject }: { concepts: JourneyConcept[]; subject: string }) {
  const t = useT();
  const copy = t.home.trail;
  const own = subject.trim().toLowerCase();
  const named = concepts.filter((c) => c.name.trim().toLowerCase() !== own && GROUP[c.state]);
  if (named.length === 0) return null;

  const groups = (['mastered', 'learning', 'shaky'] as const)
    .map((key) => ({ key, items: named.filter((c) => GROUP[c.state] === key) }))
    .filter((group) => group.items.length > 0);

  return (
    <div className="grid gap-6 sm:grid-cols-3" data-knowledge-map>
      {groups.map((group) => (
        <div key={group.key} data-concept-group={group.key}>
          <p className="flex items-center gap-2 text-sm text-ink-600">
            <span aria-hidden="true" className={`h-2 w-2 rounded-full ${TONE[group.key].dot}`} />
            {copy.groups[group.key]}
            <span className="font-mono text-xs text-ink-400">{group.items.length}</span>
          </p>
          <ul className="mt-3 flex flex-wrap gap-2">
            {group.items.map((concept) => (
              <li key={concept.name} className={`rounded-full px-3 py-1.5 text-sm ${TONE[group.key].chip}`}>
                {concept.name}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

export function MapLink() {
  const t = useT();
  return (
    <Link href="/progress" className="text-sm text-accent underline-offset-4 hover:underline">
      {t.home.trail.map} →
    </Link>
  );
}
