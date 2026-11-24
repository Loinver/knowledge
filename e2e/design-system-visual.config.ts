import { fileURLToPath } from 'node:url'

import { defineConfig } from '@playwright/test'

import config from '../playwright.config'

const sourceDir = process.env.KG_DESIGN_SOURCE_DIR
const servers = Array.isArray(config.webServer) ? config.webServer : []

// This evidence run keeps its isolated database for the matching after capture.
// The directory is removed explicitly after both phases; no developer DB is used.
export default defineConfig({
  ...config,
  testDir: fileURLToPath(new URL('./', import.meta.url)),
  testMatch: 'design-system-visual.browser.ts',
  globalTeardown: undefined,
  // A git-archive snapshot can render the before phase without touching the
  // working tree. Both phases still use the same isolated API and database.
  webServer: servers.map((server, index) =>
    sourceDir && index === 1 ? { ...server, cwd: `${sourceDir}/web` } : server,
  ),
  timeout: 240_000,
  use: { ...config.use, viewport: { width: 1440, height: 900 } },
})
