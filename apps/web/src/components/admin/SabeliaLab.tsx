'use client';

import snapshot from '@/data/sabelia-benchmarks.json';
import { useT } from '@/lib/i18n';

/**
 * The Lab: what the learner model can and cannot do, as measured.
 *
 * Admin-only, and deliberately not a dashboard. It renders a frozen snapshot of
 * the benchmark runs (`scripts/sabelia-snapshot.py`) — the product never calls
 * the engine to draw a page — and it leads with the losses. A synthetic dataset
 * is labelled synthetic; a table with one seed says one seed; the model's own
 * ablations are shown next to it even where they say the model's parts do not
 * help. The moment this page starts reading like a product claim it is wrong.
 */

type ModelRow = {
  model: string;
  seeds: number;
  auc: number;
  auc_sd?: number;
  log_loss: number;
  ece: number;
  accuracy: number;
  seconds: number;
};

type DatasetRow = {
  dataset: string;
  version: string;
  kind: string;
  ran_at: number;
  git: string;
  models: ModelRow[];
};

const DATASETS = snapshot.datasets as DatasetRow[];

/** A baseline is anything that is not the candidate or one of its ablations. */
function isCandidate(model: string) {
  return model === 'sabelia';
}

function isAblation(model: string) {
  return model.startsWith('sabelia-');
}

function metric(value: number, sd?: number) {
  return sd === undefined ? value.toFixed(4) : `${value.toFixed(4)} ± ${sd.toFixed(4)}`;
}

function when(seconds: number) {
  return new Date(seconds * 1000).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function SabeliaLab() {
  const t = useT();
  const stale = Date.now() / 1000 - (snapshot.generated_at as number) > 60 * 60 * 24 * 30;

  return (
    <section>
      <h2 className="font-display text-xl text-ink-900">{t.admin.lab.title}</h2>
      <p className="mt-2 max-w-2xl text-sm text-ink-500">{t.admin.lab.lede}</p>
      <p className="mt-1 text-xs text-ink-400">
        {t.admin.lab.snapshot} {when(snapshot.generated_at as number)}
        {stale ? ` · ${t.admin.lab.stale}` : ''}
      </p>

      {DATASETS.map((dataset) => {
        const best = dataset.models.reduce((a, b) => (a.auc >= b.auc ? a : b));
        const bestBaseline = dataset.models
          .filter((m) => !isCandidate(m.model) && !isAblation(m.model))
          .reduce((a, b) => (a.auc >= b.auc ? a : b));
        const candidate = dataset.models.find((m) => isCandidate(m.model));
        const oneSeed = dataset.models.every((m) => m.seeds < 2);

        return (
          <div key={`${dataset.dataset}:${dataset.version}`} className="mt-8">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h3 className="font-medium text-ink-900">{dataset.dataset}</h3>
              <span
                className={`rounded px-1.5 py-0.5 text-[11px] uppercase tracking-wide ${
                  dataset.kind === 'synthetic'
                    ? 'bg-amber-100 text-amber-900'
                    : 'bg-ink-100 text-ink-600'
                }`}
              >
                {dataset.kind === 'synthetic' ? t.admin.lab.synthetic : t.admin.lab.public}
              </span>
              <span className="text-xs text-ink-400">
                {when(dataset.ran_at)} · {dataset.version}
                {dataset.git ? ` · ${dataset.git}` : ''}
              </span>
            </div>

            {dataset.kind === 'synthetic' && (
              <p className="mt-1 text-xs text-amber-800">{t.admin.lab.syntheticWarning}</p>
            )}
            {oneSeed && <p className="mt-1 text-xs text-ink-500">{t.admin.lab.oneSeed}</p>}
            {candidate && candidate.auc < bestBaseline.auc && (
              <p className="mt-1 text-xs text-ink-700">
                {t.admin.lab.baselineWins.replace('{model}', bestBaseline.model)}
              </p>
            )}

            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[36rem] text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-ink-400">
                  <tr>
                    <th className="py-1 pr-4 font-normal">{t.admin.lab.model}</th>
                    <th className="py-1 pr-4 font-normal">{t.admin.lab.seeds}</th>
                    <th className="py-1 pr-4 font-normal">AUC</th>
                    <th className="py-1 pr-4 font-normal">{t.admin.lab.logLoss}</th>
                    <th className="py-1 pr-4 font-normal">ECE</th>
                    <th className="py-1 pr-4 font-normal">{t.admin.lab.trainTime}</th>
                  </tr>
                </thead>
                <tbody>
                  {dataset.models.map((row) => (
                    <tr
                      key={row.model}
                      className={`border-t border-ink-100 ${
                        row.model === best.model ? 'text-ink-900' : 'text-ink-600'
                      }`}
                    >
                      <td className="py-1.5 pr-4">
                        <span className={isCandidate(row.model) ? 'font-medium' : ''}>
                          {row.model}
                        </span>
                        {isAblation(row.model) && (
                          <span className="ml-2 text-[11px] text-ink-400">
                            {t.admin.lab.ablation}
                          </span>
                        )}
                      </td>
                      <td className="py-1.5 pr-4 tabular-nums">{row.seeds}</td>
                      <td className="py-1.5 pr-4 tabular-nums">{metric(row.auc, row.auc_sd)}</td>
                      <td className="py-1.5 pr-4 tabular-nums">{row.log_loss.toFixed(4)}</td>
                      <td className="py-1.5 pr-4 tabular-nums">{row.ece.toFixed(4)}</td>
                      <td className="py-1.5 pr-4 tabular-nums text-ink-400">{row.seconds}s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}

      <p className="mt-8 max-w-2xl text-xs text-ink-500">{t.admin.lab.shadow}</p>
    </section>
  );
}
