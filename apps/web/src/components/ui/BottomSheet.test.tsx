// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { BottomSheet } from './BottomSheet';

function sheet(open: boolean, onClose = vi.fn()) {
  return render(
    <BottomSheet open={open} onClose={onClose} title="Actions" closeLabel="Close">
      <button type="button">Explain it simpler</button>
    </BottomSheet>,
  );
}

describe('BottomSheet', () => {
  it('draws nothing while closed', () => {
    sheet(false);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('is a labelled modal dialog that takes focus and locks the page behind it', () => {
    sheet(true);
    expect(screen.getByRole('dialog', { name: 'Actions' })).toHaveAttribute('aria-modal', 'true');
    expect(document.activeElement).toHaveTextContent('Close');
    expect(document.body.style.overflow).toBe('hidden');
  });

  it('closes on Escape, on the close button and on the backdrop', () => {
    const onClose = vi.fn();
    sheet(true, onClose);
    fireEvent.keyDown(window, { key: 'Escape' });
    fireEvent.click(screen.getAllByRole('button', { name: 'Close' })[1]!);
    fireEvent.click(screen.getAllByRole('button', { name: 'Close' })[0]!);
    expect(onClose).toHaveBeenCalledTimes(3);
  });
});
