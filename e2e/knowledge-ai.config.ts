import { resolve } from 'node:path'

import { defineConfig } from '@playwright/test'

import base from '../playwright.config'

const servers = Array.isArray(base.webServer) ? base.webServer : [base.webServer!]
export default defineConfig({
  ...base,
  testDir: '.',
  testMatch: 'knowledge-ai.browser.ts',
  globalTeardown: './global-teardown.ts',
  outputDir: '../test-results/knowledge-ai',
  webServer: [
    {
      command: './server/.venv/bin/python e2e/knowledge-model-server.py',
      cwd: resolve(import.meta.dirname, '..'),
      url: 'http://127.0.0.1:8134',
      env: { KG_E2E_TEMP_DIR: process.env.KG_E2E_TEMP_DIR! },
      reuseExistingServer: false,
    },
    ...servers,
  ],
})
