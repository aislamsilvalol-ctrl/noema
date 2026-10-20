'use client';

import { Button } from '@/components/ui/Button';

const LABELS = [
  'Começar',
  'Continuar de onde você parou',
  'Continuar donde lo dejaste en Fundamentos de programación',
  'Review the formula you got wrong twice',
  'Revisar Equações diferenciais ordinárias de segunda ordem',
  'Supercalifragilisticexpialidocious-sem-espaço',
];

const OPTIONS = [
  'A',
  'Porque a velocidade média é a distância total dividida pelo tempo total, não a média das velocidades',
  'Because the discriminant is negative, so the parabola never crosses the x-axis at all',
];

const WIDTHS = [320, 375, 430];

export function StressSheet() {
  return (
    <main className="min-h-screen bg-surface p-4 text-ink-900">
      <h1 className="font-display text-2xl">Text stress</h1>
      <div className="mt-6 flex flex-wrap items-start gap-6">
        {WIDTHS.map((width) => (
          <section key={width} style={{ width }} className="border border-dashed border-ink-400 p-0" data-width={width}>
            <p className="font-mono text-xs text-ink-500">{width}px</p>
            <div className="mt-3 flex flex-col items-start gap-3 px-4">
              {LABELS.map((label) => (
                <Button key={label} variant="primary" size="lg">
                  {label} →
                </Button>
              ))}
              <div className="flex w-full flex-wrap gap-2">
                {LABELS.slice(0, 4).map((label) => (
                  <Button key={label} size="sm">
                    {label}
                  </Button>
                ))}
              </div>
              <div className="flex w-full gap-2">
                <Button variant="primary" className="flex-1">
                  {LABELS[2]}
                </Button>
                <Button variant="ghost">{LABELS[1]}</Button>
              </div>
              <div className="flex w-full flex-col gap-2">
                {OPTIONS.map((option) => (
                  <button
                    key={option}
                    type="button"
                    className="flex w-full rounded-md border border-line bg-raised px-4 py-3 text-left text-base"
                  >
                    {option}
                  </button>
                ))}
              </div>
            </div>
          </section>
        ))}
      </div>
    </main>
  );
}
