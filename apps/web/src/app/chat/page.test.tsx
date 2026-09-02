// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ChatPage from './page';
import type { ChatCallbacks } from '@/lib/api';

vi.mock('next/navigation', () => ({
  usePathname: () => '/chat',
}));

vi.mock('@/components/Shell', () => ({
  Shell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const { professorChat } = vi.hoisted(() => ({ professorChat: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, professorChat };
});

afterEach(() => {
  professorChat.mockReset();
});

describe('ChatPage', () => {
  it('shows the empty lede before any message is sent, no notebook required', () => {
    render(<ChatPage />);
    expect(
      screen.getByText(/what do you want to learn\? ask anything/i),
    ).toBeInTheDocument();
  });

  it('calls professorChat with no notebook_id at all -- the actual regression this page exists to fix', async () => {
    professorChat.mockImplementation(
      async (_body: unknown, callbacks: ChatCallbacks) => {
        callbacks.onIntent?.('explain');
        callbacks.onToken('Psychology is the study of mind and behavior.');
        callbacks.onDone?.({ prompt_tokens: 10, completion_tokens: 5 });
      },
    );
    const user = userEvent.setup();
    render(<ChatPage />);

    const textarea = screen.getByPlaceholderText(/what do you want to learn/i);
    await user.click(textarea);
    await user.paste('Quero aprender psicologia');
    await user.click(screen.getByRole('button', { name: /^send$/i }));

    await screen.findByText('Psychology is the study of mind and behavior.');
    expect(professorChat).toHaveBeenCalledWith(
      { messages: [{ role: 'user', content: 'Quero aprender psicologia' }] },
      expect.anything(),
      expect.anything(),
    );
    // The specific bug: a stray `notebook_id` key (even `undefined`) would
    // still serialize wrong for some callers -- assert the key is absent, not
    // just falsy.
    const [body] = professorChat.mock.calls[0] as [Record<string, unknown>];
    expect('notebook_id' in body).toBe(false);
  });

  it('shows the monthly limit banner and drops the pending turn when blocked', async () => {
    professorChat.mockImplementation(
      async (_body: unknown, callbacks: ChatCallbacks) => {
        callbacks.onBlocked?.({ used_units: 200, limit_units: 200 });
      },
    );
    const user = userEvent.setup();
    render(<ChatPage />);

    await user.type(screen.getByPlaceholderText(/what do you want to learn/i), 'Hi');
    await user.click(screen.getByRole('button', { name: /^send$/i }));

    await screen.findByText(/used this month's noema time/i);
    expect(screen.queryByText('NOEMA')).not.toBeInTheDocument();
  });

  it('surfaces an error and leaves the composer usable when the stream fails', async () => {
    professorChat.mockImplementation(
      async (_body: unknown, callbacks: ChatCallbacks) => {
        callbacks.onError?.('Noema is unavailable.');
      },
    );
    const user = userEvent.setup();
    render(<ChatPage />);

    await user.type(screen.getByPlaceholderText(/what do you want to learn/i), 'Hi');
    await user.click(screen.getByRole('button', { name: /^send$/i }));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Noema is unavailable.'),
    );
    expect(screen.getByRole('button', { name: /^send$/i })).toBeEnabled();
  });
});
