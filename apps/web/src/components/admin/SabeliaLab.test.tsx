// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SabeliaLab } from './SabeliaLab';

/**
 * The Lab exists to stop the engine being oversold, so what is tested is the
 * warnings: a synthetic dataset says so, one seed says so, and a dataset where
 * a baseline beats the candidate says that too. The data is the real snapshot —
 * if a future run changes what the table claims, these assertions are what
 * notices.
 */

vi.mock('@/lib/i18n', async () => {
  const { en } = await import('@/locales/en');
  return { useT: () => en };
});

describe('SabeliaLab', () => {
  it('labels a synthetic dataset as validating the pipeline, not the model', () => {
    render(<SabeliaLab />);

    expect(screen.getAllByText('synthetic').length).toBeGreaterThan(0);
    expect(screen.getByText(/validates the pipeline, not the model/)).toBeInTheDocument();
  });

  it('shows the public benchmark with its seeds and its spread', () => {
    render(<SabeliaLab />);

    expect(screen.getAllByText('duolingo-hlr').length).toBeGreaterThan(0);
    // three seeds are rendered as mean ± sd, which is the only honest form
    expect(screen.getAllByText(/0\.\d{4} ± 0\.\d{4}/).length).toBeGreaterThan(0);
  });

  it('names the baseline when a baseline wins', () => {
    render(<SabeliaLab />);

    const notes = screen.queryAllByText(/the simple baseline wins/);
    // the synthetic table is one of those; if it ever stops being, this test
    // should be updated deliberately rather than silently passing
    expect(notes.length).toBeGreaterThan(0);
  });

  it('says the engine is in shadow and never shown to a learner', () => {
    render(<SabeliaLab />);

    expect(screen.getByText(/integrated in shadow only/)).toBeInTheDocument();
    expect(screen.getByText(/never shown to a learner/)).toBeInTheDocument();
  });

  it('marks ablation rows so they are not read as separate models', () => {
    render(<SabeliaLab />);

    // not scoped to the first table: which dataset holds the ablations depends
    // on which benchmark ran last, and this is about the label, not the order
    const marked = screen.getAllByText('ablation');
    expect(marked.length).toBeGreaterThan(0);
    for (const label of marked) {
      expect(label.closest('tr')?.textContent).toMatch(/^sabelia-/);
    }
  });
});
