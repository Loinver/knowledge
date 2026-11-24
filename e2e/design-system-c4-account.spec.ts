import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import type { components } from '../web/src/api/schema'
import {
  capture,
  expect,
  expectNoPageOverflow,
  getData,
  responseData,
  test,
  uniqueName,
  waitForApi,
} from './ui-redesign-fixtures'

const copy = JSON.parse(readFileSync(resolve('web/src/locales/zh-CN.json'), 'utf8'))
const english = JSON.parse(readFileSync(resolve('web/src/locales/en-US.json'), 'utf8'))
type User = components['schemas']['UserOut']

test('auth: keyboard validation, failed login retains input, one pending request, and missing reset token', async ({
  page,
  identity,
  network,
}) => {
  const writes: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname.startsWith('/api/v1/auth/'))
      writes.push(new URL(request.url()).pathname)
  })
  await page.goto('/login?redirect=/account/profile')
  await page.getByRole('button', { name: copy.auth.login, exact: true }).click()
  const account = page.getByLabel(copy.auth.account, { exact: false })
  const password = page
    .locator('input[type="password"]')
    .and(page.getByLabel(copy.auth.password, { exact: false }))
  await expect(account).toBeFocused()
  await expect(account).toHaveAttribute('aria-invalid', 'true')
  expect(writes).toHaveLength(0)
  await account.fill(identity.credentials.ADMIN.account)
  await password.fill(identity.credentials.ADMIN.password)
  await network.failOnce({ path: '/auth/login', method: 'POST' })
  await password.press('Enter')
  await expect(page.locator('.auth-flow').getByRole('alert')).toHaveCount(1)
  await expect(password).toHaveValue(identity.credentials.ADMIN.password)
  expect(writes).toHaveLength(1)
  const hold = await network.hold({ path: '/auth/login', method: 'POST' })
  try {
    await password.press('Enter')
    await expect.poll(hold.hits).toBe(1)
    await expect(page.getByRole('button', { name: copy.auth.login, exact: true })).toBeDisabled()
    await page.keyboard.press('Enter')
    expect(hold.hits()).toBe(1)
  } finally {
    hold.release()
  }
  await expect(page).toHaveURL(/\/account\/profile$/)
  // A new context has no login state; reset token checks belong to the public route.
  const publicPage = await page
    .context()
    .browser()!
    .newPage({ baseURL: new URL(page.url()).origin, locale: 'zh-CN' })
  try {
    await publicPage.goto('/reset-password')
    await expect(publicPage.getByText(copy.auth.resetTokenMissing, { exact: true })).toBeVisible()
    await expect(
      publicPage.getByRole('button', { name: copy.auth.resetSubmit, exact: true }),
    ).toBeDisabled()
    await expect(
      publicPage
        .locator('input[type="password"]')
        .and(publicPage.getByLabel(copy.auth.newPassword, { exact: false })),
    ).toBeDisabled()
  } finally {
    await publicPage.close()
  }
})

test('profile: real validation, failure preservation, duplicate protection, null clear, themes and viewports', async ({
  signedIn: page,
  identity,
  network,
  evidence,
}, info) => {
  const submitted: Record<string, unknown>[] = []
  page.on('request', (request) => {
    if (
      request.method() === 'PATCH' &&
      new URL(request.url()).pathname === '/api/v1/users/me/profile'
    )
      submitted.push(request.postDataJSON())
  })
  await page.goto('/account/profile')
  const display = page.getByLabel(copy.account.displayName, { exact: false })
  const avatar = page.getByLabel(copy.account.avatarUrl, { exact: false })
  const save = page.getByRole('button', { name: copy.common.save, exact: true })
  await display.fill('x'.repeat(33))
  await avatar.fill('invalid URL')
  await save.click()
  await expect(display).toBeFocused()
  await expect(display).toHaveAttribute('aria-invalid', 'true')
  expect(submitted).toHaveLength(0)
  const name = uniqueName('C4Profile')
  await display.fill(name)
  await avatar.fill('')
  await network.failOnce({ path: '/users/me/profile', method: 'PATCH' })
  await save.click()
  await expect(page.locator('.account-page > [role=alert]')).toBeVisible()
  await expect(display).toHaveValue(name)
  const hold = await network.hold({ path: '/users/me/profile', method: 'PATCH' })
  try {
    await save.click()
    await expect.poll(hold.hits).toBe(1)
    await expect(save).toBeDisabled()
    await page.keyboard.press('Enter')
    expect(hold.hits()).toBe(1)
  } finally {
    hold.release()
  }
  await expect(page.getByText(copy.account.saved, { exact: true })).toBeVisible()
  await display.fill('')
  await avatar.fill('')
  const cleared = waitForApi(page, { path: '/users/me/profile', method: 'PATCH' })
  await save.click()
  await responseData(await cleared)
  expect(submitted.at(-1)).toEqual({ display_name: null, avatar_url: null })
  expect((await getData<User>(identity.api, '/auth/me')).display_name).toBeNull()
  for (const theme of ['light', 'dark']) {
    await page.evaluate((value) => localStorage.setItem('kg-theme-mode', value), theme)
    await page.reload()
    for (const viewport of [
      { width: 1440, height: 900 },
      { width: 1280, height: 720 },
      { width: 768, height: 1024 },
      { width: 390, height: 844 },
    ]) {
      await page.setViewportSize(viewport)
      await expectNoPageOverflow(page)
      await capture(
        page,
        info,
        evidence,
        `c4-profile-${theme}-${viewport.width}`,
        'profile after explicit null clear',
      )
    }
  }
  await page.evaluate(() => localStorage.setItem('kg-locale', 'en-US'))
  await page.reload()
  await expect(
    page.getByRole('heading', { name: english.account.profile, exact: true }),
  ).toBeVisible()
  await expect(page.getByLabel(english.account.displayName, { exact: false })).toBeVisible()
})

test('users: remote search and pages, validated create, failure retention, role/status and Esc focus', async ({
  signedIn: page,
  identity,
  network,
}) => {
  const prefix = uniqueName('c4_user_')
  for (let index = 0; index < 21; index++) {
    await responseData(
      await identity.api.post('/api/v1/users', {
        data: {
          username: prefix + index,
          email: prefix + index + '@example.org',
          password: 'C4-Test-Password-2026!',
          role: 'VIEWER',
        },
      }),
    )
  }
  await page.goto('/system/users')
  const search = page.getByRole('searchbox')
  await search.fill(prefix)
  await search.press('Enter')
  const rows = page.locator('main tbody tr[data-row-key]')
  await expect(rows).toHaveCount(20)
  await page.getByRole('button', { name: copy.runs.next, exact: true }).click()
  await expect(rows).toHaveCount(1)
  await page.getByRole('button', { name: copy.runs.previous, exact: true }).click()
  await expect(rows).toHaveCount(20)
  await search.fill(prefix + 'missing')
  await search.press('Enter')
  await expect(page.getByText(copy.common.empty, { exact: true })).toBeVisible()
  await page.getByRole('button', { name: copy.ds.search.clear, exact: true }).click()
  await expect(rows).toHaveCount(20)
  const create = page.getByRole('button', { name: copy.system.createUser, exact: true })
  await create.click()
  const dialog = page.getByRole('dialog')
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(create).toBeFocused()
  await create.click()
  const username = dialog.getByLabel(copy.auth.username, { exact: false })
  const save = dialog.getByRole('button', { name: copy.common.create, exact: true })
  const writes: Record<string, unknown>[] = []
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/v1/users' && request.method() === 'POST')
      writes.push(request.postDataJSON())
  })
  await save.click()
  await expect(username).toBeFocused()
  expect(writes).toHaveLength(0)
  await username.fill(prefix + 'new')
  await dialog.getByLabel(copy.auth.email, { exact: false }).fill(prefix + 'new@example.org')
  await dialog
    .locator('input[type="password"]')
    .and(dialog.getByLabel(copy.auth.password, { exact: false }))
    .fill('C4-Test-Password-2026!')
  await network.failOnce({ path: '/users', method: 'POST' })
  await save.click()
  await expect(dialog.getByRole('alert')).toHaveCount(1)
  await expect(username).toHaveValue(prefix + 'new')
  const hold = await network.hold({ path: '/users', method: 'POST' })
  const saved = waitForApi(page, { path: '/users', method: 'POST' })
  try {
    await username.press('Enter')
    await expect.poll(hold.hits).toBe(1)
    await expect(save).toBeDisabled()
    await page.keyboard.press('Enter')
    expect(hold.hits()).toBe(1)
  } finally {
    hold.release()
  }
  const user = await responseData<User>(await saved)
  await expect(dialog).toHaveCount(0)
  expect(writes).toHaveLength(2)
  await search.fill(prefix + 'new')
  await search.press('Enter')
  const row = rows.filter({ hasText: prefix + 'new' })
  await row.getByRole('button', { name: copy.common.edit, exact: true }).click()
  await dialog.getByRole('combobox', { name: copy.account.role, exact: false }).click()
  await page.getByRole('option', { name: copy.account.roles.VIEWER, exact: true }).click()
  await dialog.getByRole('combobox', { name: copy.account.status, exact: false }).click()
  await page.getByRole('option', { name: copy.account.statuses.DISABLED, exact: true }).click()
  const edited = waitForApi(page, { path: `/users/${user.id}`, method: 'PATCH' })
  await dialog.getByRole('button', { name: copy.common.save, exact: true }).click()
  const updated = await responseData<User>(await edited)
  expect(updated.role).toBe('VIEWER')
  expect(updated.status).toBe('DISABLED')
  await expect(dialog).toHaveCount(0)
  await expect(row.getByText(copy.account.statuses.DISABLED, { exact: true })).toBeVisible()
})

test('models: boolean filter contract, failed form, numeric/false payload and bounded drawer', async ({
  signedIn: page,
  network,
  evidence,
}, info) => {
  await page.goto('/system/ai-models')
  const filter = page
    .locator('.search-panel')
    .getByRole('combobox', { name: copy.common.status, exact: false })
  await filter.click()
  const filtered = waitForApi(page, { path: '/ai/model-configs', query: { enabled: 'false' } })
  await page.getByRole('option', { name: copy.aiModels.disabled, exact: true }).click()
  await responseData(await filtered)
  await page.getByRole('button', { name: copy.aiModels.create, exact: true }).click()
  const dialog = page.getByRole('dialog')
  const create = dialog.getByRole('button', { name: copy.common.create, exact: true })
  await create.click()
  const name = dialog.getByLabel(copy.aiModels.name, { exact: false })
  await expect(name).toBeFocused()
  await expect(name).toHaveAttribute('aria-invalid', 'true')
  const configName = uniqueName('C4Model')
  await name.fill(configName)
  await dialog.getByLabel(copy.aiModels.baseUrl, { exact: false }).fill('https://example.org/v1')
  await dialog.getByRole('textbox', { name: copy.aiModels.model }).fill('synthetic-model')
  await network.failOnce({ path: '/ai/model-configs', method: 'POST' })
  await create.click()
  await expect(dialog.getByRole('alert')).toHaveCount(1)
  await expect(name).toHaveValue(configName)
  const saved = waitForApi(page, { path: '/ai/model-configs', method: 'POST' })
  await create.click()
  const configuration = await responseData<components['schemas']['AiModelConfigOut']>(await saved)
  expect(configuration.enabled).toBe(false)
  expect(configuration.timeout_seconds).toBe(30)
  expect(configuration.has_key).toBe(false)
  await expect(dialog).toHaveCount(0)
  await page.getByRole('button', { name: copy.aiModels.create, exact: true }).click()
  for (const viewport of [
    { width: 1280, height: 720 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport)
    await expectNoPageOverflow(page)
    const bounds = await dialog.boundingBox()
    expect(bounds!.height).toBeLessThanOrEqual(viewport.height)
    expect(bounds!.width).toBeLessThanOrEqual(viewport.width)
    await capture(
      page,
      info,
      evidence,
      `c4-model-${viewport.width}`,
      'fresh model drawer after failed and successful writes',
    )
  }
})

test('asset audit: namespace enum stays NAMESPACE and filters reach the remote API', async ({
  signedIn: page,
}) => {
  await page.goto('/system/audit-logs')
  await page.getByRole('combobox', { name: copy.assetAudit.objectType, exact: false }).click()
  await page.getByRole('option', { name: copy.assetAudit.objects.NAMESPACE, exact: true }).click()
  const read = waitForApi(page, { path: '/asset-audit-logs', query: { object_type: 'NAMESPACE' } })
  await page
    .locator('.asset-audit')
    .getByRole('button', { name: copy.common.search, exact: true })
    .click()
  await responseData(await read)
})
