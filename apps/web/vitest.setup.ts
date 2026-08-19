import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

import '@testing-library/jest-dom/vitest';

// Vitest has no built-in per-test teardown for React Testing Library the way
// Jest's environment does — without this, an unmounted render from a
// previous test stays in the DOM and the next one queries against both.
afterEach(cleanup);
