import { fileURLToPath } from 'node:url'

import base from '../../../../../../playwright.config.ts'

// Reuse the project's isolated API, source-copy policy and cleanup.
export default {
  ...base,
  testDir: '.',
  testMatch: /run-manifest\.browser\.mjs$/,
  globalTeardown: fileURLToPath(
    new URL('../../../../../../e2e/global-teardown.ts', import.meta.url),
  ),
}
