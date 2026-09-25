// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import GlobalError from './global-error';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('GlobalError', () => {
  it('speaks the browser language and retries through reset', async () => {
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('pt-BR');
    const reset = vi.fn();
    const user = userEvent.setup();
    // It renders its own <html>/<body>: React 19 hoists those to the document's
    // own, so the page is rendered into the document, not a detached container.
    vi.spyOn(console, 'error').mockImplementation(() => {});

    render(<GlobalError error={Object.assign(new Error('boom'), { digest: 'd1' })} reset={reset} />, {
      container: document,
    });

    expect(screen.getByRole('heading', { name: /não conseguiu carregar/i })).toBeInTheDocument();
    expect(screen.getByText(/d1/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /tentar de novo/i }));
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it('falls back to English for any other language', () => {
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('de-DE');
    vi.spyOn(console, 'error').mockImplementation(() => {});

    render(<GlobalError error={new Error('boom')} reset={() => {}} />, {
      container: document,
    });

    expect(screen.getByRole('heading', { name: /could not load/i })).toBeInTheDocument();
  });
});
