import { execFileSync } from 'node:child_process'
import { join, resolve } from 'node:path'

import { expect, test, type Page } from '@playwright/test'

import { ADMIN, ensureAdmin, loginAsAdmin } from './admin'

async function pickOption(page: Page, label: string): Promise<void> {
  await page
    .locator('.n-base-select-option:visible')
    .filter({ has: page.getByText(label, { exact: true }) })
    .last()
    .click()
}

async function publishAndRun(page: Page) {
  await page.locator('.wizard-footer').getByRole('button', { name: '保存并预览' }).click()
  await expect(page.getByText('当前样例没有发现字段错误。')).toBeVisible()
  await page.locator('.wizard-footer').getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '发布映射' }).click()
  await expect(page.getByText(/映射 rev\./)).toBeVisible()
  const response = page.waitForResponse(
    (res) => res.url().endsWith('/api/v1/extraction/runs') && res.request().method() === 'POST',
  )
  await page.getByRole('button', { name: '启动抽取' }).click()
  const result = await response
  expect(result.ok(), await result.text()).toBeTruthy()
  await expect(page.getByText(/运行编号 #/)).toBeVisible()
  return (await result.json()).data
}

test('UI policies select and quarantine conflicting values with frozen source explanations', async ({
  page,
}, testInfo) => {
  await ensureAdmin(page)
  const login = await page.request.post('/api/v1/auth/login', { data: ADMIN })
  const headers = { Authorization: `Bearer ${(await login.json()).data.access_token}` }
  const sourcePath = join(process.env.KG_E2E_TEMP_DIR!, 'fusion-source.sqlite')
  execFileSync(
    resolve('server/.venv/bin/python'),
    [
      '-c',
      `import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as conn:
    conn.executescript("""
    CREATE TABLE fusion_customer(id INTEGER PRIMARY KEY, code TEXT, name TEXT, secret TEXT);
    CREATE TABLE fusion_supplier(id INTEGER PRIMARY KEY, code TEXT, name TEXT, secret TEXT);
    INSERT INTO fusion_customer VALUES (1,'C1','First','unmapped-secret'),(2,'C2','Same','unmapped-secret');
    INSERT INTO fusion_supplier VALUES (10,'C1','Second','unmapped-secret'),(20,'C2','Same','unmapped-secret');
    """)`,
      sourcePath,
    ],
    { timeout: 30000 },
  )
  // Synthetic assets are prepared via real APIs; policies, publication and runs use UI.
  const ns = await page.request.post('/api/v1/namespaces', {
    headers,
    data: { prefix: 'fusion_ui', iri: 'https://example.org/fusion-ui#' },
  })
  expect(ns.ok(), await ns.text()).toBeTruthy()
  const entity = await page.request.post('/api/v1/entity-types', {
    headers,
    data: {
      name: 'FusionPartner',
      namespace_id: (await ns.json()).data.id,
      label_i18n: { 'zh-CN': '融合伙伴' },
      data_props: [{ name: 'Name', datatype: 'string', nullable: true }],
    },
  })
  expect(entity.ok(), await entity.text()).toBeTruthy()
  const entityId = (await entity.json()).data.id
  expect(
    (await page.request.post(`/api/v1/entity-types/${entityId}/publish`, { headers })).ok(),
  ).toBeTruthy()
  const ontology = await page.request.post('/api/v1/ontologies', {
    headers,
    data: {
      name: 'FusionUiOntology',
      iri: 'https://example.org/fusion-ui/instances#',
      label_i18n: { 'zh-CN': '融合测试本体' },
      ref_resource_ids: [entityId],
    },
  })
  expect(ontology.ok(), await ontology.text()).toBeTruthy()
  const onto = (await ontology.json()).data
  expect(
    (
      await page.request.post(`/api/v1/ontologies/${onto.id}/publish`, {
        headers: { ...headers, 'If-Edit-Match': String(onto.edit_revision) },
      })
    ).ok(),
  ).toBeTruthy()
  const source = await page.request.post('/api/v1/datasources', {
    headers,
    data: { name: '融合测试源', kind: 'sqlite', params: { database: sourcePath } },
  })
  expect(source.ok(), await source.text()).toBeTruthy()

  await loginAsAdmin(page)
  await page.goto('/extraction')
  await page.locator('.step-content input').first().fill('FusionUiMapping')
  await page.locator('.step-content .n-base-selection').first().click()
  await pickOption(page, '融合测试本体 · FusionUiOntology')
  await page.locator('.wizard-footer').getByRole('button', { name: '下一步' }).click()
  await page.locator('.datasource-form .n-base-selection').first().click()
  await pickOption(page, '融合测试源 · sqlite')
  await page.getByRole('button', { name: '采集元数据' }).click()
  await expect(page.locator('.catalog-summary')).toContainText('2')
  await page.locator('.wizard-footer').getByRole('button', { name: '下一步' }).click()
  for (const [index, table] of ['fusion_customer', 'fusion_supplier'].entries()) {
    await page.getByTestId('add-entity-mapping').click()
    const editor = page.getByTestId('entity-mapping').nth(index)
    await editor.getByTestId('entity-source-table').click()
    await pickOption(page, 'main.' + table)
    await editor.getByTestId('field-source').click()
    await pickOption(page, 'name · TEXT')
    await editor.getByTestId('entity-row-key').and(page.locator('[aria-label$=" id"]')).check()
    await editor.getByTestId('entity-match-key').and(page.locator('[aria-label$=" code"]')).check()
    await editor
      .getByTestId('fusion-priority')
      .locator('input')
      .fill(String(index + 1))
    await editor.getByTestId('fusion-null-policy').click()
    await pickOption(page, '忽略空值')
    await editor.getByTestId('fusion-conflict-policy').click()
    await pickOption(page, '按来源优先级选值')
  }
  await page
    .getByTestId('fusion-policy')
    .last()
    .screenshot({
      path: testInfo.outputPath('fusion-policy.png'),
    })
  const first = await publishAndRun(page)
  expect(first.run.status).toBe('SUCCESS')
  const iri = 'https://example.org/fusion-ui/instances#FusionPartner/C1'
  const evidenceUrl = `/graph/evidence?iri=${encodeURIComponent(iri)}&graph=${first.graph_revision.id}`
  await page.goto(evidenceUrl)
  const evidence = page.getByTestId('fusion-evidence')
  const attribute = evidence.locator('[data-attribute="Name"]')
  await expect(attribute).toContainText('最终值： "First"')
  await expect(attribute).toContainText('来源优先级决定最终值')
  await expect(attribute).toContainText('"Second"')
  await expect(attribute).toContainText('fusion_customer')
  await expect(attribute).toContainText('fusion_supplier')
  await expect(evidence).not.toContainText('unmapped-secret')
  await evidence.screenshot({ path: testInfo.outputPath('fusion-evidence-desktop.png') })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.locator('.app-sider')).toHaveClass(/n-layout-sider--collapsed/)
  await evidence.scrollIntoViewIfNeeded()
  expect((await evidence.boundingBox())!.width).toBeLessThanOrEqual(390)
  const candidates = evidence.locator('.candidate-scroll')
  await candidates.evaluate((element) => {
    element.scrollLeft = element.scrollWidth
  })
  await expect(candidates.getByRole('cell', { name: '已选用', exact: true })).toBeInViewport()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await evidence.screenshot({ path: testInfo.outputPath('fusion-evidence-mobile.png') })
  await page.setViewportSize({ width: 1440, height: 960 })

  await page.goto('/extraction')
  await page.locator('.mapping-picker').click()
  await pickOption(page, 'FusionUiMapping · 已发布')
  await page.getByRole('button', { name: '复制为新草稿' }).click()
  await page.locator('.wizard-footer').getByRole('button', { name: '下一步' }).click()
  await page.locator('.datasource-form .n-base-selection').first().click()
  await pickOption(page, '融合测试源 · sqlite')
  await page.locator('.wizard-footer').getByRole('button', { name: '下一步' }).click()
  for (let index = 0; index < 2; index++) {
    const editor = page.getByTestId('entity-mapping').nth(index)
    await expect(editor.getByTestId('fusion-priority').locator('input')).toHaveValue(
      String(index + 1),
    )
    await editor.getByTestId('fusion-conflict-policy').click()
    await pickOption(page, '不同值隔离整个实体')
  }
  const quarantined = await publishAndRun(page)
  expect(quarantined.run.status).toBe('PARTIAL')
  await page.goto(
    `/graph/evidence?iri=${encodeURIComponent(iri)}&graph=${quarantined.graph_revision.id}`,
  )
  await expect(evidence).toContainText('整个实体已隔离')
  await expect(attribute).toContainText('不同值触发冲突隔离')
  await expect(attribute).toContainText('未产出值')
  await expect(attribute).toContainText('"First"')
  await expect(attribute).toContainText('"Second"')
  await evidence.screenshot({ path: testInfo.outputPath('fusion-quarantined.png') })
  // A later policy run must not alter the earlier value or explanation.
  await page.goto(evidenceUrl)
  await expect(attribute).toContainText('最终值： "First"')
  await expect(attribute).toContainText('来源优先级决定最终值')
})
