// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Button } from './Button';

describe('Button', () => {
  it('keeps every size at least 44px on both axes', () => {
    const { rerender } = render(<Button size="sm">Save</Button>);
    const button = screen.getByRole('button', { name: 'Save' });
    expect(button.className).toContain('min-h-11');
    expect(button.className).toContain('min-w-11');

    rerender(<Button size="md">Save</Button>);
    expect(screen.getByRole('button', { name: 'Save' }).className).toContain('min-h-11');

    rerender(<Button size="lg">Save</Button>);
    expect(screen.getByRole('button', { name: 'Save' }).className).toContain('min-h-12');
  });
});
