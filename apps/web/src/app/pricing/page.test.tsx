// @vitest-environment jsdom
import { render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import PricingPage from './page';

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: { plans: vi.fn().mockResolvedValue([]) } };
});

afterEach(() => {
  delete window.plausible;
});

describe('PricingPage', () => {
  it('counts a view of the plans, with no props', async () => {
    const plausible = vi.fn();
    window.plausible = plausible;

    render(<PricingPage />);

    await waitFor(() => expect(plausible).toHaveBeenCalledWith('pricing_viewed', undefined));
  });
});
