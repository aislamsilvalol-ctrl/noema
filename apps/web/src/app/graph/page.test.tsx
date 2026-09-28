// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import GraphPage from './page';

const push = vi.fn();
const router = { push };
vi.mock('next/navigation', () => ({
  useRouter: () => router,
  usePathname: () => '/graph',
}));

vi.mock('@/components/Shell', () => ({
  Shell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// The character needs a canvas and the graph needs a layout engine; neither
// is what the empty state is about.
vi.mock('@/components/mino/Mino', () => ({
  Mino: () => null,
}));
vi.mock('@/components/ConceptGraph', () => ({
  ConceptGraph: () => null,
}));

const calls = vi.hoisted(() => ({
  concepts: vi.fn(),
  mastery: vi.fn(),
  journeys: vi.fn(),
  conceptGraph: vi.fn(),
}));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: calls };
});

afterEach(() => {
  for (const fn of Object.values(calls)) fn.mockReset();
});

const journey = { id: 'j-1', subject: 'Cardiology', status: 'active' };

describe('GraphPage', () => {
  it('sends a learner with a journey but no graph to their course map', async () => {
    calls.concepts.mockResolvedValue([]);
    calls.mastery.mockResolvedValue([]);
    calls.journeys.mockResolvedValue([journey]);
    render(<GraphPage />);

    await screen.findByText('The graph is still empty.');
    expect(screen.getByRole('link', { name: 'Your course map' })).toHaveAttribute(
      'href',
      '/progress',
    );
    expect(screen.queryByText('No concepts yet.')).not.toBeInTheDocument();
    // Conversation mastery is asked for: this learner has no other kind.
    expect(calls.mastery).toHaveBeenCalledWith(false, true);
  });

  it('invites a learner with nothing at all to start', async () => {
    calls.concepts.mockResolvedValue([]);
    calls.mastery.mockResolvedValue([]);
    calls.journeys.mockResolvedValue([]);
    render(<GraphPage />);

    await screen.findByText('No concepts yet.');
    expect(screen.getByRole('link', { name: 'Start learning' })).toHaveAttribute(
      'href',
      '/learn/new',
    );
  });

  it('still draws the graph when the journeys call fails', async () => {
    calls.concepts.mockResolvedValue([
      { id: 'c-1', name: 'P wave', status: 'active', aliases: [], definition: null },
    ]);
    calls.mastery.mockResolvedValue([]);
    calls.journeys.mockRejectedValue(new Error('down'));
    calls.conceptGraph.mockResolvedValue({ nodes: [], edges: [] });
    render(<GraphPage />);

    expect(await screen.findByRole('button', { name: 'P wave' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
