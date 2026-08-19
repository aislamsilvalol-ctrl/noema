import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

const dirname = path.dirname(fileURLToPath(import.meta.url));

// Vitest doesn't read tsconfig.json's "paths" on its own — Next's own build
// does, which is why `@/lib/api` compiles today with no vitest config at all
// and would fail to resolve the moment a test tried to import it.
export default defineConfig({
  // tsconfig.json sets "jsx": "preserve" because Next's own SWC compiler does
  // the JSX transform; esbuild does not infer "use the automatic runtime"
  // from that the way Next does, and falls back to the classic one, which
  // needs `React` in scope — this file has no such import, by design.
  esbuild: {
    jsx: 'automatic',
  },
  resolve: {
    alias: {
      '@': path.resolve(dirname, './src'),
    },
  },
  test: {
    // Default stays plain Node — most of this suite is pure logic with no DOM
    // (src/lib/*.test.ts) and jsdom costs real time on every one of them for
    // nothing. A component test opts in per file with a leading
    // `// @vitest-environment jsdom` comment instead of paying that globally.
    setupFiles: ['./vitest.setup.ts'],
  },
});
