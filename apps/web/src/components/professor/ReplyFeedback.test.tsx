// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ReplyFeedback } from './ReplyFeedback';

const { rateReply } = vi.hoisted(() => ({ rateReply: vi.fn().mockResolvedValue(undefined) }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: { ...actual.api, rateReply } };
});

describe('ReplyFeedback', () => {
  it('sends the verdict and lets a second tap change it', async () => {
    const user = userEvent.setup();
    render(<ReplyFeedback sessionId="s-1" />);

    await user.click(screen.getByRole('button', { name: 'It did not help' }));
    expect(rateReply).toHaveBeenLastCalledWith('s-1', false);
    expect(screen.getByRole('button', { name: 'It did not help' })).toHaveAttribute('aria-pressed', 'true');

    await user.click(screen.getByRole('button', { name: 'It helped' }));
    expect(rateReply).toHaveBeenLastCalledWith('s-1', true);
    expect(screen.getByText(/Mino takes note/)).toBeInTheDocument();
  });
});
