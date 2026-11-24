import { createHash } from 'node:crypto'

import { expect, test } from '@playwright/test'
import type { Locator, Page, TestInfo } from '@playwright/test'

// Formal business routes with controlled, deidentified reads. Every API request is
// intercepted; this suite never seeds or reads the developer or baseline database.
const layouts = [
  'type_grid',
  'ring',
  'force',
  'org_tree',
  'indent_tree',
  'equity_tree',
  'control_chain',
  'supply_chain',
  'timeline',
  'schema',
  'clan_tree',
  'cycle_view',
  'bipartite',
  'community',
  'nary',
  'sankey',
  'chord',
  'geo',
  'impact',
  'sunburst',
  'treemap',
  'pack',
  'gantt',
  'small_multiples',
] as const
const partitions = new Set(['sunburst', 'treemap', 'pack', 'gantt'])
const aggregates = new Set(['schema', 'sankey', 'chord'])
const trees = new Set([
  'org_tree',
  'indent_tree',
  'equity_tree',
  'control_chain',
  'clan_tree',
  'impact',
])
const model = 'https://example.org/model/'
const instance = 'https://example.org/instance/'
const resource = (id: number, name: string) => ({
  id,
  name,
  iri: model + name,
  label_i18n: { 'zh-CN': name, 'en-US': name },
  status: 'PUBLISHED',
  current_revision: 1,
  edit_revision: 1,
})
const types = [resource(1, 'Person'), resource(2, 'Project')]
const ontology = { ...resource(1, 'GraphFixture'), resource_count: 6 }
const relations = [3, 4, 5, 6].map((id) => ({
  ...resource(id, `Relation${id}`),
  domain_spec: { type_id: id === 5 ? 2 : 1 },
  range_spec: { type_id: id === 6 ? 1 : id === 5 ? 1 : 2 },
}))

function fixture(layout: string) {
  const nodes = ['root', 'a', 'b', 'c', 'd', 'e'].map((name, index) => ({
    id: index + 1,
    graph_revision_id: 1,
    iri: instance + name,
    type_iri: model + (index === 0 ? 'Project' : 'Person'),
    row_key: name,
    distance: index === 0 ? 0 : 1,
    attrs: {
      name,
      size: index + 2,
      moment: index < 3 ? '2024-01-01' : '2024-02-01',
      lat: 30 + index,
      lon: 100 + index,
    },
  }))
  const edge = (id: number, source: string, target: string, kind = 'DIRECT') => ({
    id,
    graph_revision_id: 1,
    subject: instance + source,
    object_: instance + target,
    predicate: model + 'parent',
    kind,
    props: { pct: 50 },
  })
  const edges = [
    edge(11, 'a', 'root'),
    edge(12, 'a', 'root'),
    edge(11, 'a', 'root', 'DERIVED'),
    edge(13, 'b', 'root'),
    edge(14, 'c', 'root'),
    edge(15, 'd', trees.has(layout) ? 'root' : 'a'),
    edge(16, 'e', trees.has(layout) ? 'root' : 'a'),
  ]
  if (!trees.has(layout)) edges.push(edge(17, 'root', 'a'), edge(18, 'a', 'a'), edge(19, 'a', 'a'))
  return {
    graph_revision_id: 1,
    run_id: 1,
    ontology_id: 1,
    ontology_revision: 1,
    instance_namespace: instance,
    nodes,
    edges,
    entity_total: nodes.length,
    quarantine_count: 0,
    truncated: false,
    type_counts: types.map((type) => ({
      type_iri: type.iri,
      count: nodes.filter((node) => node.type_iri === type.iri).length,
    })),
  }
}

async function prepare(page: Page, layout = 'force', role = 'EDITOR', multilevel = false) {
  const writes: string[] = []
  const unexpected: string[] = []
  const evidenceReads: string[] = []
  const errors: string[] = []
  const graph = fixture(layout)
  if (multilevel) {
    graph.nodes = graph.nodes.slice(1, 4)
    graph.edges = [
      { ...graph.edges[0]!, id: 11, subject: instance + 'a', object_: instance + 'b' },
      { ...graph.edges[0]!, id: 12, subject: instance + 'b', object_: instance + 'c' },
      {
        ...graph.edges[0]!,
        id: 13,
        subject: instance + 'a',
        object_: instance + 'c',
      },
      {
        ...graph.edges[0]!,
        id: 13,
        subject: instance + 'a',
        object_: instance + 'c',
        kind: 'DERIVED',
      },
      {
        ...graph.edges[0]!,
        id: 14,
        subject: instance + 'a',
        object_: instance + 'c',
      },
    ]
    graph.entity_total = graph.nodes.length
  }
  const fields = types.flatMap((type) =>
    ['size', 'moment', 'lat', 'lon'].map((name) => ({
      iri: model + name,
      name,
      kind: 'PROPERTY',
      type_iri: type.iri,
      datatype: name === 'moment' ? 'date' : 'decimal',
    })),
  )
  fields.push({
    iri: model + 'parent',
    name: 'parent',
    kind: 'RELATION',
    type_iri: '',
    datatype: '',
  })
  const template = {
    id: 77,
    ontology_id: 1,
    ontology_revision: 1,
    layout_id: layout,
    name_i18n: { 'zh-CN': 'Graph fixture', 'en-US': 'Graph fixture' },
    stale: false,
    config: {
      semantic_version: 1,
      hierarchy_relation_iri: model + 'parent',
      measure_property_iri: model + 'size',
      time_property_iri: model + 'moment',
      latitude_property_iri: model + 'lat',
      longitude_property_iri: model + 'lon',
    },
  }
  await page.addInitScript(() => {
    localStorage.setItem('kg-access-token', 'graph-fixture-access')
    localStorage.setItem('kg-refresh-token', 'graph-fixture-refresh')
    localStorage.setItem('kg-theme-mode', 'light')
    localStorage.setItem('kg-locale', 'zh-CN')
  })
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1', '')
    if (request.method() !== 'GET') writes.push(request.method() + ' ' + path)
    let data: unknown
    if (path === '/auth/me')
      data = {
        id: 1,
        username: 'graph_fixture',
        role,
        status: 'ACTIVE',
        email: 'fixture@example.org',
      }
    else if (path === '/extraction/graph-view') data = graph
    else if (path === '/extraction/entities')
      data = { items: graph.nodes, total: graph.nodes.length, page: 1, page_size: 20 }
    else if (path === '/extraction/graph/1/layout-recommendations') data = { recommendations: [] }
    else if (path === '/view-templates') data = { items: [template], total: 1 }
    else if (path === '/view-templates/semantic-fields')
      data = { ontology_id: 1, ontology_revision: 1, stale: false, fields }
    else if (path === '/view-templates/77/applicable') data = template
    else if (path.startsWith('/extraction/evidence/')) {
      evidenceReads.push(request.url())
      data = { total_count: 0, evidences: [] }
    } else if (path === '/knowledge-bases/graph-evidence') data = []
    else if (path === '/entity-types') data = types
    else if (/^\/entity-types\/\d+$/.test(path))
      data = { ...types.find((type) => type.id === Number(path.split('/').at(-1))), data_props: [] }
    else if (path === '/relations') data = relations
    else if (/^\/relations\/\d+$/.test(path))
      data = relations.find((relation) => relation.id === Number(path.split('/').at(-1)))
    else if (path === '/domains' || path === '/namespaces') data = []
    else if (path === '/ontologies') data = [ontology]
    else if (path === '/ontologies/1') data = ontology
    else if (path === '/ontologies/1/refs')
      data = [1, 2, 3, 4, 5, 6].map((id) => ({ id, resource_id: id, pinned_revision: 1 }))
    else if (path === '/ontologies/1/canvas')
      data = { positions: { 1: { x: 500, y: 500 }, 2: { x: 1000, y: 500 } } }
    else if (path === '/ontologies/1/revisions/1/contents')
      data = {
        resources: [1, 2, 3, 4, 5, 6].map((id) => ({ resource_id: id, revision: 1 })),
        rules: [],
      }
    else if (/^\/ontologies\/1\/revisions\/1\/resources\/\d+$/.test(path)) {
      const id = Number(path.split('/').at(-1))
      const relation = relations.find((item) => item.id === id)
      data = {
        resource_id: id,
        revision: 1,
        snapshot: {
          ...(relation ?? types.find((item) => item.id === id)),
          kind: relation ? 'OBJECT_PROP' : 'ENTITY',
          resource_refs: relation
            ? [
                { role: 'relation_domain', target_id: relation.domain_spec.type_id },
                { role: 'relation_range', target_id: relation.range_spec.type_id },
              ]
            : [],
          parent_ids: [],
          datatype_props: [],
        },
      }
    } else {
      unexpected.push(request.method() + ' ' + path)
      await route.fulfill({
        status: 501,
        json: { code: 'KG.INTERNAL_ERROR', message: '', data: null },
      })
      return
    }
    await route.fulfill({ json: { code: 'KG.OK', message: '', data } })
  })
  return { writes, unexpected, evidenceReads, errors, graph, template }
}

async function camera(page: Page) {
  return page.locator('.graph-scene').evaluate((element) => {
    const matrix = (element as SVGGElement).transform.baseVal.consolidate()!.matrix
    return { x: matrix.e, y: matrix.f, scale: matrix.a }
  })
}
async function clickPath(page: Page, path: Locator) {
  // Selecting a fact opens the inspector and changes the canvas width. Fit the
  // current viewport before seeking a real pointer hit on the next fact.
  await page.locator('.canvas-scroll').focus()
  await page.keyboard.press('Home')
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  )
  const visiblePoint = () =>
    path.evaluate((element) => {
      const curve = element as SVGPathElement
      const owner = curve.closest('[data-edge-key]')
      const length = curve.getTotalLength()
      const matrix = curve.getScreenCTM()!
      for (let index = 1; index < 20; index++) {
        const position = curve.getPointAtLength((length * index) / 20)
        const nearby = curve.getPointAtLength((length * index) / 20 + 0.1)
        const screen = new DOMPoint(position.x, position.y).matrixTransform(matrix)
        const tangent = new DOMPoint(nearby.x, nearby.y).matrixTransform(matrix)
        const dx = tangent.x - screen.x
        const dy = tangent.y - screen.y
        const magnitude = Math.hypot(dx, dy) || 1
        for (const offset of [0, -3, 3, -6, 6]) {
          const point = {
            x: Math.round(screen.x - (dy / magnitude) * offset),
            y: Math.round(screen.y + (dx / magnitude) * offset),
          }
          if (document.elementFromPoint(point.x, point.y)?.closest('[data-edge-key]') === owner)
            return point
        }
      }
      return null
    })
  let point = await visiblePoint()
  for (let attempt = 0; !point && attempt < 3; attempt++) {
    const before = await camera(page)
    if (before.scale >= 3) break
    const anchor = await path.evaluate((element) => {
      const curve = element as SVGPathElement
      const world = curve.getPointAtLength(curve.getTotalLength() / 2)
      const point = new DOMPoint(world.x, world.y).matrixTransform(curve.getScreenCTM()!)
      return { x: Math.round(point.x), y: Math.round(point.y) }
    })
    await page.mouse.move(anchor.x, anchor.y)
    await page.keyboard.down('Control')
    await page.mouse.wheel(0, -300)
    await expect.poll(async () => (await camera(page)).scale).toBeGreaterThan(before.scale)
    await page.keyboard.up('Control')
    test.info().annotations.push({
      type: 'interaction',
      description: 'Explicit readable zoom before edge click',
    })
    point = await visiblePoint()
  }
  if (!point)
    await test.info().attach('unreachable-edge', {
      contentType: 'application/json',
      body: JSON.stringify(
        await path.evaluate((element) => {
          const path = element as SVGPathElement
          return {
            d: path.getAttribute('d'),
            transform: path.getScreenCTM(),
            points: [0.1, 0.25, 0.5, 0.75, 0.9].map((fraction) => {
              const p = path.getPointAtLength(path.getTotalLength() * fraction)
              const screen = new DOMPoint(p.x, p.y).matrixTransform(path.getScreenCTM()!)
              return {
                x: screen.x,
                y: screen.y,
                hits: document
                  .elementsFromPoint(screen.x, screen.y)
                  .slice(0, 4)
                  .map((hit) => ({
                    tag: hit.tagName,
                    class: hit.getAttribute('class'),
                    key: hit.closest('[data-edge-key]')?.getAttribute('data-edge-key'),
                  })),
              }
            }),
          }
        }),
      ),
    })
  expect(
    point,
    'The actual edge must have a visible hit area after bounded explicit zoom',
  ).not.toBeNull()
  if (!point) return
  await page.mouse.click(point.x, point.y)
}
async function checkDesignerPointerRelations(page: Page) {
  const canvas = page.locator('.designer .canvas')
  for (const id of [3, 4, 5, 6]) {
    const key = `rel-${id}`
    const path = page.locator(`.designer .edge-hit[data-selection="${key}"]`)
    // Refit after the inspector closes; its width affects the visible canvas.
    await canvas.focus()
    await page.keyboard.press('Home')
    await page.evaluate(
      () =>
        new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        ),
    )
    const point = await path.evaluate((element) => {
      const curve = element as SVGPathElement
      const length = curve.getTotalLength()
      const matrix = curve.getScreenCTM()!
      for (let index = 1; index < 40; index++) {
        const distance = (length * index) / 40
        const position = curve.getPointAtLength(distance)
        const nearby = curve.getPointAtLength(Math.min(length, distance + 0.1))
        const screen = new DOMPoint(position.x, position.y).matrixTransform(matrix)
        const tangent = new DOMPoint(nearby.x, nearby.y).matrixTransform(matrix)
        const dx = tangent.x - screen.x
        const dy = tangent.y - screen.y
        const magnitude = Math.hypot(dx, dy) || 1
        for (const offset of [0, -2, 2, -4, 4, -6, 6]) {
          const point = {
            x: Math.round(screen.x - (dy / magnitude) * offset),
            y: Math.round(screen.y + (dx / magnitude) * offset),
          }
          // Require the hit path itself, not its label or a sibling's painted stroke.
          if (document.elementFromPoint(point.x, point.y) === curve) return point
        }
      }
      return null
    })
    expect(point, `Designer ${key} must have an unobscured pointer target`).not.toBeNull()
    if (!point) throw new Error(`No visible Designer hit path for ${key}`)
    await page.mouse.click(point.x, point.y)
    await expect(page.locator('.designer .edge.selected .edge-hit')).toHaveAttribute(
      'data-selection',
      key,
    )
    await expect(page.locator('#designer-inspector')).toContainText(`Relation${id}`)
    await page.keyboard.press('Escape')
    await expect(page.locator('#designer-inspector')).toHaveCount(0)
    await expect(path).toBeFocused()
  }
}
async function evidence(info: TestInfo, page: Page, data: unknown) {
  await info.attach('renderer-matrix', {
    body: JSON.stringify(
      {
        data,
        route: page.url(),
        viewport: page.viewportSize(),
        browser: page.context().browser()?.version(),
        locale: await page.evaluate(() => navigator.language),
        mode: 'real browser; controlled API reads; no backend or database',
        fixtureSha256: createHash('sha256').update(JSON.stringify(data)).digest('hex'),
      },
      null,
      2,
    ),
    contentType: 'application/json',
  })
  await info.attach('renderer', {
    body: await page.screenshot({ animations: 'disabled' }),
    contentType: 'image/png',
  })
}

for (const layout of ['equity_tree', 'clan_tree']) {
  test(`${layout}: multilevel and parallel facts have independent pointer targets`, async ({
    page,
  }, info) => {
    const state = await prepare(page, layout, 'EDITOR', true)
    await page.goto(`/graph?graph=1&layout=${layout}&template=77`)
    await page.waitForLoadState('networkidle')
    for (const key of ['DIRECT:11', 'DIRECT:12', 'DIRECT:13', 'DERIVED:13', 'DIRECT:14']) {
      const edge = page.locator(`.edge-group[data-edge-key="${key}"]`)
      await clickPath(page, edge.locator('.edge-hit'))
      await expect(edge).toHaveAttribute('aria-pressed', 'true')
      await expect(page.locator('.inspector-binding')).toContainText(key)
    }
    expect(state.writes).toEqual([])
    expect(state.unexpected).toEqual([])
    expect(state.errors).toEqual([])
    await evidence(info, page, {
      layout,
      checks:
        'multilevel/parallel/DIRECT+DERIVED identity and real pointer hit; reverse cycles are invalid in hierarchy modes',
    })
  })
}

for (const layout of layouts) {
  test(`${layout}: formal renderer wheel, anchored zoom, keyboard and business identity`, async ({
    page,
  }, info) => {
    const state = await prepare(page, layout)
    await page.goto(`/graph?graph=1&layout=${layout}&template=77`)
    await page.waitForLoadState('networkidle')
    const canvas = page.locator('.canvas-scroll')
    await expect(canvas).toBeVisible()
    await expect(
      page.locator(partitions.has(layout) ? '.mark-group[data-iri]' : '.node'),
    ).not.toHaveCount(0)
    const initial = await camera(page)
    const box = (await canvas.boundingBox())!
    const anchor = {
      x: Math.round(box.x + box.width * 0.65),
      y: Math.round(box.y + box.height * 0.6),
    }
    await page.mouse.move(anchor.x, anchor.y)
    await page.mouse.wheel(24, 36)
    await expect.poll(async () => (await camera(page)).y).toBeCloseTo(initial.y - 36, 1)
    expect((await camera(page)).scale).toBeCloseTo(initial.scale, 8)
    for (const modifier of ['Control', 'Meta']) {
      const before = await camera(page)
      const point = {
        x: (anchor.x - box.x - before.x) / before.scale,
        y: (anchor.y - box.y - before.y) / before.scale,
      }
      await page.keyboard.down(modifier)
      await page.mouse.wheel(0, -80)
      await expect.poll(async () => (await camera(page)).scale).toBeGreaterThan(before.scale)
      await page.keyboard.up(modifier)
      const after = await camera(page)
      expect(point.x * after.scale + after.x).toBeCloseTo(anchor.x - box.x, 1)
      expect(point.y * after.scale + after.y).toBeCloseTo(anchor.y - box.y, 1)
    }
    await canvas.focus()
    await expect(canvas).toBeFocused()
    const beforeKey = await camera(page)
    await page.keyboard.press('ArrowRight')
    await expect
      .poll(async () => Math.abs((await camera(page)).x - (beforeKey.x - 48)))
      .toBeLessThan(0.01)
    await page.keyboard.press('Home')
    if (partitions.has(layout)) {
      const mark = page.locator('.mark-group[data-iri]').first()
      await mark.focus()
      await page.keyboard.press('Enter')
      await expect(mark).toHaveAttribute('aria-pressed', 'true')
      const snapshot = await canvas.evaluate((element) => {
        const owner = (
          element as unknown as { __vueParentComponent: { exposed: { getContext: () => unknown } } }
        ).__vueParentComponent
        return owner.exposed.getContext()
      })
      const original = await mark.getAttribute('transform')
      const label = (await mark.locator('.mark-label').boundingBox())!
      const start = { x: label.x + label.width / 2, y: label.y + label.height / 2 }
      for (const ending of ['Escape', 'pointercancel', 'lostpointercapture', 'pointerup']) {
        await canvas.evaluate((element) =>
          element.addEventListener(
            'pointerdown',
            (event) => {
              ;(element as HTMLElement).dataset.testPointer = String(
                (event as PointerEvent).pointerId,
              )
            },
            { once: true, capture: true },
          ),
        )
        await page.mouse.move(start.x, start.y)
        await page.mouse.down()
        await page.mouse.move(start.x + 40, start.y + 20)
        await expect(mark).not.toHaveAttribute('transform', original!)
        const pointerId = Number(await canvas.getAttribute('data-test-pointer'))
        if (ending === 'Escape') await page.keyboard.press('Escape')
        else if (ending === 'pointercancel')
          await canvas.dispatchEvent('pointercancel', { pointerId })
        else if (ending === 'lostpointercapture')
          await canvas.evaluate((element, id) => element.releasePointerCapture(id), pointerId)
        await page.mouse.up()
        if (ending !== 'pointerup') await expect(mark).toHaveAttribute('transform', original!)
      }
      const restored = await canvas.evaluate((element, context) => {
        const owner = (
          element as unknown as {
            __vueParentComponent: { exposed: { restoreContext: (value: unknown) => boolean } }
          }
        ).__vueParentComponent
        return owner.exposed.restoreContext(context)
      }, snapshot)
      expect(restored).toBe(true)
      await expect(mark).toHaveAttribute('transform', original!)
      expect((await mark.getAttribute('transform'))!).not.toMatch(/NaN|Infinity/)
    } else if (layout !== 'geo') {
      const keys = aggregates.has(layout)
        ? ['DIRECT:11', 'DERIVED:11']
        : trees.has(layout)
          ? ['DIRECT:11', 'DIRECT:12', 'DERIVED:11']
          : ['DIRECT:11', 'DIRECT:12', 'DERIVED:11', 'DIRECT:17', 'DIRECT:18', 'DIRECT:19']
      for (const key of keys) {
        const edge = page.locator(`.edge-group[data-edge-key="${key}"]`)
        await expect(edge).toBeVisible()
        await clickPath(page, edge.locator('.edge-hit'))
        await expect(edge).toHaveAttribute('aria-pressed', 'true')
        await edge.evaluate((element) => (element as SVGElement).focus({ preventScroll: true }))
        await page.keyboard.press('Space')
        await expect(edge).toHaveAttribute('aria-pressed', 'true')
        const inspector = page.locator('.graph-inspector')
        await expect(inspector).toBeVisible()
        if (aggregates.has(layout)) {
          await expect(inspector).toContainText(model + 'Person')
          await expect(inspector).toContainText(model + 'Project')
          await expect(inspector).toContainText('count')
          await expect(
            inspector.getByRole('button', { name: '追溯证据', exact: true }),
          ).toBeDisabled()
          await expect(inspector.locator('.document-references')).toHaveCount(0)
        } else await expect(inspector.locator('.inspector-binding')).toContainText(key)
      }
    } else await expect(page.locator('.edge-group')).toHaveCount(0)
    expect(state.writes).toEqual([])
    expect(state.unexpected).toEqual([])
    expect(state.errors).toEqual([])
    if (aggregates.has(layout)) expect(state.evidenceReads).toEqual([])
    await evidence(info, page, {
      layout,
      renderer: partitions.has(layout) ? 'marks' : 'node-edge',
      graph: state.graph,
      checks: 'wheel/Control/Meta/Home/selection and mode-specific identity/cancel',
    })
  })
}

for (const mode of ['VIEWER', 'frozen']) {
  test(`Designer ${mode}: selection and camera remain available without editing positions`, async ({
    page,
  }, info) => {
    const state = await prepare(page, 'force', mode === 'VIEWER' ? 'VIEWER' : 'EDITOR')
    await page.goto('/ontology/designer?ontology=1')
    await page.waitForLoadState('networkidle')
    if (mode === 'frozen') {
      await page.locator('.revision-select').getByRole('combobox').click()
      await page.getByRole('option', { name: '冻结版本 r1', exact: true }).click()
    }
    const node = page.locator('.designer .node[data-selection="1"]')
    await expect(node).toBeVisible()
    const original = await node.getAttribute('style')
    await node.focus()
    await page.keyboard.press('Enter')
    await expect(page.locator('#designer-inspector')).toBeVisible()
    const box = (await node.boundingBox())!
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await page.mouse.down()
    await page.mouse.move(box.x + box.width / 2 + 60, box.y + box.height / 2 + 30)
    await page.mouse.up()
    await expect(node).toHaveAttribute('style', original!)
    await expect(page.getByRole('button', { name: '保存布局', exact: true })).toBeDisabled()
    await page.keyboard.press('Escape')
    await expect(page.locator('#designer-inspector')).toHaveCount(0)
    await expect(node).toBeFocused()
    await checkDesignerPointerRelations(page)
    await expect(node).toHaveAttribute('style', original!)
    await expect(page.getByRole('button', { name: '保存布局', exact: true })).toBeDisabled()
    expect(state.writes).toEqual([])
    expect(state.unexpected).toEqual([])
    expect(state.errors).toEqual([])
    await evidence(info, page, {
      mode,
      checks:
        'read-only selection/focus/escape; real parallel/reverse/self edge hits; no editing or save',
    })
  })
}

for (const width of [1440, 1024, 1023, 768, 767]) {
  test(`Designer ${width}: empty inspector space, focus, fold and single-layer Escape`, async ({
    page,
  }, info) => {
    const state = await prepare(page)
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/ontology/designer?ontology=1')
    await page.waitForLoadState('networkidle')
    const canvas = page.locator('.designer .canvas')
    const node = page.locator('.designer .node[data-selection="1"]')
    await expect(node).toBeVisible()
    await expect(page.locator('#designer-inspector')).toHaveCount(0)
    const emptyWidth = (await canvas.boundingBox())!.width
    const original = await node.getAttribute('style')
    await node.focus()
    await page.keyboard.press('Enter')
    await expect(page.locator('#designer-inspector')).toBeVisible()
    const box = (await canvas.boundingBox())!
    const nodeBox = (await node.boundingBox())!
    await info.attach('designer-focus-geometry', {
      body: JSON.stringify(
        await canvas.evaluate((element) => {
          const host = element as HTMLElement
          const node = host.querySelector('.node') as HTMLElement
          const world = host.querySelector('.world') as HTMLElement
          const rect = (target: Element | null) => target?.getBoundingClientRect().toJSON()
          return {
            canvas: rect(host),
            node: rect(node),
            world: rect(world),
            spin: rect(host.querySelector('.canvas-spin')),
            scroll: [host.scrollLeft, host.scrollTop],
            worldTransform: world.style.transform,
            nodePosition: node.style.cssText,
            inspector: rect(host.parentElement?.querySelector('.inspector') ?? null),
            pool: rect(host.parentElement?.querySelector('.pool') ?? null),
          }
        }),
      ),
      contentType: 'application/json',
    })
    expect(nodeBox.x).toBeGreaterThanOrEqual(box.x)
    expect(nodeBox.x + nodeBox.width).toBeLessThanOrEqual(box.x + box.width + 1)
    await page.getByRole('button', { name: '图例', exact: true }).click()
    const dragBox = (await node.boundingBox())!
    await page.mouse.move(dragBox.x + dragBox.width / 2, dragBox.y + dragBox.height / 2)
    await page.mouse.down()
    await page.mouse.move(dragBox.x + dragBox.width / 2 + 40, dragBox.y + dragBox.height / 2 + 20)
    await expect(node).not.toHaveAttribute('style', original!)
    await page.keyboard.press('Escape')
    await page.mouse.up()
    await expect(node).toHaveAttribute('style', original!)
    await expect(page.locator('.designer .legend')).toBeVisible()
    await expect(page.locator('#designer-inspector')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.locator('.designer .legend')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '图例', exact: true })).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(page.locator('#designer-inspector')).toHaveCount(0)
    await expect(node).toBeFocused()
    expect((await canvas.boundingBox())!.width).toBeGreaterThanOrEqual(emptyWidth - 1)
    for (const id of [3, 4, 5, 6]) {
      const path = page.locator(`.designer .edge-hit[data-selection="rel-${id}"]`)
      await path.focus()
      await page.keyboard.press('Enter')
      await expect(page.locator('#designer-inspector')).toContainText(`Relation${id}`)
      await page.keyboard.press('Escape')
      await expect(path).toBeFocused()
    }
    await checkDesignerPointerRelations(page)
    expect(state.writes).toEqual([])
    expect(state.unexpected).toEqual([])
    expect(state.errors).toEqual([])
    await evidence(info, page, {
      mode: 'Designer working',
      width,
      checks:
        'focus/fold/gesture/legend/inspector; keyboard and real pointer parallel/reverse/self IDs; no layout save',
    })
  })
}
