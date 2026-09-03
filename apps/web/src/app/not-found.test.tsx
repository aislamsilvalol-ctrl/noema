// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import NotFound from './not-found';

const { meFn } = vi.hoisted(() => ({ meFn: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: { ...actual.api, me: meFn } };
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('NotFound', () => {
  it('offers to sign in for a signed-out visitor, never leaving them stuck', async () => {
    meFn.mockRejectedValue(new Error('not signed in'));
    render(<NotFound />);

    await waitFor(() => expect(meFn).toHaveBeenCalled());
    expect(screen.getByRole('link', { name: /back to home/i })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: /sign in/i })).toHaveAttribute('href', '/login');
    expect(screen.queryByRole('link', { name: /continue learning/i })).not.toBeInTheDocument();
  });

  it('offers to continue learning for a signed-in visitor, straight to /chat', async () => {
    meFn.mockResolvedValue({ id: 'u-1', email: 'a@example.com' });
    render(<NotFound />);

    const cta = await screen.findByRole('link', { name: /continue learning/i });
    expect(cta).toHaveAttribute('href', '/chat');
    expect(screen.queryByRole('link', { name: /^sign in$/i })).not.toBeInTheDocument();
  });
});
