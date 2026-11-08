import { readFile } from 'node:fs/promises'

import { capture, expect, getData, settleApi, test } from './ui-redesign-fixtures'
import type { GraphView } from '../web/src/api/graph'

const config = { registration_enabled: true, password_reset_enabled: true, password_min_length: 8 }

test('narrow navigation collapses without overwriting desktop preference', async ({
  signedIn: page,
}) => {
  await page.evaluate(() => localStorage.setItem('kg-sider-collapsed', '0'))
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/')
  const sider = page.locator('.app-sider')
  await expect(sider).not.toHaveClass(/n-layout-sider--collapsed/)
  await page.setViewportSize({ width: 900, height: 700 })
  await expect(sider).toHaveClass(/n-layout-sider--collapsed/)
  await expect.poll(async () => Math.round((await sider.boundingBox())!.width)).toBe(64)
  await page.getByRole('button', { name: '展开侧栏', exact: true }).click()
  await expect(sider).not.toHaveClass(/n-layout-sider--collapsed/)
  await page.getByRole('button', { name: '折叠侧栏', exact: true }).click()
  expect(await page.evaluate(() => localStorage.getItem('kg-sider-collapsed'))).toBe('0')
  await page.setViewportSize({ width: 1440, height: 900 })
  await expect(sider).not.toHaveClass(/n-layout-sider--collapsed/)
  await page.setViewportSize({ width: 600, height: 800 })
  await expect(sider).toHaveClass(/n-layout-sider--collapsed/)
  await expect.poll(async () => (await sider.boundingBox())!.x).toBeLessThan(0)
  await page.getByRole('button', { name: '展开侧栏', exact: true }).click()
  await expect(sider).not.toHaveClass(/n-layout-sider--collapsed/)
  await page.locator('.mobile-backdrop').click({ position: { x: 550, y: 300 } })
  await expect(sider).toHaveClass(/n-layout-sider--collapsed/)
})

test('graph refresh cancels an older expansion and allows a deliberate retry', async ({
  signedIn: page,
  identity,
  routeCatalog: catalog,
  network,
  evidence,
}, info) => {
  const source = await getData<GraphView>(
    identity.api,
    '/extraction/graph-view?graph_revision_id=' + catalog.graphId,
  )
  expect(source.nodes.length).toBeGreaterThan(1)
  const iri = source.nodes[0]!.iri
  const base = { path: '/extraction/graph-view', query: { center: '' } }
  const branch = { path: '/extraction/graph-view', query: { center: iri } }
  await network.empty(base, { ...source, nodes: source.nodes.slice(0, 1), edges: [] })
  await network.empty(branch, { ...source, nodes: source.nodes.slice(0, 2), edges: [] })
  await page.goto('/graph?graph=' + catalog.graphId)
  await expect(page.locator('.node')).toHaveCount(1)
  await expect(page.locator('.graph-workspace')).toHaveAttribute('aria-busy', 'false')
  await page.locator('.node').focus()
  await page.keyboard.press('Enter')
  const expanding = await network.hold(branch)
  await page.getByRole('button', { name: '展开关联', exact: true }).click()
  await expect.poll(expanding.hits).toBe(1)
  const refreshing = await network.hold(base)
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect.poll(refreshing.hits).toBe(1)
  expanding.release()
  await expect(page.getByRole('button', { name: '展开关联', exact: true })).toBeDisabled()
  await expect(page.locator('.node.selected')).toHaveAttribute('data-iri', iri)
  refreshing.release()
  await expect(page.locator('.graph-workspace')).toHaveAttribute('aria-busy', 'false')
  await expect(page.locator('.node')).toHaveCount(1)
  await expect(page.locator('.graph-inspector')).toBeVisible()
  await page.getByRole('button', { name: '展开关联', exact: true }).click()
  await expect(page.locator('.node')).toHaveCount(2)
  await expect(page.locator('.node.selected')).toHaveAttribute('data-iri', iri)
  await capture(
    page,
    info,
    evidence,
    'graph-concurrent-refresh',
    'real nodes with controlled subset and delayed response order',
  )
})

test('downloaded graph SVG retains light and dark paint and PNG decodes independently', async ({
  signedIn: page,
  routeCatalog: catalog,
  context,
}) => {
  await page.goto('/graph?graph=' + catalog.graphId)
  await expect(page.locator('.node').first()).toBeVisible()
  await page.locator('.node').first().focus()
  await page.keyboard.press('Enter')
  const standalone = await context.newPage()
  const paint = (element: Element) => {
    const styles = getComputedStyle(element)
    return { fill: styles.fill, stroke: styles.stroke, width: styles.strokeWidth }
  }
  try {
    for (const dark of [false, true]) {
      if (dark) await page.getByRole('button', { name: '切换到暗色模式', exact: true }).click()
      const body = await page.locator('.node-body').first().evaluate(paint)
      const label = await page.locator('.node-name').first().evaluate(paint)
      await page.getByRole('button', { name: '筛选与视图', exact: true }).click()
      await page.getByRole('button', { name: '导出', exact: true }).click()
      const download = page.waitForEvent('download')
      await page.getByText('导出 SVG', { exact: true }).click()
      const file = await download
      const svg = await readFile((await file.path())!, 'utf8')
      await standalone.setContent(svg)
      await expect(standalone.locator('.node-body').first()).toBeVisible()
      expect(await standalone.locator('.node-body').first().evaluate(paint)).toEqual(body)
      expect(await standalone.locator('.node-name').first().evaluate(paint)).toEqual(label)
      expect(svg).not.toContain('url(&quot;http')
      await page.keyboard.press('Escape')
      await expect(page.locator('.n-drawer')).toHaveCount(0)
    }
    await page.getByRole('button', { name: '筛选与视图', exact: true }).click()
    await page.getByRole('button', { name: '导出', exact: true }).click()
    const pngDownload = page.waitForEvent('download')
    await page.getByText('导出 PNG', { exact: true }).click()
    const png = await readFile((await (await pngDownload).path())!)
    await standalone.setContent(
      '<img alt="export" src="data:image/png;base64,' + png.toString('base64') + '">',
    )
    await expect
      .poll(() =>
        standalone.locator('img').evaluate((image: HTMLImageElement) => image.naturalWidth),
      )
      .toBeGreaterThan(500)
  } finally {
    await standalone.close()
  }
})

test('dashboard loading failure recovery and zero assets retain a clear next step', async ({
  signedIn: page,
  identity,
  network,
  evidence,
}, info) => {
  const target = { path: '/dashboard/stats' }
  await network.failOnce(target)
  const held = await network.hold(target)
  await page.goto('/')
  await expect(page.getByRole('status')).toBeVisible()
  held.release()
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await expect(page.locator('.pipeline li')).toHaveCount(6)
  const stats = await getData<Record<string, unknown>>(identity.api, '/dashboard/stats')
  const empty = Object.fromEntries(
    Object.entries(stats).map(([key, value]) => [key, typeof value === 'number' ? 0 : value]),
  )
  empty.current_graph_id = null
  await network.empty(target, empty)
  await page.reload()
  await expect(page.locator('.continue-work a')).toHaveAttribute('href', '/ontology/designer')
  await capture(page, info, evidence, 'dashboard-empty', 'valid zero-count statistics injection')
})

test('security pending failure retains passwords and successful response clears them', async ({
  signedIn: page,
  network,
  evidence,
}, info) => {
  await page.goto('/account/security')
  const fields = page.locator('input[type=password]')
  await fields.nth(0).fill('Temporary-old-password')
  await fields.nth(1).fill('Temporary-new-password')
  await fields.nth(2).fill('Temporary-new-password')
  const target = { path: '/users/me/password', method: 'PUT' }
  await network.empty(target, null)
  await network.failOnce(target)
  const held = await network.hold(target)
  const button = page.getByRole('button', { name: '修改密码', exact: true })
  await button.click()
  await expect.poll(held.hits).toBe(1)
  await expect(page.locator('.n-button--loading')).toBeVisible()
  held.release()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(fields.nth(0)).toHaveValue('Temporary-old-password')
  await button.click()
  await expect(fields.nth(0)).toHaveValue('')
  await capture(
    page,
    info,
    evidence,
    'security-recovered',
    'injected success; no password is changed',
  )
})

test('register configuration loading and failure are distinct from disabled registration', async ({
  page,
  network,
  evidence,
}, info) => {
  await network.empty({ path: '/auth/config' }, config)
  await network.failOnce({ path: '/auth/config' })
  const pending = await network.hold({ path: '/auth/config' })
  await page.goto('/register')
  await expect(page.getByRole('status')).toBeVisible()
  pending.release()
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await expect(page.getByRole('button', { name: '注册', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '注册', exact: true }).click()
  await expect(page.locator('.n-form-item-feedback').first()).toBeVisible()
  await page.getByLabel('用户名', { exact: true }).fill('ui_auxiliary')
  await page.getByLabel('邮箱', { exact: true }).fill('auxiliary@example.org')
  await page.getByLabel('密码', { exact: true }).fill('Temporary-UI-2026')
  await page.getByLabel('确认密码', { exact: true }).fill('Temporary-UI-2026')
  await network.failOnce({ path: '/auth/register', method: 'POST' }, 409, 'AUTH.USERNAME_EXISTS')
  const submit = await network.hold({ path: '/auth/register', method: 'POST' })
  await page.getByLabel('确认密码', { exact: true }).press('Enter')
  await expect.poll(submit.hits).toBe(1)
  await expect(page.locator('.n-button--loading')).toBeVisible()
  submit.release()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByLabel('用户名', { exact: true })).toHaveValue('ui_auxiliary')
  await capture(
    page,
    info,
    evidence,
    'register-error',
    'enabled config and conflict are explicit injections; no account created',
  )
})

test('forgot password enabled form preserves errors and disables repeated completed requests', async ({
  page,
  network,
  evidence,
}, info) => {
  await network.empty({ path: '/auth/config' }, config)
  await page.goto('/forgot-password')
  const submitButton = page.getByRole('button', { name: '发送重置链接', exact: true })
  await submitButton.click()
  await expect(page.locator('.n-form-item-feedback')).toBeVisible()
  await page.locator('input').first().fill('auxiliary@example.org')
  const target = { path: '/auth/forgot-password', method: 'POST' }
  await network.empty(target, { reset_token: null })
  await network.failOnce(target)
  const pending = await network.hold(target)
  await submitButton.click()
  await expect.poll(pending.hits).toBe(1)
  await expect(page.locator('.n-button--loading')).toBeVisible()
  pending.release()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.locator('input').first()).toHaveValue('auxiliary@example.org')
  await submitButton.click()
  await expect(submitButton).toBeDisabled()
  await capture(page, info, evidence, 'forgot-sent', 'injected provider response; no email sent')
})

test('reset password missing token, pending request and failed token preserve form', async ({
  page,
  network,
  evidence,
}, info) => {
  await page.goto('/reset-password')
  const button = page.getByRole('button', { name: '确认重置', exact: true })
  await expect(button).toBeDisabled()
  await page.goto('/reset-password?token=explicit-ui-fixture')
  await page.locator('input[type=password]').nth(0).fill('Temporary-UI-2026')
  await page.locator('input[type=password]').nth(1).fill('Temporary-UI-2026')
  const target = { path: '/auth/reset-password', method: 'POST' }
  await network.empty(target, null)
  await network.failOnce(target, 400, 'AUTH.RESET_TOKEN_INVALID')
  const pending = await network.hold(target)
  await page.locator('input[type=password]').nth(1).press('Enter')
  await expect.poll(pending.hits).toBe(1)
  await expect(page.locator('.n-button--loading')).toBeVisible()
  pending.release()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.locator('input[type=password]').first()).toHaveValue('Temporary-UI-2026')
  await capture(page, info, evidence, 'reset-error', 'injected invalid token; no password changed')
  await button.click()
  await expect(page).toHaveURL(/\/login$/)
})

test('entity evidence failure keeps attributes and returns through detail to the exact list query', async ({
  signedIn: page,
  routeCatalog: data,
  network,
  evidence,
}, info) => {
  await network.failOnce({ path: '/extraction/evidence/trace/entity' })
  const params = new URLSearchParams({
    graph: String(data.graphId),
    q: data.entityIri,
    page: '1',
    size: '25',
    sort: '-iri',
  })
  await page.goto('/graph/entities/' + encodeURIComponent(data.entityIri) + '?' + params)
  await expect(page.locator('.iri')).toHaveText(data.entityIri)
  await expect(page.locator('.n-data-table')).toBeVisible()
  await page.locator('.n-tabs-tab[data-name="evidence"]').click()
  await expect(page.locator('.n-alert')).toBeVisible()
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await expect(page.locator('.n-alert')).toHaveCount(0)
  await page
    .getByRole('link', { name: '证据溯源链（事实 → 来源行 → 运行 → 冻结版本）', exact: true })
    .click()
  await page.getByRole('link', { name: '返回对象', exact: true }).click()
  await page.getByRole('link', { name: '返回列表位置', exact: true }).click()
  const current = new URL(page.url())
  for (const [key, value] of params) expect(current.searchParams.get(key)).toBe(value)
  await capture(
    page,
    info,
    evidence,
    'entity-context-restored',
    'real graph entity and evidence; one injected 503',
  )
})

test('new type drawer protects unsaved input and restores cancellation focus', async ({
  signedIn: page,
  entityCatalog,
  evidence,
}, info) => {
  void entityCatalog
  await page.goto('/ontology/entity-types')
  await page.getByRole('button', { name: '创建', exact: true }).click()
  const name = page.locator('.n-drawer').getByPlaceholder('Employee', { exact: true })
  await name.fill('UnsavedType')
  page.once('dialog', (dialog) => dialog.dismiss())
  await page.locator('.n-drawer').getByRole('button', { name: '取消', exact: true }).click()
  await expect(name).toHaveValue('UnsavedType')
  await capture(page, info, evidence, 'unsaved-retained', 'cancel close retains draft')
  page.once('dialog', (dialog) => dialog.accept())
  await page.locator('.n-drawer').getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.locator('.n-drawer')).toHaveCount(0)
})

test.describe('VIEWER navigation and page search', () => {
  test.use({ role: 'VIEWER' })
  test('page search excludes admin destinations and old routes remain usable', async ({
    signedIn: page,
    evidence,
  }, info) => {
    await page.goto('/ontology')
    await expect(page).toHaveURL(/\/ontology\/entity-types/)
    await page.keyboard.press('Control+k')
    const search = page.getByPlaceholder('搜索页面 · ⌘/Ctrl K', { exact: true })
    await expect(search).toBeFocused()
    await search.fill('用户')
    await expect(page.locator('.n-auto-complete-option')).toHaveCount(0)
    await page.locator('.quick-search .n-base-clear').click()
    await expect(search).toHaveValue('')
    await search.fill('数据源')
    await page.getByText('数据源', { exact: true }).last().click()
    await expect(page).toHaveURL(/\/datasources$/)
    await page.goto('/system/users')
    await expect(page).toHaveURL(/\/forbidden\?redirect=/)
    await page.getByRole('button', { name: '刷新权限', exact: true }).click()
    await settleApi(page, evidence)
    await expect(page).toHaveURL(/\/forbidden/)
    await capture(
      page,
      info,
      evidence,
      'viewer-search-permissions',
      'real VIEWER and route authorization',
    )
  })
})
