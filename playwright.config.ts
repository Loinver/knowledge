import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { defineConfig } from '@playwright/test'

const root = dirname(fileURLToPath(import.meta.url))
const e2eTempDir = process.env.KG_E2E_TEMP_DIR ?? mkdtempSync(join(tmpdir(), 'knowledge-e2e-'))
const metadataDb = join(e2eTempDir, 'metadata.sqlite')
const inheritedEnv = Object.fromEntries(
  Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] !== undefined),
) as Record<string, string>

process.env.KG_E2E_TEMP_DIR = e2eTempDir

const isolatedEnv = {
  ...inheritedEnv,
  KG_ENVIRONMENT: 'development',
  KG_CREATE_TABLES_ON_STARTUP: 'true',
  KG_DATABASE_URL: 'sqlite:///' + metadataDb,
  KG_E2E_TEMP_DIR: e2eTempDir,
  KG_ALLOW_PUBLIC_REGISTRATION: 'true',
  KG_EXPOSE_RESET_TOKEN: 'false',
  KG_PASSWORD_ITERATIONS: '1000',
  KG_API_PROXY_TARGET: 'http://127.0.0.1:8123',
}

export default defineConfig({
  testDir: './e2e',
  globalTeardown: './e2e/global-teardown.ts',
  fullyParallel: false,
  workers: 1,
  timeout: 180_000,
  expect: { timeout: 10_000 },
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5199',
    browserName: 'chromium',
    locale: 'zh-CN',
    viewport: { width: 1440, height: 960 },
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: './.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8123',
      cwd: resolve(root, 'server'),
      url: 'http://127.0.0.1:8123/api/v1/health',
      env: isolatedEnv,
      reuseExistingServer: false,
      timeout: 120_000,
      name: 'isolated API',
    },
    {
      command: './node_modules/.bin/vite --host 127.0.0.1 --port 5199 --strictPort',
      cwd: resolve(root, 'web'),
      url: 'http://127.0.0.1:5199/login',
      env: isolatedEnv,
      reuseExistingServer: false,
      timeout: 120_000,
      name: 'Vite frontend',
    },
  ],
})
