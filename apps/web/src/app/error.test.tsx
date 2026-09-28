// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import ErrorBoundary from './error';

describe('ErrorBoundary', () => {
  it('logs the error once and offers a retry that calls reset', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    const reset = vi.fn();
    const error = Object.assign(new Error('boom'), { digest: 'abc' });
    const user = userEvent.setup();

    render(<ErrorBoundary error={error} reset={reset} />);

    expect(consoleError).toHaveBeenCalledWith(error);
    expect(screen.getByRole('link', { name: /back to home/i })).toHaveAttribute('href', '/');

    await user.click(screen.getByRole('button', { name: /try again/i }));
    expect(reset).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/abc/)).toBeInTheDocument();

    consoleError.mockRestore();
  });

  it('offers to report it, as a bug, with the reference already written', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    const error = Object.assign(new Error('boom'), { digest: 'abc' });
    const user = userEvent.setup();

    render(<ErrorBoundary error={error} reset={vi.fn()} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /report this/i }));

    expect(screen.getByRole('dialog', { name: /tell us what happened/i })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Bug' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByLabelText('Your message')).toHaveValue(
      'This page broke. Reference abc\n\n',
    );

    consoleError.mockRestore();
  });
});
