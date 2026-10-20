// @vitest-environment jsdom
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Button } from './Button';

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.tsx$/.test(name) && !/\.test\.tsx$/.test(name) ? [path] : [];
  });
}

describe('Button', () => {
  it('lets a long label wrap inside the button instead of escaping it', () => {
    render(<Button>Continuar donde lo dejaste en Fundamentos de programación</Button>);
    const button = screen.getByRole('button');
    expect(button.className).not.toContain('whitespace-nowrap');
    expect(button.className).toContain('max-w-full');
    expect(button.className).toContain('[overflow-wrap:anywhere]');
    // Height is a floor, never a fixed size, so a second line has room.
    expect(button.className).toMatch(/\bmin-h-11\b/);
    expect(button.className).not.toMatch(/(^|\s)h-\d/);
  });

  it('is the rule everywhere: no screen pins a translated label to one line', () => {
    const root = join(__dirname, '..', '..');
    const offenders = sources(root)
      .filter((path) => !path.includes('/landing/') && !path.includes('/admin/'))
      .filter((path) => readFileSync(path, 'utf8').includes('whitespace-nowrap'))
      .map((path) => path.slice(root.length + 1));
    expect(offenders).toEqual([]);
  });
});
