import { resolve } from 'node:path'

import { defineConfig } from '@playwright/test'

import base from '../playwright.config'

const servers = Array.isArray(base.webServer) ? base.webServer : [base.webServer!]
const env = {
  KG_LLM_BASE_URL: 'http://127.0.0.1:8134/v1',
  KG_LLM_API_KEY: 'isolated-test-key',
  KG_LLM_MODEL: 'test-extractive-fixture',
  KG_EMBEDDING_BASE_URL: 'http://127.0.0.1:8134/v1',
  KG_EMBEDDING_API_KEY: 'isolated-test-key',
  KG_EMBEDDING_MODEL: 'test-three-dimensional-fixture',
  KG_EMBEDDING_VERSION: 'test-v1',
}
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
    ...servers.map((server) => ({ ...server, env: { ...server.env, ...env } })),
  ],
})
