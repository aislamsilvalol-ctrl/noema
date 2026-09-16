// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CommandPalette } from '@/components/CommandPalette';
import { en } from '@/locales/en';
import { PREFILL_KEY, takePrefill } from '@/lib/prefill';

const push = vi.fn();
let pathname = '/today';
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  usePathname: () => pathname,
}));

afterEach(() => {
  push.mockClear();
  pathname = '/today';
  window.sessionStorage.removeItem(PREFILL_KEY);
});

describe('CommandPalette', () => {
  it('renders nothing when closed', () => {
    const { container } = render(<CommandPalette open={false} onClose={() => {}} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('lists every command when open with an empty query', () => {
    render(<CommandPalette open onClose={() => {}} />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getAllByRole('button').length).toBeGreaterThan(1);
  });

  it('filters commands as you type, case-insensitively', async () => {
    const user = userEvent.setup();
    render(<CommandPalette open onClose={() => {}} />);

    await user.type(screen.getByRole('textbox'), 'LIBRARY');

    const options = screen.getAllByRole('button');
    expect(options).toHaveLength(1);
    expect(options[0]).toHaveTextContent(/library/i);
  });

  it('shows a no-match message rather than an empty list', async () => {
    const user = userEvent.setup();
    render(<CommandPalette open onClose={() => {}} />);

    await user.type(screen.getByRole('textbox'), 'zzz-nothing-matches-this');

    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.getByText(/no/i)).toBeInTheDocument();
  });

  it('runs the matched command and closes on Enter', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<CommandPalette open onClose={onClose} />);

    await user.type(screen.getByRole('textbox'), 'library');
    await user.keyboard('{Enter}');

    expect(push).toHaveBeenCalledWith('/library');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes without running anything on Escape', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<CommandPalette open onClose={onClose} />);

    await user.click(screen.getByRole('textbox'));
    await user.keyboard('{Escape}');

    expect(push).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('moves the selection with arrow keys, clamped to the list', async () => {
    const user = userEvent.setup();
    render(<CommandPalette open onClose={() => {}} />);

    // "Review due cards" and "Review my mistakes" both match, in that order,
    // and — unlike most pairs in this list — go to different places, so which
    // one ran after moving the selection is actually observable.
    await user.type(screen.getByRole('textbox'), 'review');
    expect(screen.getAllByRole('button')).toHaveLength(2);

    await user.keyboard('{ArrowUp}'); // already first — must clamp, not wrap or throw
    await user.keyboard('{ArrowDown}{Enter}');

    expect(push).toHaveBeenCalledWith('/mistakes');
    expect(push).toHaveBeenCalledTimes(1);
  });

  it('runs a command on click', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<CommandPalette open onClose={onClose} />);

    await user.type(screen.getByRole('textbox'), 'library');
    await user.click(screen.getByRole('button'));

    expect(push).toHaveBeenCalledWith('/library');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes on a click outside the panel, not inside it', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<CommandPalette open onClose={onClose} />);

    await user.click(screen.getByRole('dialog'));
    expect(onClose).toHaveBeenCalledTimes(1);

    onClose.mockClear();
    await user.click(screen.getByRole('textbox'));
    expect(onClose).not.toHaveBeenCalled();
  });

  it('lists Home once, not as "today" and again as "session"', async () => {
    const user = userEvent.setup();
    render(<CommandPalette open onClose={() => {}} />);

    await user.type(screen.getByRole('textbox'), 'today');

    expect(screen.getAllByRole('button')).toHaveLength(1);
  });

  it('carries "Explain differently" into the Professor, prefilled, from outside a lesson', async () => {
    const user = userEvent.setup();
    render(<CommandPalette open onClose={() => {}} />);

    await user.type(screen.getByRole('textbox'), en.professor.reframe.button);
    await user.keyboard('{Enter}');

    expect(push).toHaveBeenCalledWith('/chat');
    expect(takePrefill()).toEqual({
      text: en.professor.reframe.messages.simpler,
      autosend: false,
    });
  });

  it('carries "Guide me" the same way', async () => {
    const user = userEvent.setup();
    render(<CommandPalette open onClose={() => {}} />);

    await user.type(screen.getByRole('textbox'), en.professor.reframe.guide);
    await user.keyboard('{Enter}');

    expect(push).toHaveBeenCalledWith('/chat');
    expect(takePrefill()?.text).toBe(en.professor.reframe.guideMessage);
  });

  it('leaves the lesson moves out on a lesson page, where the composer has them', async () => {
    pathname = '/notebooks/abc/professor';
    const user = userEvent.setup();
    render(<CommandPalette open onClose={() => {}} />);

    await user.type(screen.getByRole('textbox'), en.professor.reframe.guide);

    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });

  it('resets the query each time it opens', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<CommandPalette open onClose={() => {}} />);

    await user.type(screen.getByRole('textbox'), 'stale query');
    expect(screen.getByRole('textbox')).toHaveValue('stale query');

    rerender(<CommandPalette open={false} onClose={() => {}} />);
    rerender(<CommandPalette open onClose={() => {}} />);

    expect(screen.getByRole('textbox')).toHaveValue('');
  });
});
