'use client';

/**
 * The knowledge graph, one neighbourhood at a time.
 *
 * Never the whole workspace: a graph view that renders everything is a hairball,
 * and the API refuses to serve one for the same reason. You start at a concept
 * and walk outward, which is also how anyone actually reads a graph.
 */

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ConceptGraph } from '@/components/ConceptGraph';
import { Shell } from '@/components/Shell';
import { ApiError, api, type Concept, type ConceptEdge } from '@/lib/api';
import { useT } from '@/lib/i18n';

export default function GraphPage() {
  const router = useRouter();
  const t = useT();
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [rootId, setRootId] = useState<string | null>(null);
  const [nodes, setNodes] = useState<Concept[]>([]);
  const [edges, setEdges] = useState<ConceptEdge[]>([]);
  const [mastery, setMastery] = useState<Map<string, number>>(new Map());
  const [depth, setDepth] = useState(2);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [all, scores] = await Promise.all([api.concepts(), api.mastery()]);
      setConcepts(all);
      setMastery(new Map(scores.map((s) => [s.concept_id, s.mastery])));
      if (all[0] && !rootId) setRootId(all[0].id);
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        router.push('/login');
        return;
      }
      setError(err instanceof Error ? err.message : t.graph.couldNotLoadConcepts);
    } finally {
      setLoading(false);
    }
  }, [router, rootId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!rootId) return;
    let cancelled = false;

    void (async () => {
      try {
        const graph = await api.conceptGraph(rootId, depth);
        // Guarded because clicking through the graph quickly starts several of
        // these, and an older one landing last would show the wrong
        // neighbourhood.
        if (cancelled) return;
        setNodes(graph.nodes);
        setEdges(graph.edges);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t.graph.couldNotLoadGraph);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [rootId, depth, t]);

  return (
    <Shell>
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="font-display text-2xl text-ink-900">{t.graph.title}</h1>
        <span className="flex items-center gap-2 text-sm text-ink-500">
          {t.graph.depth}
          {[1, 2, 3].map((level) => (
            <button
              key={level}
              type="button"
              onClick={() => setDepth(level)}
              aria-pressed={depth === level}
              className={`rounded-md px-2 py-1 text-sm transition-colors duration-state ${
                depth === level ? 'bg-ink-100 text-ink-900' : 'hover:text-ink-900'
              }`}
            >
              {level}
            </button>
          ))}
        </span>
      </header>

      {error && (
        <p role="alert" className="mt-6 max-w-reading text-sm text-critical">
          {error}
        </p>
      )}

      {loading ? (
        <p className="mt-10 text-sm text-ink-500">{t.common.loading}</p>
      ) : concepts.length === 0 ? (
        <div className="mt-16 max-w-reading">
          <h2 className="text-lg text-ink-900">{t.graph.emptyTitle}</h2>
          <p className="mt-2 text-base text-ink-600">
            {t.graph.emptyBody}
          </p>
        </div>
      ) : (
        <div className="mt-8 flex flex-col gap-8 lg:flex-row">
          <div className="min-w-0 flex-1">
            {nodes.length > 0 && rootId && (
              <ConceptGraph
                nodes={nodes}
                edges={edges}
                mastery={mastery}
                rootId={rootId}
                onExpand={setRootId}
              />
            )}
          </div>

          <nav className="w-full shrink-0 lg:w-64" aria-label={t.graph.allConcepts}>
            <h2 className="text-xs uppercase tracking-wide text-ink-500">
              {t.graph.startSomewhere}
            </h2>
            <ul className="mt-3 max-h-[28rem] space-y-0.5 overflow-y-auto">
              {concepts.map((concept) => (
                <li key={concept.id}>
                  <button
                    type="button"
                    onClick={() => setRootId(concept.id)}
                    aria-current={concept.id === rootId ? 'true' : undefined}
                    className={`w-full truncate rounded-md px-2 py-1.5 text-left text-sm transition-colors duration-state ${
                      concept.id === rootId
                        ? 'bg-ink-100 text-ink-900'
                        : 'text-ink-600 hover:text-ink-900'
                    }`}
                  >
                    {concept.name}
                  </button>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      )}
    </Shell>
  );
}
