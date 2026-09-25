import { describe, expect, it } from 'vitest';

import { ApiError } from '@/lib/api';
import { passwordError } from './SecuritySection';

function problem(type: string, status = 403) {
  return new ApiError({ type, title: 't', status, detail: 'd' });
}

describe('passwordError', () => {
  it('says the password is wrong only when the server says exactly that', () => {
    expect(passwordError(problem('https://noema.dev/problems/wrong-password'), 'wrong', 'other')).toBe(
      'wrong',
    );
  });

  it('does not blame the password for a refused CSRF token, which is also a 403', () => {
    expect(passwordError(problem('https://noema.dev/problems/forbidden'), 'wrong', 'other')).toBe(
      'other',
    );
  });
});
