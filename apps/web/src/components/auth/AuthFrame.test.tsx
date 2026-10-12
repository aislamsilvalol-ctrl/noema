// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AuthFrame } from './AuthFrame';

vi.mock('@/components/mino/Mino', () => ({ Mino: () => null }));

describe('AuthFrame', () => {
  it('uses the small viewport so the keyboard does not resize the frame', () => {
    render(<AuthFrame aside="A quiet place to learn.">form</AuthFrame>);

    const main = screen.getByRole('main');
    expect(main.className).toContain('min-h-svh');
    expect(main.className).not.toContain('min-h-screen');
    expect(screen.getByLabelText(/language/i).className).toContain('min-h-11');
  });
});
