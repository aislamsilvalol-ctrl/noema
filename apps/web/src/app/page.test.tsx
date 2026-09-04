// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

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

const { meFn, demoFn } = vi.hoisted(() => ({ meFn: vi.fn(), demoFn: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: { me: meFn }, demoTeach: demoFn };
});

afterEach(() => vi.clearAllMocks());
meFn.mockRejectedValue(new Error('not signed in'));

describe('LandingPage', () => {
  it('asks the one question first and offers to sign in to a signed-out visitor', async () => {
    render(<LandingPage />);
    expect(screen.getByLabelText('What do you want to learn?')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Start' })).toHaveAttribute('href', '/login');
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/login');
  });

  it('switches to "Continue learning" once a session is confirmed', async () => {
    meFn.mockResolvedValueOnce({ id: 'u1', email: 'x@y.z' });
    render(<LandingPage />);
    await waitFor(() =>
      expect(screen.getAllByRole('link', { name: 'Continue learning' })[0]).toHaveAttribute('href', '/chat'),
    );
  });

  it('streams the real tutor reply for a typed subject and labels it as the demo', async () => {
    demoFn.mockImplementation(async (_subject: string, callbacks: { onToken: (t: string) => void }) => {
      callbacks.onToken('Start with the slip. ');
      callbacks.onToken('Which part did the work?');
    });
    const user = userEvent.setup();
    render(<LandingPage />);

    await user.type(screen.getByLabelText('What do you want to learn?'), 'Psychology according to Freud');
    await user.click(screen.getByRole('button', { name: /teach me/i }));

    // The reply appears in the hero and again in the LEARN beat: one lesson, carried down.
    await waitFor(() => expect(screen.getAllByText(/Which part did the work\?/)).toHaveLength(2));
    expect(demoFn).toHaveBeenCalledWith('Psychology according to Freud', expect.anything(), expect.anything());
    expect(screen.getByText(/A real reply from the tutor/)).toBeInTheDocument();
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

  it('adapts practice to the subject and reacts to a wrong answer with the distinction, not a score', async () => {
    demoFn.mockRejectedValue(new Error('503'));
    const user = userEvent.setup();
    render(<LandingPage />);
    await user.type(screen.getByLabelText('What do you want to learn?'), 'JavaScript');
    await user.click(screen.getByRole('button', { name: /teach me/i }));
    await screen.findByText(/The tutor is busy right now/);

    await user.click(screen.getByRole('button', { name: '6' }));
    await user.click(screen.getByRole('button', { name: 'Certain' }));
    expect(screen.getByText(/Close\. Look at this difference/)).toBeInTheDocument();
    expect(screen.getByText(/returns a/)).toBeInTheDocument();
    expect(screen.getByText('Reordered after your answer')).toBeInTheDocument();
  });

  it('keeps Mino decorative and the legal links real', () => {
    render(<LandingPage />);
    for (const svg of document.querySelectorAll('svg.mino-rig')) {
      expect(svg).toHaveAttribute('aria-hidden', 'true');
    }
    expect(document.querySelectorAll('svg.mino-rig').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole('link', { name: 'Privacy' })).toHaveAttribute('href', '/privacy');
    expect(screen.getByRole('link', { name: 'Terms' })).toHaveAttribute('href', '/terms');
    for (const id of ['ask', 'learn', 'practice', 'adapt', 'remember', 'close']) {
      expect(document.querySelector(`[data-section="${id}"]`)).not.toBeNull();
    }
  });
});
