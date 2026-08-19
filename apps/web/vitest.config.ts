import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

const dirname = path.dirname(fileURLToPath(import.meta.url));

// Vitest doesn't read tsconfig.json's "paths" on its own — Next's own build
// does, which is why `@/lib/api` compiles today with no vitest config at all
// and would fail to resolve the moment a test tried to import it.
export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(dirname, './src'),
    },
  },
});
