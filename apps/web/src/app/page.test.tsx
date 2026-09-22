// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import LandingPage from './page';

vi.mock('@/components/LanguageSwitcher', () => ({
  LanguageSwitcher: () => null,
}));

// jsdom has no matchMedia or IntersectionObserver: every media query is "no
// match" and the observers never mount — the page must render fully on it.
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

vi.setConfig({ testTimeout: 20_000 });
afterEach(() => vi.clearAllMocks());
meFn.mockRejectedValue(new Error('not signed in'));

describe('LandingPage', () => {
  it('opens on the valley with one line, one sub-line and one action', () => {
    render(<LandingPage />);
    expect(screen.getAllByText('Learn anything.').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('An intelligence that learns how you learn.')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Start learning' })[0]).toHaveAttribute('href', '/login?mode=register');
    expect(screen.getByRole('link', { name: 'Log in' })).toHaveAttribute('href', '/login');
  });

  it('switches to "Continue" once a session is confirmed', async () => {
    meFn.mockResolvedValueOnce({ id: 'u1', email: 'x@y.z' });
    render(<LandingPage />);
    await waitFor(() => expect(screen.getAllByRole('link', { name: 'Continue' })[0]).toHaveAttribute('href', '/today'));
  });

  it('tells the story in order: statement, one question, map, trail', () => {
    render(<LandingPage />);
    const order = [
      'Most platforms teach everyone the same way.',
      'A teacher with a plan, not a chat with a topic.',
      'What you learn becomes territory.',
      'The more you learn, the better it learns to teach you.',
    ];
    const positions = order.map((text) => screen.getByText((content) => content.startsWith(text)));
    for (let i = 1; i < positions.length; i++) {
      expect(positions[i - 1]!.compareDocumentPosition(positions[i]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it('calls the real tutor from the teaching screen, and says so', async () => {
    demoFn.mockImplementation(async (_subject: string, callbacks: { onToken: (t: string) => void }) => {
      callbacks.onToken('Start with the slip.');
    });
    const user = userEvent.setup();
    render(<LandingPage />);
    await user.type(screen.getByLabelText('What do you want to learn?'), 'Freud');
    await user.click(screen.getByRole('button', { name: /teach me/i }));
    await screen.findByText(/Start with the slip/);
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

  it('keeps the landscapes decorative and the legal links real', () => {
    render(<LandingPage />);
    for (const img of document.querySelectorAll('picture img')) {
      expect(img).toHaveAttribute('alt', '');
      expect(img).toHaveAttribute('width');
    }
    expect(screen.getByRole('img', { name: /The unconscious: mastered/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Privacy' })).toHaveAttribute('href', '/privacy');
    expect(screen.getByRole('link', { name: 'Terms' })).toHaveAttribute('href', '/terms');
    expect(screen.getAllByRole('link', { name: 'Pricing' })[0]).toHaveAttribute('href', '/pricing');
  });
});
