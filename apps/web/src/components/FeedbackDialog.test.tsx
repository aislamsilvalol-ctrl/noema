// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FeedbackDialog } from './FeedbackDialog';
import { ApiError } from '@/lib/api';

const { sendFeedback } = vi.hoisted(() => ({ sendFeedback: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: { ...actual.api, sendFeedback } };
});

describe('FeedbackDialog', () => {
  beforeEach(() => {
    sendFeedback.mockReset();
    window.history.replaceState(null, '', '/review');
  });

  it('sends the kind, the message and the page, then says thank you', async () => {
    sendFeedback.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<FeedbackDialog open onClose={() => undefined} />);

    expect(screen.getByRole('radio', { name: 'Bug' })).toHaveAttribute('aria-checked', 'true');
    await user.click(screen.getByRole('radio', { name: 'Bad answer' }));
    await user.type(screen.getByLabelText('Your message'), '  Mino said 2 + 2 = 5  ');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    expect(sendFeedback).toHaveBeenCalledWith({
      kind: 'ai_quality',
      message: 'Mino said 2 + 2 = 5',
      page: '/review',
    });
    expect(await screen.findByText('Thank you — we read everything.')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('does not send an empty message', async () => {
    const user = userEvent.setup();
    render(<FeedbackDialog open onClose={() => undefined} />);

    await user.type(screen.getByLabelText('Your message'), '   ');

    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    expect(sendFeedback).not.toHaveBeenCalled();
  });

  it('keeps the form and says why when sending fails', async () => {
    sendFeedback.mockRejectedValue(
      new ApiError({ type: 'about:blank', title: 'Too many', status: 429, detail: '' }),
    );
    const user = userEvent.setup();
    render(<FeedbackDialog open onClose={() => undefined} />);

    await user.type(screen.getByLabelText('Your message'), 'again');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/a lot for one hour/);
    expect(screen.getByLabelText('Your message')).toHaveValue('again');
  });

  it('starts from the kind and opening line the caller hands in', () => {
    render(
      <FeedbackDialog open onClose={() => undefined} kind="idea" message="A thought:" />,
    );

    expect(screen.getByRole('radio', { name: 'Idea' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByLabelText('Your message')).toHaveValue('A thought:');
  });
});
