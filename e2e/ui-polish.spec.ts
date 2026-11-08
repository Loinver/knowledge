import {
  attachJson,
  capture,
  expect,
  getData,
  responseData,
  settleApi,
  test,
} from './ui-redesign-fixtures'
import type { AuthUser } from '../web/src/api/auth'
import type { DatasourceOut } from '../web/src/api/datasources'
import type { GraphView } from '../web/src/api/graph'

const longName = 'InternationalKnowledgePlatformEntity'.repeat(5)
const longKey = 'upstream_source_system_business_identifier'

test('graph visual selection preserves forward and reverse keyboard traversal', async ({
  signedIn: page,
  routeCatalog: data,
}) => {
  await page.goto('/graph?graph=' + data.graphId)
  const nodes = page.locator('.canvas-scroll .node')
  await expect(nodes.first()).toBeVisible()
  const order = await nodes.evaluateAll((items) => items.map((el) => el.getAttribute('data-iri')!))
  const node = (index: number) => page.locator(`.canvas-scroll .node[data-iri="${order[index]}"]`)
  await node(0).focus()
  await node(0).press('Enter')
  for (const index of [1, 2, 3]) {
    await page.keyboard.press('Tab')
    await expect(node(index)).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(node(index)).toHaveAttribute('aria-pressed', 'true')
  }
  for (const index of [2, 1, 0]) {
    await page.keyboard.press('Shift+Tab')
    await expect(node(index)).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(node(index)).toHaveAttribute('aria-pressed', 'true')
  }
  await page.keyboard.press('Shift+Tab')
  await expect(page.locator('.canvas-scroll')).toBeFocused()
  await node(order.length - 1).focus()
  await page.keyboard.press('Enter')
  await page.keyboard.press('Tab')
  await expect(
    page.locator('.graph-inspector').getByRole('button', { name: '关闭', exact: true }),
  ).toBeFocused()
  await node(0).focus()
  await node(0).press('Enter')
  await node(order.length - 1).focus()
  await page.keyboard.press('Tab')
  for (const index of [order.length - 1, order.length - 2]) {
    await page.keyboard.press('Shift+Tab')
    await expect(node(index)).toBeFocused()
  }
  await node(0).focus()
  await page.keyboard.press('Shift+Tab')
  await page.keyboard.press('Tab')
  await expect(node(0)).toBeFocused()
})

test('user edit failure stays in the dialog and a real retry restores the list', async ({
  signedIn: page,
  identity,
  network,
  evidence,
}, info) => {
  const username = 'polish_' + Date.now()
  const user = await responseData<AuthUser>(
    await identity.api.post('/api/v1/users', {
      data: {
        username,
        email: username + '@example.org',
        password: 'Test-Password-2026!',
        role: 'EDITOR',
      },
    }),
  )
  await page.goto('/system/users')
  await page.getByPlaceholder('按用户名或邮箱搜索').fill(username)
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  const row = page.locator('tr').filter({ hasText: username })
  await row.getByRole('button', { name: '编辑', exact: true }).click()
  const dialog = page.locator('.n-modal:visible')
  const role = dialog.locator('.n-form-item').filter({ hasText: '角色' })
  await role.locator('.n-base-selection').click()
  await page.locator('.n-base-select-option:visible').filter({ hasText: '只读' }).click()
  await network.failOnce({ path: '/users/' + user.id, method: 'PATCH' })
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await settleApi(page, evidence)
  await capture(page, info, evidence, 'user-edit-error', 'injected 503; changed role is preserved')
  await expect.poll(async () => (await dialog.boundingBox())?.width).toBe(480)
  await expect.soft(dialog.locator('.n-alert')).toBeVisible()
  await expect.soft(row).toBeVisible()
  await expect(role).toContainText('只读')
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog).toBeHidden()
  await expect(row.getByText('只读', { exact: true })).toBeVisible()
  await expect(page.locator('.n-alert')).toHaveCount(0)
  await page.setViewportSize({ width: 1024, height: 768 })
  await row.getByRole('button', { name: '编辑', exact: true }).click()
  await expect.poll(async () => (await dialog.boundingBox())?.width).toBe(480)
  await expect(dialog.getByRole('button', { name: '保存', exact: true })).toBeInViewport()
})

test('connection feedback belongs to the current parameters and ignores delayed results', async ({
  signedIn: page,
  identity,
  routeCatalog: data,
  network,
  evidence,
}, info) => {
  const source = await getData<DatasourceOut>(identity.api, '/datasources/' + data.datasourceId)
  await page.goto('/datasources')
  await page.getByRole('button', { name: '新建数据源', exact: true }).click()
  const dialog = page.locator('.n-modal:visible')
  const database = dialog.getByRole('textbox', { name: '数据库', exact: true })
  const testButton = dialog.getByRole('button', { name: '测试连接', exact: true })
  const success = dialog.getByRole('alert').filter({ hasText: /发现 \d+ 张表/ })
  await dialog.getByRole('textbox', { name: '名称', exact: true }).fill('连接反馈验收')
  await database.fill(String(source.params.database))
  await testButton.click()
  await expect(success).toContainText('张表')
  await database.fill(String(source.params.database) + '.changed')
  await capture(
    page,
    info,
    evidence,
    'connection-parameters',
    'actual successful connection followed by a database parameter change',
  )
  await expect.poll(async () => (await dialog.boundingBox())?.width).toBe(640)
  await expect.soft(success).toHaveCount(0)
  await database.fill(String(source.params.database))
  const hold = await network.hold({ path: '/datasources/test-connection', method: 'POST' })
  await testButton.click()
  await expect.poll(hold.hits).toBe(1)
  await database.fill(String(source.params.database) + '.changed')
  // Returning to A must not revive the old request for A.
  await database.fill(String(source.params.database))
  hold.release()
  await settleApi(page, evidence)
  await expect(success).toHaveCount(0)
  await expect(testButton).toBeEnabled()
  await testButton.click()
  await expect(success).toContainText('张表')
  await page.setViewportSize({ width: 1024, height: 768 })
  await expect.poll(async () => (await dialog.boundingBox())?.width).toBe(640)
  await expect(dialog.getByRole('button', { name: '保存', exact: true })).toBeInViewport()
})

test('graph gestures, panel resize and refresh preserve the existing view', async ({
  signedIn: page,
  routeCatalog: data,
  evidence,
}, info) => {
  await page.goto('/graph?graph=' + data.graphId)
  const viewport = page.locator('.canvas-scroll')
  const node = viewport.locator(`.node[data-iri="${data.entityIri}"]`)
  await expect(node).toBeVisible()
  const zoom = page.locator('.zoom-value')
  const initialZoom = await zoom.textContent()
  const initialPoint = await node.boundingBox()
  await viewport.hover({ position: { x: 100, y: 150 } })
  await page.mouse.wheel(40, 60)
  await expect.poll(async () => (await node.boundingBox())!.y).not.toBe(initialPoint!.y)
  await expect(zoom).toHaveText(initialZoom!)
  await page.keyboard.down('Control')
  await page.mouse.wheel(0, -100)
  await page.keyboard.up('Control')
  await expect(zoom).not.toHaveText(initialZoom!)
  await page.getByRole('button', { name: '适应视图', exact: true }).click()
  await node.focus()
  await node.press('Enter')
  await expect(page.locator('.graph-inspector')).toBeVisible()
  const selectedZoom = await zoom.textContent()
  const position = await node.getAttribute('transform')
  const canvasWidth = await viewport.evaluate((el) => el.clientWidth)
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await settleApi(page, evidence)
  await expect(node).toHaveAttribute('aria-pressed', 'true')
  await expect(node).toHaveAttribute('transform', position!)
  await expect(zoom).toHaveText(selectedZoom!)
  await page.locator('.graph-inspector').getByRole('button', { name: '关闭', exact: true }).click()
  await expect.poll(() => viewport.evaluate((el) => el.clientWidth)).toBeGreaterThan(canvasWidth)
  await expect(zoom).toHaveText(selectedZoom!)
  await expect(node).toHaveAttribute('transform', position!)
  await capture(
    page,
    info,
    evidence,
    'graph-gestures',
    'real graph; wheel pan, Ctrl zoom, refresh and inspector resize',
  )
})

for (const count of [120, 500]) {
  test(`graph supported size ${count} retains distinct parallel reverse and self edges`, async ({
    signedIn: page,
    routeCatalog: data,
    identity,
    network,
    evidence,
  }, info) => {
    const graph = await getData<GraphView>(
      identity.api,
      '/extraction/graph-view?graph_revision_id=' + data.graphId,
    )
    graph.nodes = Array.from({ length: count }, (_, index) => ({
      ...graph.nodes[0],
      id: index + 1,
      iri: `https://example.org/ui-density/entity/${index}`,
      type_iri: `https://example.org/ui-density/Type${index % 4}`,
      attrs: { name: index % 2 ? `Entity ${index} / 业务对象` : `业务对象 ${index}` },
    }))
    graph.entity_total = count
    graph.truncated = count === 500
    const pairs = [
      [0, 1],
      [0, 1],
      [1, 0],
      [0, 0],
      [0, 0],
    ]
    for (let index = 1; index < count - 10; index++) pairs.push([index, index + 1])
    graph.edges = pairs.map(([subject, object], index) => ({
      id: index + 1,
      graph_revision_id: graph.graph_revision_id,
      subject: graph.nodes[subject].iri,
      object_: graph.nodes[object].iri,
      predicate: `https://example.org/ui-density/${index < 5 ? `SpecialRelation${index}` : 'relatedTo'}`,
      kind: index === 1 ? 'DERIVED' : 'DIRECT',
      props: {},
    }))
    await network.empty({ path: '/extraction/graph-view' }, graph)
    const started = performance.now()
    await page.goto('/graph?graph=' + data.graphId)
    const nodes = page.locator('.canvas-scroll .node')
    await expect(nodes).toHaveCount(count)
    const renderMs = performance.now() - started
    await expect(page.locator('.edge-group')).toHaveCount(graph.edges.length)
    const specialPaths = await page
      .locator('.edge-group .edge')
      .evaluateAll((paths) => paths.slice(0, 5).map((el) => el.getAttribute('d')))
    expect(new Set(specialPaths).size).toBe(5)
    await nodes.first().focus()
    await nodes.first().press('Enter')
    await expect(page.locator('.graph-inspector h2')).toHaveText('业务对象 0')
    await expect(page.locator('.node[aria-pressed="true"] .node-name')).toBeVisible()
    const activeNode = page.locator('.node[aria-pressed="true"]')
    await expect(activeNode).toBeFocused()
    const hitsSelected = await activeNode.evaluate((node) => {
      const rect = node.querySelector('.node-body')!.getBoundingClientRect()
      return [-0.2, 0, 0.2].every((dx) =>
        [-0.2, 0, 0.2].every((dy) => {
          const hit = document.elementFromPoint(
            rect.x + rect.width * (0.5 + dx),
            rect.y + rect.height * (0.5 + dy),
          )
          return hit?.closest('.node') === node
        }),
      )
    })
    expect(
      hitsSelected,
      'the selected node stays readable and clickable above the dense graph',
    ).toBe(true)
    const loops = await page
      .locator('.edge-group')
      .filter({ hasText: 'SpecialRelation3' })
      .locator('.edge-label')
      .boundingBox()
    const otherLoop = await page
      .locator('.edge-group')
      .filter({ hasText: 'SpecialRelation4' })
      .locator('.edge-label')
      .boundingBox()
    expect(Math.abs(loops!.y - otherLoop!.y)).toBeGreaterThan(20)
    await attachJson(info, 'density-observations', {
      nodes: count,
      edges: graph.edges.length,
      isolatedNodes: 9,
      navigationToRenderedMs: Math.round(renderMs),
      mode: 'controlled graph fixture, real browser rendering; includes navigation and API overhead',
    })
    await capture(
      page,
      info,
      evidence,
      `graph-density-${count}`,
      'controlled graph with isolated nodes, reverse/parallel edges, two self loops and selected label',
    )
  })
}

test('designer Escape cancels pointer drag from toolbar focus and exposes complete IRI', async ({
  signedIn: page,
  routeCatalog: data,
  evidence,
}, info) => {
  await page.goto('/ontology/designer?ontology=' + data.ontology.id)
  const node = page.locator('.designer .node').first()
  await expect(node).toBeVisible()
  await node.focus()
  await node.press('Enter')
  await expect(page.locator('.inspect-iri')).toBeVisible()
  await capture(page, info, evidence, 'designer-inspector', 'real ontology and resource IRI')
  const iri = await page
    .locator('.inspect-iri')
    .evaluate((el) => ({ width: el.clientWidth, content: el.scrollWidth }))
  expect.soft(iri.content).toBeLessThanOrEqual(iri.width + 1)
  const original = await node.getAttribute('style')
  await page.locator('.view-toolbar button').first().focus()
  const bounds = (await node.boundingBox())!
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2)
  await page.mouse.down()
  await page.mouse.move(bounds.x + bounds.width / 2 + 70, bounds.y + bounds.height / 2 + 35)
  await expect(node).not.toHaveAttribute('style', original!)
  await page.keyboard.press('Escape')
  await page.mouse.up()
  await expect(node).toHaveAttribute('style', original!)
  const canvas = page.locator('.designer .canvas')
  const world = page.locator('.designer .world')
  const originalView = await world.getAttribute('style')
  await page.locator('.view-toolbar button').first().focus()
  const area = (await canvas.boundingBox())!
  await page.mouse.move(area.x + 20, area.y + 20)
  await page.mouse.down()
  await page.mouse.move(area.x + 60, area.y + 50)
  await expect(world).not.toHaveAttribute('style', originalView!)
  await page.keyboard.press('Escape')
  await page.mouse.up()
  await expect(world).toHaveAttribute('style', originalView!)
})

test('narrow mapping scroll keeps step navigation above its content', async ({
  signedIn: page,
  routeCatalog: data,
  evidence,
}, info) => {
  await page.setViewportSize({ width: 900, height: 720 })
  await page.goto('/extraction?mapping=' + data.mappingId)
  await page.locator('.wizard-step').nth(2).click()
  await settleApi(page, evidence)
  await page.locator('.step-content').hover()
  await page.mouse.wheel(0, 450)
  const heading = page.locator('.wizard-heading')
  await expect(heading).toBeVisible()
  await capture(
    page,
    info,
    evidence,
    'mapping-narrow-scroll',
    'published mapping, step 3, scroll 450px',
  )
  const unobscured = await heading.evaluate((el) => {
    const rect = el.getBoundingClientRect()
    return el.contains(document.elementFromPoint(rect.x + rect.width / 2, rect.bottom - 12))
  })
  expect(unobscured, 'mapping context remains visible above scrolled content').toBe(true)
  const target = page.locator('.wizard-step').nth(1)
  await target.click({ trial: true })
  await target.click()
  await expect(target).toHaveClass(/active/)
})

test('graph panel Escape preserves selection and closing inspector restores node focus', async ({
  signedIn: page,
  routeCatalog: data,
  evidence,
}, info) => {
  await page.goto('/graph?graph=' + data.graphId)
  const node = page.locator(`.canvas-scroll .node[data-iri="${data.entityIri}"]`)
  await node.focus()
  await node.press('Enter')
  await expect(page.locator('.graph-inspector')).toBeVisible()
  await page.getByRole('button', { name: '图例', exact: true }).click()
  await capture(
    page,
    info,
    evidence,
    'graph-legend-selected',
    'real graph, selected node and legend',
  )
  await page.keyboard.press('Escape')
  await expect(page.locator('.legend-panel')).toHaveCount(0)
  await expect(page.locator('.graph-inspector')).toBeVisible()
  await expect(node).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: '小地图', exact: true }).click()
  await expect(page.locator('.minimap-panel')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.locator('.minimap-panel')).toHaveCount(0)
  await expect(node).toHaveAttribute('aria-pressed', 'true')
  const originalPosition = await node.getAttribute('transform')
  const box = (await node.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 40, box.y + box.height / 2 + 30)
  await expect(node).not.toHaveAttribute('transform', originalPosition!)
  await page.keyboard.press('Escape')
  await page.mouse.up()
  await expect(node).toHaveAttribute('transform', originalPosition!)
  await expect(node).toHaveAttribute('aria-pressed', 'true')
  await page.locator('.graph-inspector').getByRole('button', { name: '关闭', exact: true }).click()
  await expect(page.locator('.graph-inspector')).toHaveCount(0)
  await expect(node).toBeFocused()
  await node.press('Enter')
  await page.getByRole('button', { name: '追溯证据', exact: true }).click()
  await settleApi(page, evidence)
  await page
    .locator('.graph-inspector')
    .getByRole('button', { name: '返回对象', exact: true })
    .click()
  await expect(page.getByRole('button', { name: '追溯证据', exact: true })).toBeFocused()
})

test('long relation details retain all fields in a narrow desktop', async ({
  signedIn: page,
  routeCatalog: data,
  identity,
  network,
  evidence,
}, info) => {
  await page.setViewportSize({ width: 1024, height: 768 })
  const relation = await getData<Record<string, unknown>>(
    identity.api,
    '/relations/' + data.relation.id,
  )
  await network.empty(
    { path: '/relations/' + data.relation.id },
    {
      ...relation,
      label_i18n: { 'zh-CN': longName, 'en-US': longName },
    },
  )
  await page.goto('/ontology/relation-types/' + data.relation.id)
  await expect(page.locator('.page-header h1')).toHaveText(longName)
  const dimensions = await page
    .locator('.n-descriptions-table')
    .first()
    .evaluate((el) => ({
      width: el.getBoundingClientRect().width,
      containerWidth: el.parentElement!.getBoundingClientRect().width,
    }))
  expect(dimensions.width).toBeLessThanOrEqual(dimensions.containerWidth + 1)
  await capture(
    page,
    info,
    evidence,
    'relation-long-details',
    'controlled long relation label; real relation data',
  )
})

for (const viewport of [
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
]) {
  test(`long graph content remains inside inspector at ${viewport.width}`, async ({
    signedIn: page,
    identity,
    routeCatalog: data,
    network,
    evidence,
  }, info) => {
    await page.setViewportSize(viewport)
    const graph = await getData<GraphView>(
      identity.api,
      '/extraction/graph-view?graph_revision_id=' + data.graphId,
    )
    graph.nodes[0].attrs = { name: longName, [longKey]: 'Source value / 来源值' }
    await network.empty({ path: '/extraction/graph-view' }, graph)
    await page.goto('/graph?graph=' + data.graphId)
    await page.locator('.canvas-scroll .node').first().focus()
    await page.locator('.canvas-scroll .node').first().press('Enter')
    await expect(page.locator('.graph-inspector h2')).toHaveText(longName)
    await capture(
      page,
      info,
      evidence,
      'graph-long-content',
      'real graph with controlled long name and attribute key',
    )
    const metrics = await page.locator('.graph-inspector').evaluate((panel) => {
      const heading = panel.querySelector('h2')!
      const key = [...panel.querySelectorAll('dt')].find((el) => el.textContent!.length > 20)!
      return {
        headingWidth: heading.clientWidth,
        headingContent: heading.scrollWidth,
        keyWidth: key.clientWidth,
        keyContent: key.scrollWidth,
        panelWidth: panel.clientWidth,
        panelContent: panel.scrollWidth,
      }
    })
    await attachJson(info, 'long-content-metrics', metrics)
    expect.soft(metrics.headingContent).toBeLessThanOrEqual(metrics.headingWidth + 1)
    expect.soft(metrics.keyContent).toBeLessThanOrEqual(metrics.keyWidth + 1)
    expect.soft(metrics.panelContent).toBeLessThanOrEqual(metrics.panelWidth + 1)
    await page.getByRole('button', { name: '筛选与视图', exact: true }).click()
    await page.getByRole('button', { name: '中心性排行', exact: true }).click()
    await expect(
      page.locator('.n-drawer:visible').getByText(longName, { exact: true }),
    ).toBeVisible()
  })

  test(`English long resource title keeps actions reachable at ${viewport.width}`, async ({
    signedIn: page,
    entityCatalog: data,
    identity,
    network,
    evidence,
  }, info) => {
    await page.setViewportSize(viewport)
    await page.evaluate(() => localStorage.setItem('kg-locale', 'en-US'))
    const type = await getData<Record<string, unknown>>(
      identity.api,
      '/entity-types/' + data.published.id,
    )
    await network.empty(
      { path: '/entity-types/' + data.published.id },
      {
        ...type,
        label_i18n: { 'zh-CN': longName, 'en-US': longName },
      },
    )
    await page.goto('/ontology/entity-types/' + data.published.id)
    await expect(page.locator('.page-header h1')).toHaveText(longName)
    await capture(
      page,
      info,
      evidence,
      'resource-long-title',
      'controlled long label, English UI, real resource detail',
    )
    const title = await page
      .locator('.page-header h1')
      .evaluate((el) => ({ width: el.clientWidth, content: el.scrollWidth }))
    expect(title.content).toBeLessThanOrEqual(title.width + 1)
    const table = await page
      .locator('.n-descriptions-table')
      .first()
      .evaluate((el) => ({
        width: el.getBoundingClientRect().width,
        containerWidth: el.parentElement!.getBoundingClientRect().width,
      }))
    expect(table.width).toBeLessThanOrEqual(table.containerWidth + 1)
    for (const button of await page.locator('.page-header .actions button').all()) {
      await expect(button).toBeInViewport()
    }
  })
}
