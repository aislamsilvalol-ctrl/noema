// @vitest-environment jsdom
import { render, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { Shell } from '@/components/Shell';
import { en } from '@/locales/en';

vi.mock('next/navigation', () => ({
  usePathname: () => '/today',
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/lib/api', () => ({
  api: { logout: vi.fn() },
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
      en.nav.home,
      en.nav.learn,
      en.nav.review,
      en.nav.notes,
      en.nav.progress,
      en.nav.goals,
      en.nav.settings,
    ]);
  });
});
