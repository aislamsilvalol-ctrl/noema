import { describe, expect, it } from 'vitest';

import { config as middlewareConfig } from '@/middleware';
import { GUARDED_PREFIXES, guardRedirect, isGuardedPath, safeNextPath } from './route-guard';

describe('isGuardedPath', () => {
  it('guards the authenticated areas and their subtrees', () => {
    for (const path of [
      '/today',
      '/chat',
      '/review',
      '/library',
      '/progress',
      '/graph',
      '/mistakes',
      '/goals',
      '/explain',
      '/socratic',
      '/notebooks/abc/professor',
      '/learn/new',
      '/settings',
      '/admin/sabelia',
    ]) {
      expect(isGuardedPath(path), path).toBe(true);
    }
  });

  it('leaves public pages, the API and static files alone', () => {
    for (const path of [
      '/',
      '/login',
      '/forgot-password',
      '/reset-password',
      '/privacy',
      '/terms',
      '/api/v1/auth/login',
      '/brand/mino.png',
      '/todayish', // a prefix match is not a subtree
    ]) {
      expect(isGuardedPath(path), path).toBe(false);
    }
  });
});

describe('guardRedirect', () => {
  it('sends a signed-out visit to /login with the page it wanted', () => {
    expect(
      guardRedirect({
        pathname: '/notebooks/abc',
        search: '?tab=notes',
        hasSession: false,
      }),
    ).toBe('/login?next=%2Fnotebooks%2Fabc%3Ftab%3Dnotes');
  });

  it('lets a session through, and every public path', () => {
    expect(guardRedirect({ pathname: '/today', hasSession: true })).toBeNull();
    expect(guardRedirect({ pathname: '/privacy', hasSession: false })).toBeNull();
  });

  it('stands aside in demo mode, where there is no cookie by design', () => {
    expect(guardRedirect({ pathname: '/today', hasSession: false, demo: true })).toBeNull();
  });
});

describe('safeNextPath', () => {
  it('accepts a path on this origin, with its query', () => {
    expect(safeNextPath('/notebooks/abc?tab=notes')).toBe('/notebooks/abc?tab=notes');
  });

  it('refuses anything that could leave the origin or loop back', () => {
    for (const raw of [
      null,
      '',
      'https://evil.example/',
      '//evil.example',
      '/\\evil.example',
      'javascript:alert(1)',
      '/login',
      '/login?next=%2Ftoday',
    ]) {
      expect(safeNextPath(raw), String(raw)).toBeNull();
    }
  });
});

describe('middleware matcher', () => {
  it('covers exactly the guarded prefixes', () => {
    const matched = middlewareConfig.matcher.map((pattern) => pattern.replace(/\/:path\*$/, ''));
    expect(matched).toEqual([...GUARDED_PREFIXES]);
  });
});
