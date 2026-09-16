// @vitest-environment jsdom
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { bankFor } from '@/components/landing/v4/subjects';
import LandingPage from './page';

vi.mock('@/components/LanguageSwitcher', () => ({
  LanguageSwitcher: () => null,
}));

// jsdom has no matchMedia or IntersectionObserver: every media query is "no
// match" and the scroll observer never mounts, which is the reduced-motion
// path — the page must render fully on it.
window.matchMedia = vi.fn().mockImplementation((query: string) => ({
  matches: false,
  media: query,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  addListener: vi.fn(),
  removeListener: vi.fn(),
  dispatchEvent: vi.fn(),
}));

const { meFn, demoFn, plansFn } = vi.hoisted(() => ({ meFn: vi.fn(), demoFn: vi.fn(), plansFn: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: { me: meFn, plans: plansFn }, demoTeach: demoFn };
});

// The whole landing renders per test; under a parallel run 5 s is not enough.
vi.setConfig({ testTimeout: 20_000 });

afterEach(() => vi.clearAllMocks());
meFn.mockRejectedValue(new Error('not signed in'));
plansFn.mockRejectedValue(new Error('no billing'));

describe('LandingPage', () => {
  it('opens with the one line and the one question, and offers to sign in', async () => {
    render(<LandingPage />);
    expect(screen.getAllByText('Learn like no one else.').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('An intelligence that learns how you learn.')).toBeInTheDocument();
    expect(screen.getByLabelText('What do you want to learn?')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Start' })).toHaveAttribute('href', '/login?mode=register');
    expect(screen.getByRole('link', { name: 'Log in' })).toHaveAttribute('href', '/login');
  });

  it('switches to "Continue learning" once a session is confirmed', async () => {
    meFn.mockResolvedValueOnce({ id: 'u1', email: 'x@y.z' });
    render(<LandingPage />);
    await waitFor(() =>
      expect(screen.getAllByRole('link', { name: 'Continue learning' })[0]).toHaveAttribute('href', '/today'),
    );
  });

  it('streams the real tutor reply for a typed subject and carries it into the modes demo', async () => {
    demoFn.mockImplementation(async (_subject: string, callbacks: { onToken: (t: string) => void }) => {
      callbacks.onToken('Start with the slip. ');
      callbacks.onToken('Which part did the work?');
    });
    const user = userEvent.setup();
    render(<LandingPage />);

    await user.type(screen.getByLabelText('What do you want to learn?'), 'Psychology according to Freud');
    await user.click(screen.getByRole('button', { name: /teach me/i }));

    // The reply is shown in the hero and in the modes demo (Normal rhythm).
    await waitFor(() => expect(screen.getAllByText(/Which part did the work\?/)).toHaveLength(2));
    expect(demoFn).toHaveBeenCalledWith('Psychology according to Freud', expect.anything(), expect.anything());
    expect(screen.getByText(/That was the real tutor/)).toBeInTheDocument();
  });

  it('falls back to the written sample when the tutor is unavailable, and says so', async () => {
    demoFn.mockRejectedValue(new Error('503'));
    const user = userEvent.setup();
    render(<LandingPage />);

    await user.type(screen.getByLabelText('What do you want to learn?'), 'Italian');
    await user.click(screen.getByRole('button', { name: /teach me/i }));

    await screen.findByText(/The tutor is busy right now/);
    expect(screen.getAllByText(/Ragazzo/).length).toBeGreaterThan(0);
  });

  it('tells the lesson in four beats, and a wrong answer moves what it knows', async () => {
    demoFn.mockRejectedValue(new Error('503'));
    const user = userEvent.setup();
    render(<LandingPage />);
    for (const id of ['learn-1', 'learn-2', 'learn-3', 'learn-4']) {
      expect(document.querySelector(`[data-section="${id}"]`)).not.toBeNull();
    }
    expect(screen.getByText('Then we will not start with Freud.')).toBeInTheDocument();

    await user.type(screen.getByLabelText('What do you want to learn?'), 'JavaScript');
    await user.click(screen.getByRole('button', { name: /teach me/i }));
    await screen.findByText(/The tutor is busy right now/);

    const bank = bankFor('JavaScript', 'en');
    const options = within(screen.getByRole('group', { name: bank.question })).getAllByRole('button');
    const wrong = options.findIndex((_, index) => index !== bank.correct);
    await user.click(options[wrong]!);
    await user.click(screen.getByRole('button', { name: 'Sure' }));
    expect(screen.getByText(/Almost\. Notice this difference/)).toBeInTheDocument();
    expect(screen.getByText(/reordered after your answer/)).toBeInTheDocument();
  });

  it('explains differently on demand, with the modes labelled', async () => {
    const user = userEvent.setup();
    render(<LandingPage />);
    await user.click(screen.getByRole('button', { name: 'Analogy' }));
    expect(screen.getByText(/iceberg/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Step by step' }));
    expect(screen.getByText(/learning to read those signs/)).toBeInTheDocument();
  });

  it('shows pricing only from the API, and hides it otherwise', async () => {
    const { unmount } = render(<LandingPage />);
    await waitFor(() => expect(plansFn).toHaveBeenCalled());
    expect(document.querySelector('#pricing')).toBeNull();
    unmount();

    plansFn.mockResolvedValueOnce([
      { plan: 'free', monthly_price_cents: 0, monthly_ai_units: 60 },
      { plan: 'pro', monthly_price_cents: 2990, monthly_ai_units: 900 },
    ]);
    render(<LandingPage />);
    await screen.findByText('Pro');
    expect(screen.getByText('Free', { selector: 'span' })).toBeInTheDocument();
    expect(screen.getByText(/R\$/)).toBeInTheDocument();
    expect(screen.getByText('900 AI units per month')).toBeInTheDocument();
  });

  it('keeps the map, the questions and the legal links real', () => {
    render(<LandingPage />);
    expect(screen.getByRole('img', { name: /The unconscious: mastered/ })).toBeInTheDocument();
    expect(screen.getByText('Is NOEMA a chatbot?')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Privacy' })).toHaveAttribute('href', '/privacy');
    expect(screen.getByRole('link', { name: 'Terms' })).toHaveAttribute('href', '/terms');
    for (const id of ['ask', 'different', 'meet', 'explain', 'map', 'modes', 'mastery', 'faq', 'close']) {
      expect(document.querySelector(`[data-section="${id}"]`)).not.toBeNull();
    }
  });

  it('keeps Mino decorative: the figures are stills until the stage is ready, never announced', () => {
    render(<LandingPage />);
    const stages = document.querySelectorAll('[data-mino-stage]');
    expect(stages.length).toBeGreaterThanOrEqual(2);
    for (const img of document.querySelectorAll('[data-mino-stage] img')) {
      expect(img).toHaveAttribute('aria-hidden', 'true');
      expect(img).toHaveAttribute('alt', '');
    }
  });
});
