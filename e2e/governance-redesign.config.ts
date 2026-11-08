import { mkdtempSync, realpathSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, dirname, join, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

import { defineConfig } from '@playwright/test'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const directory =
  process.env.KG_GOVERNANCE_TEST_DIR ?? mkdtempSync(join(tmpdir(), 'knowledge-governance-'))
const webPort = Number(process.env.KG_GOVERNANCE_WEB_PORT ?? 5207)
const apiPort = Number(process.env.KG_GOVERNANCE_API_PORT ?? 8137)
const resolvedDirectory = realpathSync(directory)
if (
  !resolvedDirectory.startsWith(realpathSync(tmpdir()) + sep) ||
  !basename(resolvedDirectory).startsWith('knowledge-governance-')
) {
  throw new Error('Governance browser tests require a dedicated temporary database directory')
}
if (![webPort, apiPort].every((port) => Number.isInteger(port) && port >= 1024 && port <= 65535)) {
  throw new Error('Governance browser tests require valid local ports')
}
process.env.KG_GOVERNANCE_TEST_DIR = directory
const env = {
  KG_ENVIRONMENT: 'development',
  KG_CREATE_TABLES_ON_STARTUP: 'true',
  KG_DATABASE_URL: `sqlite:///${join(directory, 'metadata.sqlite')}`,
  KG_PASSWORD_ITERATIONS: '1000',
  KG_ALLOW_PUBLIC_REGISTRATION: 'false',
  KG_API_PROXY_TARGET: `http://127.0.0.1:${apiPort}`,
}

export default defineConfig({
  testDir: '.',
  testMatch: 'governance-redesign.browser.ts',
  workers: 1,
  timeout: 90_000,
  outputDir: join(directory, 'results'),
  reporter: 'list',
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    viewport: { width: 1440, height: 900 },
    browserName: 'chromium',
    locale: 'zh-CN',
    actionTimeout: 10_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: `./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: join(root, 'server'),
      url: `http://127.0.0.1:${apiPort}/api/v1/health`,
      env,
      reuseExistingServer: false,
    },
    {
      command: `./node_modules/.bin/vite --host 127.0.0.1 --port ${webPort} --strictPort`,
      cwd: join(root, 'web'),
      url: `http://127.0.0.1:${webPort}/login`,
      env,
      reuseExistingServer: false,
    },
  ],
})
