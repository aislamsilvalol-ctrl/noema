'use client';

import { useState } from 'react';
import { Mino, type MinoState } from '@/components/mino/Mino';
import { POSES } from '@/components/mino/machine';

const STATES = Object.keys(POSES) as MinoState[];

export function MinoSheet() {
  const [state, setState] = useState<MinoState>('idle');
  const [dark, setDark] = useState(false);
  return (
    <main className="min-h-screen bg-surface px-6 py-8 text-ink-800">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-4 font-display text-xl text-ink-900">Mino — state sheet</h1>
        {STATES.map((s) => (
          <button
            key={s}
            type="button"
            aria-pressed={state === s}
            onClick={() => setState(s)}
            className={`rounded-md px-2 py-1 font-mono text-xs ${
              state === s ? 'bg-ink-900 text-ink-50' : 'bg-ink-100 text-ink-700'
            }`}
          >
            {s}
          </button>
        ))}
        <button
          type="button"
          onClick={() => {
            // The tokens live on :root, so the theme is switched there.
            document.documentElement.dataset.theme = dark ? 'light' : 'dark';
            setDark((d) => !d);
          }}
          className="ml-auto rounded-md border border-line px-2 py-1 font-mono text-xs"
        >
          {dark ? 'light' : 'dark'}
        </button>
      </div>

      {/* One WebGL stage, re-posed by the buttons: a browser caps the number
          of contexts, so the grid below is the SVG rig. */}
      <div className="mt-8 grid gap-10 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div data-sheet-stage className="mx-auto w-full max-w-md">
          <Mino state={state} size="xl" quality="high" className="w-full" />
          <p className="mt-2 text-center font-mono text-xs text-ink-500">{state} · WebGL</p>
        </div>
        <div className="grid grid-cols-4 gap-4 sm:grid-cols-5">
          {STATES.map((s) => (
            <figure key={s} className="text-center">
              <Mino state={s} size="md" />
              <figcaption className="mt-1 font-mono text-[10px] text-ink-500">{s}</figcaption>
            </figure>
          ))}
        </div>
      </div>
    </main>
  );
}
