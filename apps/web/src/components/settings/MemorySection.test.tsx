// @vitest-environment jsdom
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MemorySection } from './MemorySection';
import type { Journey, JourneyMemory } from '@/lib/api';

const { journeys, journeyMemory, forgetPattern, forgetSummary, forgetMisconception, forgetAll } =
  vi.hoisted(() => ({
    journeys: vi.fn(),
    journeyMemory: vi.fn(),
    forgetPattern: vi.fn(),
    forgetSummary: vi.fn(),
    forgetMisconception: vi.fn(),
    forgetAll: vi.fn(),
  }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    api: {
      journeys,
      journeyMemory,
      forgetPattern,
      forgetSummary,
      forgetMisconception,
      forgetJourneyMemory: forgetAll,
    },
  };
});

// Only what the picker reads; the rest of a journey is not this section's business.
const freud = { id: 'j-1', subject: 'Psicanálise', objective: 'Entender Freud' } as Journey;
const kant = { id: 'j-2', subject: 'Filosofia', objective: 'Ler a Crítica' } as Journey;

const remembered: JourneyMemory = {
  patterns: ['analogias funcionam', 'precisa da fórmula primeiro'],
  communication: [{ label: 'verbosity', value: 'lower' }],
  summaries: [
    {
      id: 's-1',
      level: 'session',
      text: 'o inconsciente',
      next_step: 'recalque',
      created_at: '2026-09-20T10:00:00Z',
    },
  ],
  misconceptions: [{ concept: 'inconsciente', text: 'tudo que esqueci está no inconsciente' }],
};

const nothing: JourneyMemory = {
  patterns: [],
  communication: [],
  summaries: [],
  misconceptions: [],
};

afterEach(() => {
  vi.resetAllMocks();
});

async function renderWith(memory: JourneyMemory, list: Journey[] = [freud, kant]) {
  journeys.mockResolvedValue(list);
  journeyMemory.mockResolvedValue(memory);
  render(<MemorySection />);
  await waitFor(() => expect(journeyMemory).toHaveBeenCalledWith(list[0]!.id));
}

describe('MemorySection', () => {
  it('lists what Mino remembers on the most recent course, in plain terms', async () => {
    await renderWith(remembered);

    expect(await screen.findByText('analogias funcionam')).toBeInTheDocument();
    expect(screen.getByText('precisa da fórmula primeiro')).toBeInTheDocument();
    // A preference is shown by its human label, never the JSON key.
    expect(screen.getByText(/Length/)).toBeInTheDocument();
    expect(screen.queryByText(/verbosity/)).not.toBeInTheDocument();
    expect(screen.getByText('o inconsciente')).toBeInTheDocument();
    expect(screen.getByText(/Next: recalque/)).toBeInTheDocument();
    expect(screen.getByText('tudo que esqueci está no inconsciente')).toBeInTheDocument();
    expect(screen.getByRole('combobox')).toHaveValue('j-1');
  });

  it('forgets one line and re-reads the list from the server', async () => {
    forgetPattern.mockResolvedValue(undefined);
    const user = userEvent.setup();
    await renderWith(remembered);
    await screen.findByText('analogias funcionam');
    journeyMemory.mockResolvedValue({ ...remembered, patterns: ['precisa da fórmula primeiro'] });

    await user.click(screen.getByRole('button', { name: 'Forget: analogias funcionam' }));

    expect(forgetPattern).toHaveBeenCalledWith('j-1', 0);
    await waitFor(() => {
      expect(screen.queryByText('analogias funcionam')).not.toBeInTheDocument();
    });
    expect(screen.getByRole('status')).toHaveTextContent('Forgotten.');
  });

  it('forgets a summary and a misconception by what they are, not by position', async () => {
    forgetSummary.mockResolvedValue(undefined);
    forgetMisconception.mockResolvedValue(undefined);
    const user = userEvent.setup();
    await renderWith(remembered);
    await screen.findByText('o inconsciente');

    await user.click(screen.getByRole('button', { name: 'Forget: o inconsciente' }));
    expect(forgetSummary).toHaveBeenCalledWith('j-1', 's-1');

    await user.click(
      screen.getByRole('button', { name: 'Forget: tudo que esqueci está no inconsciente' }),
    );
    expect(forgetMisconception).toHaveBeenCalledWith(
      'j-1',
      'inconsciente',
      'tudo que esqueci está no inconsciente',
    );
  });

  it('asks once before forgetting everything on a course, and can be talked out of it', async () => {
    forgetAll.mockResolvedValue(undefined);
    const user = userEvent.setup();
    await renderWith(remembered);
    await screen.findByText('analogias funcionam');

    await user.click(screen.getByRole('button', { name: 'Forget everything on this course' }));
    expect(forgetAll).not.toHaveBeenCalled();
    const confirm = screen.getByRole('group', { name: 'Forget everything on this course' });
    expect(confirm).toHaveTextContent(/plan, progress and cards stay/);

    await user.click(within(confirm).getByRole('button', { name: 'Cancel' }));
    expect(forgetAll).not.toHaveBeenCalled();
    expect(screen.queryByRole('group')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Forget everything on this course' }));
    journeyMemory.mockResolvedValue(nothing);
    await user.click(screen.getByRole('button', { name: 'Yes, forget' }));

    expect(forgetAll).toHaveBeenCalledWith('j-1');
    expect(await screen.findByText(/remembers nothing about you on this course/)).toBeInTheDocument();
  });

  it('re-reads memory when another course is picked', async () => {
    const user = userEvent.setup();
    await renderWith(remembered);
    await screen.findByText('analogias funcionam');
    journeyMemory.mockResolvedValue(nothing);

    await user.selectOptions(screen.getByRole('combobox'), 'j-2');

    await waitFor(() => expect(journeyMemory).toHaveBeenCalledWith('j-2'));
    expect(await screen.findByText(/remembers nothing/)).toBeInTheDocument();
    expect(screen.queryByText('analogias funcionam')).not.toBeInTheDocument();
  });

  it('says so when there is no course yet, without asking the server for memory', async () => {
    journeys.mockResolvedValue([]);
    render(<MemorySection />);

    expect(await screen.findByText(/Mino starts remembering/)).toBeInTheDocument();
    expect(journeyMemory).not.toHaveBeenCalled();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('keeps the line and says so when forgetting fails', async () => {
    forgetPattern.mockRejectedValue(new Error('network down'));
    const user = userEvent.setup();
    await renderWith(remembered);
    await screen.findByText('analogias funcionam');

    await user.click(screen.getByRole('button', { name: 'Forget: analogias funcionam' }));

    const alert = await screen.findByRole('alert');
    expect(alert).not.toHaveTextContent('network down');
    expect(screen.getByText('analogias funcionam')).toBeInTheDocument();
  });
});
