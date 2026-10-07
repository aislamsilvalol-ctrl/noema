// @vitest-environment jsdom
import { fireEvent, render, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { Shell } from '@/components/Shell';
import { en } from '@/locales/en';

vi.mock('next/navigation', () => ({
  usePathname: () => '/today',
  useRouter: () => ({ push: vi.fn() }),
}));

const updatePreferences = vi.hoisted(() =>
  vi.fn().mockResolvedValue({ learning_mode: 'normal', session_minutes: 7 }),
);
vi.mock('@/lib/api', () => ({
  api: {
    logout: vi.fn(),
    me: vi.fn().mockResolvedValue({ email_verified: true }),
    updatePreferences,
  },
}));

/** The desktop rail — the tab bar below `md` carries the same accessible name. */
function renderRail() {
  const { container } = render(<Shell>content</Shell>);
  const rail = container.querySelector('nav.noema-rail');
  if (!(rail instanceof HTMLElement)) throw new Error('rail not rendered');
  return rail;
}

describe('Shell navigation', () => {
  it('names five places, and Goals one level down', () => {
    const rail = renderRail();
    const labels = within(rail)
      .getAllByRole('link')
      .map((link) => link.textContent);

    expect(labels).toEqual([
      // The wordmark comes first; it links Home too.
      expect.any(String),
      // Modo TDAH: its own place, above the others.
      en.foco.name,
      en.nav.home,
      en.nav.learn,
      en.nav.review,
      en.nav.notes,
      en.nav.progress,
      en.nav.goals,
      en.nav.settings,
    ]);
  });

  it('puts Modo TDAH in the rail, linking to /foco', () => {
    const rail = renderRail();
    const entry = within(rail).getByRole('link', { name: en.foco.name });
    expect(entry).toHaveAttribute('href', '/foco');
  });

  it('keeps Modo TDAH two taps from anywhere on a phone: More, then the first item', () => {
    const { container } = render(<Shell>content</Shell>);
    const bar = container.querySelector('nav.noema-tabbar');
    if (!(bar instanceof HTMLElement)) throw new Error('tab bar not rendered');
    fireEvent.click(within(bar).getByRole('button', { name: en.nav.more }));
    const palette = within(document.body).getByRole('dialog', { name: en.palette.ariaLabel });
    const first = within(palette).getAllByRole('listitem')[0];
    expect(first?.textContent).toContain(en.foco.name);
  });

  it('turns Focus off in place instead of sending the learner to Settings', async () => {
    const { container } = render(<Shell focus>content</Shell>);
    const rail = container.querySelector('[data-focus-rail]');
    if (!(rail instanceof HTMLElement)) throw new Error('focus rail not rendered');
    expect(within(rail).queryByRole('link')).toBeNull();
    fireEvent.click(within(rail).getByRole('button', { name: en.nav.focusBack }));
    await waitFor(() =>
      expect(updatePreferences).toHaveBeenCalledWith({ learning_mode: 'normal' }),
    );
  });
});
