import { expect, test } from '@playwright/test'

import { ensureAdmin, loginAsAdmin } from './admin'

test('admin searches retained asset versions and safely retries failed reads', async ({
  page,
}, testInfo) => {
  await ensureAdmin(page)
  await loginAsAdmin(page)
  const created = await page.evaluate(async () => {
    const { http } = await import('/src/api/client.ts')
    const result = await http.post('/ontologies', {
      name: 'AuditBrowserAsset',
      iri: 'https://example.org/audit-browser',
      label_i18n: { 'zh-CN': '不应进入审计的正文' },
    })
    await http.put(`/ontologies/${result.data.id}`, {
      if_match: 0,
      if_edit_match: 0,
      definition_i18n: { 'zh-CN': '不应进入审计的正文' },
    })
    return { id: result.data.id, correlation: result.headers['x-correlation-id'] }
  })
  await page.goto('/system/audit-logs')
  const panel = page.locator('.asset-audit')
  await expect(panel.getByText('业务资产审计', { exact: true })).toBeVisible()
  await expect(panel.getByRole('cell', { name: '编辑', exact: true })).toBeVisible()
  await expect(panel).not.toContainText('不应进入审计的正文')
  await panel.getByPlaceholder('操作者 ID、对象 ID 或关联 ID').fill(created.correlation)
  await panel.getByRole('button', { name: '搜索', exact: true }).click()
  await expect(panel).toContainText('共 1 条记录')
  await expect(panel.getByRole('cell', { name: '创建', exact: true })).toBeVisible()
  await expect(panel.getByRole('cell', { name: '编辑', exact: true })).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath('asset-audit-desktop.png'), fullPage: true })
  await page.route('**/api/v1/asset-audit-logs?**', (route) =>
    route.fulfill({
      status: 503,
      json: { code: 'KG.DATABASE_ERROR', message: '', data: null, params: {} },
    }),
  )
  await panel.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(panel.getByRole('alert')).toContainText('审计记录加载失败')
  await expect(panel.getByRole('cell', { name: '创建', exact: true })).toHaveCount(0)
  await page.unroute('**/api/v1/asset-audit-logs?**')
  await panel.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(panel).toContainText('共 1 条记录')
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.locator('.app-sider')).toHaveClass(/n-layout-sider--collapsed/)
  await expect(panel.getByRole('button', { name: '搜索', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  )
  await page.screenshot({ path: testInfo.outputPath('asset-audit-mobile.png'), fullPage: true })
})
