import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync, realpathSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, dirname, join, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

import type { APIRequestContext, Page } from '@playwright/test'
import { expect, test } from '@playwright/test'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const password = 'Governance-Test-2026!'
const locale = JSON.parse(readFileSync(join(root, 'web/src/locales/zh-CN.json'), 'utf8'))
const text = (key: string): string =>
  key.split('.').reduce((value, part) => value?.[part], locale) ?? key
let ruleId: number
let templateId: number

async function data(api: APIRequestContext, path: string, input: unknown) {
  const response = await api.post(`/api/v1${path}`, { data: input })
  expect(response.ok(), await response.text()).toBe(true)
  return (await response.json()).data
}

async function login(page: Page, role: 'ADMIN' | 'EDITOR' | 'VIEWER') {
  await page.goto('/login')
  await page
    .getByPlaceholder('用户名或邮箱', { exact: true })
    .fill(`governance_${role.toLowerCase()}`)
  await page.getByPlaceholder('请输入密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
}

test.beforeAll(async ({ playwright, baseURL }) => {
  expect(baseURL).toBe(`http://127.0.0.1:${Number(process.env.KG_GOVERNANCE_WEB_PORT ?? 5207)}`)
  const directory = realpathSync(process.env.KG_GOVERNANCE_TEST_DIR!)
  expect(directory.startsWith(realpathSync(tmpdir()) + sep)).toBe(true)
  expect(basename(directory)).toMatch(/^knowledge-governance-/)
  expect(existsSync(join(directory, 'metadata.sqlite'))).toBe(true)
  const fixtureFile = join(directory, 'governance-browser-fixtures.json')
  if (existsSync(fixtureFile)) {
    const fixture = JSON.parse(readFileSync(fixtureFile, 'utf8'))
    ruleId = fixture.ruleId
    templateId = fixture.templateId
    return
  }
  execFileSync(
    join(root, 'server/.venv/bin/python'),
    [
      join(root, 'scripts/seed_admin.py'),
      '--username',
      'governance_admin',
      '--email',
      'governance_admin@example.org',
      '--password',
      password,
    ],
    {
      cwd: join(root, 'server'),
      env: {
        ...process.env,
        KG_ENVIRONMENT: 'development',
        KG_DATABASE_URL: `sqlite:///${join(directory, 'metadata.sqlite')}`,
        KG_PASSWORD_ITERATIONS: '1000',
      },
      stdio: 'pipe',
    },
  )
  const anonymous = await playwright.request.newContext({ baseURL })
  const token = await data(anonymous, '/auth/login', { account: 'governance_admin', password })
  const api = await playwright.request.newContext({
    baseURL,
    extraHTTPHeaders: { Authorization: `Bearer ${token.access_token}` },
  })
  try {
    for (const role of ['EDITOR', 'VIEWER']) {
      await data(api, '/users', {
        username: `governance_${role.toLowerCase()}`,
        email: `governance_${role.toLowerCase()}@example.org`,
        password,
        role,
      })
    }
    const rule = await data(api, '/governance/rules', {
      identifier: 'GovernanceBrowserRule',
      name_i18n: { 'zh-CN': '浏览器规则', 'en-US': 'Browser rule' },
      category: 'quality',
      source_kind: 'ENTERPRISE',
      source_reference: 'Policy 1',
      target_iri: 'https://example.org/Entity',
      severity: 'VIOLATION',
      language: 'OWL',
      execution: 'MANUAL',
      expression: '<https://example.org/Entity> a <http://www.w3.org/2002/07/owl#Class> .',
    })
    ruleId = rule.id
    await data(api, '/governance/clauses', {
      standard: 'Example Standard',
      clause_number: '1',
      title_i18n: { 'zh-CN': '示例条款' },
      self_authored_description: { 'zh-CN': '自撰说明' },
      appendix_nature: 'NORMATIVE',
    })
    const dictionary = await data(api, '/governance/enum-dictionaries', {
      name: 'BrowserStatus',
      label_i18n: { 'zh-CN': '浏览器状态' },
      definition_i18n: { 'zh-CN': '状态定义' },
      entries: [{ value: 'OPEN', label_i18n: { 'zh-CN': '开放' } }],
    })
    const update = await api.put(`/api/v1/governance/enum-dictionaries/${dictionary.id}`, {
      headers: { 'If-Match': String(dictionary.revision) },
      data: {
        name: dictionary.name,
        label_i18n: dictionary.label_i18n,
        definition_i18n: dictionary.definition_i18n,
        entries: [...dictionary.entries, { value: 'CLOSED', label_i18n: { 'zh-CN': '关闭' } }],
      },
    })
    expect(update.ok(), await update.text()).toBe(true)
    const template = await data(api, '/governance/templates', {
      name: 'BrowserTemplate',
      label_i18n: { 'zh-CN': '浏览器模板' },
      source: 'Policy 1',
      basis: 'Example domain',
      resources: [],
    })
    templateId = template.id
    writeFileSync(fixtureFile, JSON.stringify({ ruleId, templateId }))
  } finally {
    await anonymous.dispose()
    await api.dispose()
  }
})

test('VIEWER uses governance read paths and rule test only; API rejects other writes', async ({
  page,
  playwright,
  baseURL,
}, info) => {
  await login(page, 'VIEWER')
  const mutations: string[] = []
  page.on('request', (request) => {
    if (
      request.url().includes('/api/v1/') &&
      !['GET', 'HEAD', 'OPTIONS'].includes(request.method())
    )
      mutations.push(new URL(request.url()).pathname)
  })
  await page.goto('/governance/rules')
  await expect(page.getByRole('button', { name: text('rules.create'), exact: true })).toBeDisabled()
  await page.getByRole('button', { name: text('governanceUi.details'), exact: true }).click()
  await page.getByText(text('rules.examples'), { exact: true }).click()
  const testResponse = page.waitForResponse((response) =>
    response.url().endsWith(`/rules/${ruleId}/test`),
  )
  await expect(page.getByRole('button', { name: text('rules.runTest'), exact: true })).toBeEnabled()
  await page.getByRole('button', { name: text('rules.runTest'), exact: true }).click()
  expect((await testResponse).ok()).toBe(true)
  await expect(page.locator('.test-summary')).toContainText(text('validation.NOT_RUN'))
  for (const [path, action] of [
    ['clauses', 'clauses.create'],
    ['enum-dictionaries', 'enumDictionaries.create'],
    ['templates', 'templates.create'],
  ]) {
    await page.goto(`/governance/${path}`)
    await expect(page.getByRole('button', { name: text(action), exact: true })).toBeDisabled()
  }
  await page
    .getByRole('button', { name: text('governanceUi.previewTemplate'), exact: true })
    .click()
  await expect(
    page.getByRole('button', { name: text('governanceUi.configureInstance'), exact: true }),
  ).toBeDisabled()
  await page.goto('/governance/export')
  await expect(page.getByRole('heading', { name: text('ui.exchange'), exact: true })).toBeVisible()
  await page.getByText(text('governanceUi.importTab'), { exact: true }).click()
  await expect(
    page.getByRole('button', { name: text('ontologyRestore.preview'), exact: true }),
  ).toBeDisabled()
  await expect(
    page.getByRole('button', { name: text('ontologyRestore.apply'), exact: true }),
  ).toBeDisabled()
  expect(mutations).toEqual([`/api/v1/governance/rules/${ruleId}/test`])
  await page.screenshot({ path: info.outputPath('viewer-import.png'), animations: 'disabled' })
  const anonymous = await playwright.request.newContext({ baseURL })
  const token = await data(anonymous, '/auth/login', { account: 'governance_viewer', password })
  const api = await playwright.request.newContext({
    baseURL,
    extraHTTPHeaders: { Authorization: `Bearer ${token.access_token}` },
  })
  try {
    for (const path of [
      '/ontologies/import/restore-preview',
      `/governance/templates/${templateId}/core-check`,
      `/governance/templates/${templateId}/instantiate`,
    ]) {
      const response = await api.post(`/api/v1${path}`, { data: {} })
      expect(response.status()).toBe(403)
    }
  } finally {
    await anonymous.dispose()
    await api.dispose()
  }
})

test('EDITOR sees grouped clauses, frozen enum history, and template preview before creation', async ({
  page,
}, info) => {
  await login(page, 'EDITOR')
  await page.goto('/governance/clauses')
  await page.getByRole('button', { name: text('common.edit'), exact: true }).click()
  await expect(page.getByText(text('governanceUi.clauseIdentity'), { exact: true })).toBeVisible()
  const details = page.locator('details.terminology')
  await expect(details).not.toHaveAttribute('open')
  await details.locator('summary').click()
  await expect(details).toHaveAttribute('open')
  await page.screenshot({
    path: info.outputPath('editor-clause-groups.png'),
    animations: 'disabled',
  })
  await page.goto('/governance/enum-dictionaries')
  await page.getByRole('button', { name: text('enumDictionaries.details'), exact: true }).click()
  await page.getByText(text('enumDictionaries.history'), { exact: true }).click()
  await expect(page.getByRole('button', { name: text('common.save'), exact: true })).toHaveCount(0)
  await expect(page.locator('.history-description')).toBeVisible()
  await page.goto('/governance/templates')
  await page
    .getByRole('button', { name: text('governanceUi.previewTemplate'), exact: true })
    .click()
  await expect(page.locator('.instance-preview')).toBeVisible()
  await expect(
    page.getByRole('button', { name: text('templates.instantiate'), exact: true }),
  ).toHaveCount(0)
  await page.screenshot({
    path: info.outputPath('editor-template-preview.png'),
    animations: 'disabled',
  })
  await page
    .getByRole('button', { name: text('governanceUi.configureInstance'), exact: true })
    .click()
  await expect(
    page.getByRole('button', { name: text('templates.instantiate'), exact: true }),
  ).toBeDisabled()
})

test('rule list separates loading, error, retry and empty', async ({ page }) => {
  await login(page, 'EDITOR')
  let release!: () => void
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route('**/api/v1/governance/rules?**', async (route) => {
    await gate
    await route.fulfill({ status: 503, json: { code: 'NETWORK_ERROR' } })
  })
  await page.goto('/governance/rules')
  await expect(page.locator('p[role="status"]')).toHaveText(text('common.loading'))
  await expect(page.getByText(text('rules.empty'), { exact: true })).toHaveCount(0)
  release()
  await expect(page.locator('[role="alert"]')).toBeVisible()
  await expect(page.getByText(text('rules.empty'), { exact: true })).toHaveCount(0)
  await page.unroute('**/api/v1/governance/rules?**')
  await page.route('**/api/v1/governance/rules?**', (route) =>
    route.fulfill({
      json: { code: 'KG.OK', data: { items: [], total: 0, page: 1, page_size: 20 } },
    }),
  )
  await page.getByRole('button', { name: text('governanceUi.retry'), exact: true }).click()
  await expect(page.getByText(text('rules.empty'), { exact: true })).toBeVisible()
  await expect(page.locator('[role="alert"]')).toHaveCount(0)
})

test('X08 governance guards preserve cancelled input, allow discard and do not prompt after save or history loading', async ({
  page,
}, info) => {
  await login(page, 'EDITOR')
  const dialogs: string[] = []
  let discard = false
  page.on('dialog', async (dialog) => {
    dialogs.push(dialog.message())
    if (discard) await dialog.accept()
    else await dialog.dismiss()
  })
  await page.goto('/governance/rules')
  await page.getByRole('button', { name: text('common.edit'), exact: true }).click()
  await page.getByText(text('rules.expressionTab'), { exact: true }).click()
  const expression = page.getByLabel(text('rules.expression'), { exact: true })
  const changed = (await expression.inputValue()) + '\n# unsaved X08'
  await expression.fill(changed)
  await page
    .locator('.n-drawer')
    .getByRole('button', { name: text('common.cancel'), exact: true })
    .click()
  await expect(expression).toHaveValue(changed)
  expect(dialogs).toEqual([text('ui.unsaved')])
  await page.screenshot({ path: info.outputPath('x08-rule-retained.png'), animations: 'disabled' })
  await page
    .locator('.n-drawer')
    .getByRole('button', { name: text('common.save'), exact: true })
    .click()
  await expect(page.getByText(text('rules.saved'), { exact: true })).toBeVisible()
  await page
    .locator('.n-drawer')
    .getByRole('button', { name: text('common.cancel'), exact: true })
    .click()
  await expect(page.locator('.n-drawer')).toHaveCount(0)
  expect(dialogs).toHaveLength(1)

  await page.goto('/governance/clauses')
  await page.getByRole('button', { name: text('clauses.create'), exact: true }).click()
  const standard = page
    .locator('.n-drawer')
    .getByPlaceholder(text('clauses.standardPlaceholder'), { exact: true })
  await standard.fill('unsaved standard')
  await page.keyboard.press('Escape')
  await expect(standard).toHaveValue('unsaved standard')
  discard = true
  await page.keyboard.press('Escape')
  await expect(page.locator('.n-drawer')).toHaveCount(0)
  expect(dialogs).toHaveLength(3)
  discard = false

  let release!: () => void
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route('**/api/v1/governance/enum-dictionaries/*', async (route) => {
    if (/\/\d+$/.test(new URL(route.request().url()).pathname)) await gate
    await route.continue()
  })
  await page.goto('/governance/enum-dictionaries')
  await page.getByRole('button', { name: text('enumDictionaries.details'), exact: true }).click()
  await expect(page.locator('.n-drawer p[role="status"]')).toHaveText(text('common.loading'))
  release()
  await expect(page.getByText(text('governanceUi.currentEntries'), { exact: true })).toBeVisible()
  await page.getByText(text('enumDictionaries.history'), { exact: true }).click()
  await expect(page.locator('.history-description')).toBeVisible()
  await page
    .locator('.n-drawer')
    .getByRole('button', { name: text('common.cancel'), exact: true })
    .click()
  await expect(page.locator('.n-drawer')).toHaveCount(0)
  expect(dialogs).toHaveLength(3)

  await page.goto('/governance/templates')
  await page
    .getByRole('button', { name: text('governanceUi.previewTemplate'), exact: true })
    .click()
  await page
    .getByRole('button', { name: text('governanceUi.configureInstance'), exact: true })
    .click()
  const instanceName = page.locator('.n-modal input').first()
  await instanceName.fill('UnsavedOntology')
  await page.keyboard.press('Escape')
  await expect(instanceName).toHaveValue('UnsavedOntology')
  discard = true
  await page.keyboard.press('Escape')
  await expect(page.locator('.n-modal')).toHaveCount(0)
  expect(dialogs).toHaveLength(5)

  await page.goto('/governance/export')
  await page.getByText(text('governanceUi.importTab'), { exact: true }).click()
  await page.locator('#ontology-restore-content').fill('unsaved RDF')
  discard = false
  await page.locator('a[href="/"]').first().click()
  await expect(page).toHaveURL(/\/governance\/export$/)
  await expect(page.locator('#ontology-restore-content')).toHaveValue('unsaved RDF')
  await page.screenshot({
    path: info.outputPath('x08-import-retained.png'),
    animations: 'disabled',
  })
  discard = true
  await page.locator('a[href="/"]').first().click()
  await expect(page).toHaveURL(/\/$/)
  expect(dialogs).toHaveLength(7)
})

test('X08 user modals guard cancel, mask and Escape while successful create and edit close directly', async ({
  page,
}, info) => {
  await login(page, 'ADMIN')
  const dialogs: string[] = []
  let discard = false
  page.on('dialog', async (dialog) => {
    dialogs.push(dialog.message())
    if (discard) await dialog.accept()
    else await dialog.dismiss()
  })
  await page.goto('/system/users')
  await page.getByRole('button', { name: text('system.createUser'), exact: true }).click()
  const modal = page.locator('.n-modal')
  const username = modal.getByPlaceholder(text('system.usernamePlaceholder'), { exact: true })
  await username.fill('unsaved_user')
  await page.keyboard.press('Escape')
  await expect(username).toHaveValue('unsaved_user')
  // Naive UI handles outside clicks through the full-screen scroll container above its mask.
  await page.locator('.n-modal-scroll-content').click({ position: { x: 10, y: 10 } })
  await expect(username).toHaveValue('unsaved_user')
  expect(dialogs).toHaveLength(2)
  await page.screenshot({ path: info.outputPath('x08-user-retained.png'), animations: 'disabled' })
  discard = true
  await modal.getByRole('button', { name: text('common.cancel'), exact: true }).click()
  await expect(modal).toHaveCount(0)
  await page.getByRole('button', { name: text('system.createUser'), exact: true }).click()
  const account = 'x08_' + Date.now()
  await username.fill(account)
  await modal
    .locator('.n-form-item')
    .filter({ hasText: text('auth.email') })
    .locator('input')
    .fill(account + '@example.org')
  await modal.locator('input[type="password"]').fill(password)
  await modal.getByRole('button', { name: text('common.create'), exact: true }).click()
  await expect(modal).toHaveCount(0)
  expect(dialogs).toHaveLength(3)
  const row = page.getByRole('row').filter({ hasText: account })
  await row.getByRole('button', { name: text('common.edit'), exact: true }).click()
  await modal.locator('.n-base-selection').first().click()
  await page
    .locator('.n-base-select-option')
    .filter({ hasText: text('account.roles.VIEWER') })
    .click()
  discard = false
  await modal.getByRole('button', { name: text('common.cancel'), exact: true }).click()
  await expect(modal).toBeVisible()
  await expect(modal.locator('.n-base-selection').first()).toContainText(
    text('account.roles.VIEWER'),
  )
  await modal.getByRole('button', { name: text('common.save'), exact: true }).click()
  await expect(modal).toHaveCount(0)
  expect(dialogs).toHaveLength(4)
  await page.screenshot({ path: info.outputPath('x08-user-saved.png'), animations: 'disabled' })
})
