import { execFileSync, spawn } from 'node:child_process'
import { once } from 'node:events'
import { mkdtempSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { expect, test } from '@playwright/test'

import { ADMIN, ensureAdmin, loginAsAdmin } from './admin'

test('UI export, restore into an independent database, and semantic reexport', async ({
  page,
  browser,
}, testInfo) => {
  await ensureAdmin(page)
  const login = await page.request.post('/api/v1/auth/login', { data: ADMIN })
  const token = (await login.json()).data.access_token
  const headers = { Authorization: `Bearer ${token}` }
  // The synthetic source is prepared through real APIs; transfer actions use the UI.
  const namespace = await page.request.post('/api/v1/namespaces', {
    headers,
    data: { prefix: 'transfer', iri: 'https://example.org/transfer#' },
  })
  expect(namespace.ok(), await namespace.text()).toBeTruthy()
  const resource = await page.request.post('/api/v1/entity-types', {
    headers,
    data: {
      name: 'TransferPerson',
      namespace_id: (await namespace.json()).data.id,
      label_i18n: { 'zh-CN': '迁移人员', 'en-US': 'Transfer person' },
      data_props: [
        { name: 'Name', datatype: 'string', label_i18n: { 'zh-CN': '姓名' }, nullable: false },
      ],
    },
  })
  expect(resource.ok(), await resource.text()).toBeTruthy()
  const resourceId = (await resource.json()).data.id
  expect(
    (await page.request.post(`/api/v1/entity-types/${resourceId}/publish`, { headers })).ok(),
  ).toBeTruthy()
  const ontology = await page.request.post('/api/v1/ontologies', {
    headers,
    data: {
      name: 'TransferOntology',
      iri: 'https://example.org/transfer/ontology',
      label_i18n: { 'zh-CN': '迁移本体' },
      ref_resource_ids: [resourceId],
    },
  })
  expect(ontology.ok(), await ontology.text()).toBeTruthy()
  const ontologyData = (await ontology.json()).data
  const published = await page.request.post(`/api/v1/ontologies/${ontologyData.id}/publish`, {
    headers: { ...headers, 'If-Edit-Match': String(ontologyData.edit_revision) },
  })
  expect(published.ok(), await published.text()).toBeTruthy()
  await loginAsAdmin(page)
  await page.goto(`/governance/export?ontology=${ontologyData.id}&revision=1`)
  const sourceDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载文件', exact: true }).click()
  const sourcePath = testInfo.outputPath('source.ttl')
  await (await sourceDownload).saveAs(sourcePath)

  // A separate metadata file, API process and browser context form the destination.
  const destinationDir = mkdtempSync(join(process.env.KG_E2E_TEMP_DIR!, 'restore-destination-'))
  const destinationEnv = {
    ...process.env,
    KG_ENVIRONMENT: 'development',
    KG_CREATE_TABLES_ON_STARTUP: 'true',
    KG_DATABASE_URL: `sqlite:///${join(destinationDir, 'metadata.sqlite')}`,
    KG_PASSWORD_ITERATIONS: '1000',
  }
  const api = spawn(
    resolve('server/.venv/bin/uvicorn'),
    ['app.main:app', '--host', '127.0.0.1', '--port', '0'],
    {
      cwd: resolve('server'),
      env: destinationEnv,
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  )
  let output = ''
  const collect = (data: Buffer) => {
    output += data.toString()
  }
  api.stdout.on('data', collect)
  api.stderr.on('data', collect)
  const context = await browser.newContext({
    baseURL: 'http://127.0.0.1:5199',
    locale: 'zh-CN',
    viewport: { width: 1440, height: 960 },
  })
  try {
    await expect
      .poll(() => output, { timeout: 30000 })
      .toMatch(/Uvicorn running on http:\/\/127\.0\.0\.1:\d+/)
    const port = /Uvicorn running on http:\/\/127\.0\.0\.1:(\d+)/.exec(output)![1]
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
        env: destinationEnv,
        stdio: 'pipe',
        timeout: 30000,
      },
    )
    const destination = await context.newPage()
    await destination.route('**/api/v1/**', async (route) => {
      const sourceUrl = new URL(route.request().url())
      const response = await route.fetch({
        url: `http://127.0.0.1:${port}${sourceUrl.pathname}${sourceUrl.search}`,
      })
      await route.fulfill({ response })
    })
    await loginAsAdmin(destination)
    await destination.goto('/governance/export')
    await destination
      .locator('.exchange-tabs > .n-tabs-nav .n-tabs-tab')
      .filter({ hasText: '预检与导入' })
      .click()
    await destination.locator('#ontology-restore-file').setInputFiles(sourcePath)
    await destination.getByRole('button', { name: '预览导入', exact: true }).click()
    const apply = destination.getByRole('button', { name: '导入为本地新本体', exact: true })
    await expect(apply).toBeEnabled()
    await apply.click()
    await expect(destination.getByText(/已创建本体 #\d+，本地版本 r1/)).toBeVisible()
    await destination
      .locator('.exchange-tabs > .n-tabs-nav .n-tabs-tab')
      .filter({ hasText: '冻结版本与导出' })
      .click()
    const frozen = destination.locator('.n-card').filter({ hasText: '本体 r1 的冻结内容' })
    await frozen.getByRole('button', { name: '迁移人员 · r1', exact: true }).click()
    await expect(frozen).toContainText('https://example.org/transfer#TransferPerson/Name')
    const destinationDownload = destination.waitForEvent('download')
    await destination.getByRole('button', { name: '下载文件', exact: true }).click()
    const restoredPath = testInfo.outputPath('restored.ttl')
    await (await destinationDownload).saveAs(restoredPath)
    expect(readFileSync(restoredPath, 'utf8')).toContain('TransferPerson')
    execFileSync(
      resolve('server/.venv/bin/python'),
      [
        '-c',
        'import sys; from rdflib import Graph; from rdflib.compare import isomorphic; assert isomorphic(Graph().parse(sys.argv[1]), Graph().parse(sys.argv[2]))',
        sourcePath,
        restoredPath,
      ],
      { timeout: 30000 },
    )
    await destination.screenshot({
      path: testInfo.outputPath('restore-desktop.png'),
      fullPage: true,
    })
    await destination.setViewportSize({ width: 390, height: 844 })
    await expect(destination.locator('.app-sider')).toHaveClass(/n-layout-sider--collapsed/)
    await destination
      .locator('.exchange-tabs > .n-tabs-nav .n-tabs-tab')
      .filter({ hasText: '预检与导入' })
      .click()
    await apply.scrollIntoViewIfNeeded()
    await destination.screenshot({
      path: testInfo.outputPath('restore-mobile.png'),
      fullPage: true,
    })
    await destination.getByRole('button', { name: '预览导入', exact: true }).click()
    await expect(destination.getByText('RESOURCE_EXISTS', { exact: false }).first()).toBeVisible()
    await expect(apply).toBeDisabled()
  } finally {
    await context.close()
    if (api.exitCode === null && api.signalCode === null) {
      const exited = once(api, 'exit')
      api.kill('SIGTERM')
      const timer = setTimeout(() => api.kill('SIGKILL'), 5000)
      await exited
      clearTimeout(timer)
    }
  }
})
