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
import { ProgressTabs } from '@/components/progress/ProgressTabs';
import { Shell } from '@/components/Shell';
import { Mino } from '@/components/mino/Mino';
import { Loading } from '@/components/ui/Loading';
import { Notice } from '@/components/ui/Notice';
import { SegmentedControl } from '@/components/ui/SegmentedControl';
import { ApiError, api, type Concept, type ConceptEdge } from '@/lib/api';
import { humanError } from '@/lib/errors';
import { useT } from '@/lib/i18n';

export default function GraphPage() {
  const router = useRouter();
  const t = useT();
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [rootId, setRootId] = useState<string | null>(null);
  const [nodes, setNodes] = useState<Concept[]>([]);
  const [edges, setEdges] = useState<ConceptEdge[]>([]);
  const [mastery, setMastery] = useState<Map<string, number>>(new Map());
  const [hasJourney, setHasJourney] = useState(false);
  const [depth, setDepth] = useState(2);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      // Conversation mastery included: a learner who studies only through
      // Mino has no cards or answers, and their nodes would all read unscored.
      // The journeys only decide which empty state to show, so a failure
      // there must not blank the graph.
      const [all, scores, journeys] = await Promise.all([
        api.concepts(),
        api.mastery(false, true),
        api.journeys().catch(() => []),
      ]);
      setConcepts(all);
      setMastery(new Map(scores.map((s) => [s.concept_id, s.mastery])));
      setHasJourney(journeys.length > 0);
      if (all[0] && !rootId) setRootId(all[0].id);
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        router.push('/login');
        return;
      }
      setError(humanError(err, t, 'load'));
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
          setError(humanError(err, t, 'load'));
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
          <SegmentedControl
            label={t.graph.depth}
            value={depth}
            onChange={setDepth}
            options={[1, 2, 3].map((level) => ({ value: level, label: String(level) }))}
          />
        </span>
      </header>
      <ProgressTabs />

      {error && (
        <p role="alert" className="mt-6 max-w-reading text-sm text-critical">
          {error}
        </p>
      )}

      {loading ? (
        <Loading mino className="mt-10" />
      ) : concepts.length === 0 ? (
        // With a journey behind them, an empty graph does not mean nothing was
        // learned: the map on /progress already shows what the lessons reached.
        hasJourney ? (
          <Notice
            kind="empty"
            title={t.graph.mapTitle}
            body={t.graph.mapBody}
            action={{ label: t.graph.mapAction, href: '/progress' }}
            mino={<Mino state="curious" size="lg" />}
          />
        ) : (
          <Notice
            kind="empty"
            title={t.graph.emptyTitle}
            body={t.graph.emptyBody}
            action={{ label: t.graph.emptyAction, href: '/learn/new' }}
            mino={<Mino state="curious" size="lg" />}
          />
        )
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
            <h2 className="font-mono text-xs text-ink-500">
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
