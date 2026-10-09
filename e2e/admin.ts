import { execFileSync } from 'node:child_process'
import { join, resolve } from 'node:path'

import { expect, type Page } from '@playwright/test'

export const ADMIN = { account: 'e2e_admin', password: 'E2E-Admin-Password-2026!' }

export async function ensureAdmin(page: Page): Promise<void> {
  const login = await page.request.post('/api/v1/auth/login', {
    data: { account: ADMIN.account, password: ADMIN.password },
  })
  if (login.ok()) return

  const tempDir = process.env.KG_E2E_TEMP_DIR
  expect(tempDir, 'Playwright config provides an isolated temp directory').toBeTruthy()
  execFileSync(
    resolve('server/.venv/bin/python'),
    [
      resolve('scripts/seed_admin.py'),
      '--username',
      ADMIN.account,
      '--email',
      'e2e_admin@example.org',
      '--password',
      ADMIN.password,
    ],
    {
      cwd: resolve('server'),
      env: {
        ...process.env,
        KG_ENVIRONMENT: 'development',
        KG_DATABASE_URL: 'sqlite:///' + join(tempDir!, 'metadata.sqlite'),
        KG_PASSWORD_ITERATIONS: '1000',
      },
      stdio: 'pipe',
      timeout: 30_000,
    },
  )
}

export async function loginAsAdmin(page: Page): Promise<void> {
  await page.goto('/login')
  await page.getByPlaceholder('用户名或邮箱', { exact: true }).fill(ADMIN.account)
  await page.getByPlaceholder('请输入密码', { exact: true }).fill(ADMIN.password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
}
