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
  it('opens on the terraces with one line, one sub-line and one action', () => {
    render(<LandingPage />);
    expect(screen.getAllByText('Learn anything.')).toHaveLength(1);
    expect(screen.getByText('An AI teacher that finds out what you already know and teaches you the rest.')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Start learning' })[0]).toHaveAttribute('href', '/login?mode=register');
    expect(screen.getByRole('link', { name: 'Log in' })).toHaveAttribute('href', '/login');
  });

  it('switches to "Continue" once a session is confirmed', async () => {
    meFn.mockResolvedValueOnce({ id: 'u1', email: 'x@y.z' });
    render(<LandingPage />);
    await waitFor(() => expect(screen.getAllByRole('link', { name: 'Continue' })[0]).toHaveAttribute('href', '/today'));
  });

  it('tells the story in order: the lesson, why it works, ADHD mode, the map, the close', () => {
    render(<LandingPage />);
    const order = [
      'It asks before it explains.',
      'It knows where you are.',
      'It changes its approach.',
      'You actually progress.',
      'Five minutes. One thing.',
      'What you learn becomes territory.',
      'Start with what you want to know.',
    ];
    const positions = order.map((text) => screen.getByText((content) => content.startsWith(text)));
    for (let i = 1; i < positions.length; i++) {
      expect(positions[i - 1]!.compareDocumentPosition(positions[i]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it('shows the finished lesson when it cannot play it: the mistake, the new approach, the concept that firmed up', () => {
    render(<LandingPage />);
    // jsdom has no IntersectionObserver: the demo renders its end state.
    expect(screen.getAllByText(/Not quite\. Speed is distance ÷ time/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/new approach · a concrete example/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Firmed up: average speed').length).toBeGreaterThan(0);
    expect(screen.getByText('A staged lesson. Yours starts from what you already know.')).toBeInTheDocument();
    // ADHD mode makes no medical claim.
    expect(screen.getByText('Made for minds that wander. Not a treatment.')).toBeInTheDocument();
  });

  it('pins the scenes only when motion is welcome', () => {
    const { container, unmount } = render(<LandingPage />);
    expect(container.querySelector('main')).toHaveClass('v6-motion');
    unmount();
    const original = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('reduce'),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    try {
      const view = render(<LandingPage />);
      expect(view.container.querySelector('main')).not.toHaveClass('v6-motion');
    } finally {
      window.matchMedia = original;
    }
  });

  it('sends a question typed in the lesson to the real tutor, and says so', async () => {
    demoFn.mockImplementation(async (_subject: string, callbacks: { onToken: (t: string) => void }) => {
      callbacks.onToken('Start with the slip.');
    });
    const user = userEvent.setup();
    render(<LandingPage />);
    await user.type(screen.getByLabelText('Your turn: ask about any subject'), 'Freud');
    await user.click(screen.getByRole('button', { name: 'Ask' }));
    await screen.findByText(/Start with the slip/);
    expect(demoFn).toHaveBeenCalledWith('Freud', expect.anything(), expect.anything());
    expect(screen.getByText(/That was the real tutor/)).toBeInTheDocument();
  });

  it('falls back to the written sample when the tutor is unavailable, and says so', async () => {
    demoFn.mockRejectedValue(new Error('503'));
    const user = userEvent.setup();
    render(<LandingPage />);
    await user.type(screen.getByLabelText('Your turn: ask about any subject'), 'Italian');
    await user.click(screen.getByRole('button', { name: 'Ask' }));
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
