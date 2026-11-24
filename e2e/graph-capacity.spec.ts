import { execFileSync } from 'node:child_process'
import { existsSync, realpathSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, join, resolve, sep } from 'node:path'

import type { Locator, Page } from '@playwright/test'

import type { GraphView } from '../web/src/api/graph'
import type { components } from '../web/src/api/schema'
import {
  attachJson,
  capture,
  expect,
  getData,
  responseData,
  settleApi,
  test,
  uniqueName,
} from './ui-redesign-fixtures'

type Resource = components['schemas']['EntityTypeOut']
type Ontology = components['schemas']['OntologyOut']
type Api = Parameters<typeof getData>[0]

async function seedOntology(api: Api) {
  const post = async <T>(path: string, data?: unknown) =>
    responseData<T>(await api.post(`/api/v1${path}`, { data }))
  const name = uniqueName('Capacity')
  const namespace = await post<{ id: number }>('/namespaces', {
    prefix: name.toLowerCase(),
    iri: `https://example.org/${name}/`,
    label_i18n: { 'zh-CN': '图谱交互回归', 'en-US': 'Graph interaction regression' },
  })
  const types: Resource[] = []
  for (const [typeName, label] of [
    [uniqueName('CapacityHub'), '高阶中心'],
    [uniqueName('CapacityLeaf'), '长标签邻居'],
  ]) {
    const type = await post<Resource>('/entity-types', {
      namespace_id: namespace.id,
      name: typeName,
      label_i18n: { 'zh-CN': label, 'en-US': typeName },
      data_props: [{ name: 'name', datatype: 'string', nullable: false }],
    })
    await post(`/entity-types/${type.id}/publish`)
    types.push(type)
  }
  const relation = await post<components['schemas']['RelationTypeOut']>('/relations', {
    namespace_id: namespace.id,
    name: uniqueName('CapacityLink'),
    label_i18n: { 'zh-CN': '关联邻居', 'en-US': 'Related leaf' },
    domain_spec: { type_id: types[0].id },
    range_spec: { type_id: types[1].id },
  })
  await post(`/relations/${relation.id}/publish`)
  const ontology = await post<Ontology>('/ontologies', {
    name,
    iri: `https://example.org/${name}/ontology/`,
    label_i18n: { 'zh-CN': '图谱交互回归', 'en-US': 'Graph interaction regression' },
    ref_resource_ids: [...types.map((type) => type.id), relation.id],
  })
  await post(`/ontologies/${ontology.id}/publish`)
  return { ontology, types, relation, post }
}

async function seedStar(api: Api) {
  const seeded = await seedOntology(api)
  const temp = process.env.KG_E2E_TEMP_DIR
  expect(temp, 'Only the repository Playwright isolated source/database is allowed').toBeTruthy()
  const directory = realpathSync(temp!)
  expect(directory.startsWith(realpathSync(tmpdir()) + sep)).toBe(true)
  expect(basename(directory)).toMatch(/^knowledge-e2e-/)
  expect(existsSync(join(directory, 'metadata.sqlite'))).toBe(true)
  const sourcePath = join(directory, `${uniqueName('capacity-source-')}.sqlite`)
  // Only create a synthetic SOURCE database. Metadata, graph facts and revisions are produced by APIs.
  execFileSync(
    resolve('server/.venv/bin/python'),
    [
      '-c',
      `
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as connection:
    connection.execute('CREATE TABLE hubs (id INTEGER PRIMARY KEY, name TEXT NOT NULL)')
    connection.execute('CREATE TABLE leaves (id INTEGER PRIMARY KEY, name TEXT NOT NULL)')
    connection.execute('CREATE TABLE links (id INTEGER PRIMARY KEY, hub_id INTEGER REFERENCES hubs(id), leaf_id INTEGER REFERENCES leaves(id))')
    connection.execute('INSERT INTO hubs VALUES (1, ?)', ('高阶中心',))
    connection.executemany('INSERT INTO leaves VALUES (?, ?)', [(index, f'邻居{index:03d} 很长的实体名称🙂用于验证既有裁剪') for index in range(1, 200)])
    connection.executemany('INSERT INTO links VALUES (?, 1, ?)', [(index, index) for index in range(1, 200)])
`,
      sourcePath,
    ],
    { timeout: 10_000, stdio: 'pipe' },
  )
  const source = await seeded.post<{ id: number }>('/datasources', {
    name: uniqueName('CapacitySource'),
    kind: 'sqlite',
    params: { database: sourcePath },
  })
  await seeded.post(`/datasources/${source.id}/metadata/capture`)
  const mapping = await seeded.post<{ id: number; current_revision: number }>('/mappings', {
    name: uniqueName('CapacityMapping'),
    ontology_id: seeded.ontology.id,
    draft: {
      entity_maps: seeded.types.map((type, index) => ({
        entity_type: type.name,
        table: index ? 'leaves' : 'hubs',
        schema: 'main',
        key_fields: ['id'],
        field_maps: [{ target_attr: 'name', source_field: 'name', null_policy: 'REQUIRED' }],
      })),
      rel_maps: [
        {
          relation_type: seeded.relation.name,
          mode: 'JUNCTION',
          table: 'links',
          schema: 'main',
          source: { field: 'hub_id', ref_table: 'hubs', ref_field: 'id' },
          target: { field: 'leaf_id', ref_table: 'leaves', ref_field: 'id' },
          attributes: [],
        },
      ],
    },
  })
  const revision = await seeded.post<{ id: number }>(`/mappings/${mapping.id}/publish`, {
    if_match: mapping.current_revision,
  })
  const result = await seeded.post<{ run: { status: string }; graph_revision: { id: number } }>(
    '/extraction/runs',
    {
      mapping_revision_id: revision.id,
      datasource_id: source.id,
      namespace: seeded.ontology.iri,
    },
  )
  expect(result.run.status).toBe('SUCCESS')
  const graph = await getData<GraphView>(
    api,
    `/extraction/graph-view?graph_revision_id=${result.graph_revision.id}`,
  )
  expect(graph.nodes).toHaveLength(200)
  expect(graph.edges).toHaveLength(199)
  expect(graph.truncated).toBe(false)
  expect(new Set(graph.edges.map((edge) => edge.subject)).size).toBe(1)
  expect(new Set(graph.edges.map((edge) => edge.object_)).size).toBe(199)
  return { ...seeded, graph }
}

async function camera(page: Page) {
  return page.locator('.graph-scene').evaluate((element) => {
    const matrix = (element as SVGGElement).transform.baseVal.consolidate()!.matrix
    return { x: matrix.e, y: matrix.f, scale: matrix.a }
  })
}

async function disks(page: Page) {
  return page.locator('.canvas-scroll').evaluate((host) => {
    const viewport = host.getBoundingClientRect()
    const circles = [...host.querySelectorAll<SVGCircleElement>('.node-body')].map((circle) => {
      const box = circle.getBoundingClientRect()
      return {
        iri: circle.closest<SVGElement>('.node')!.dataset.iri!,
        x: box.x + box.width / 2,
        y: box.y + box.height / 2,
        r: box.width / 2,
        inside:
          box.left >= viewport.left - 1 &&
          box.top >= viewport.top - 1 &&
          box.right <= viewport.right + 1 &&
          box.bottom <= viewport.bottom + 1,
      }
    })
    const overlaps: { left: string; right: string; distance: number; radii: number }[] = []
    let closest = Number.POSITIVE_INFINITY
    for (let left = 0; left < circles.length; left++) {
      for (let right = left + 1; right < circles.length; right++) {
        const a = circles[left],
          b = circles[right]
        const distance = Math.hypot(a.x - b.x, a.y - b.y)
        closest = Math.min(closest, distance)
        if (distance + 0.1 < a.r + b.r)
          overlaps.push({ left: a.iri, right: b.iri, distance, radii: a.r + b.r })
      }
    }
    return {
      count: circles.length,
      closest,
      overlaps,
      outside: circles.filter((circle) => !circle.inside),
      circles,
    }
  })
}

async function frames(page: Page) {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  )
}

function distribution(samples: number[]) {
  const sorted = [...samples].sort((a, b) => a - b)
  const quantile = (fraction: number) => sorted[Math.ceil(sorted.length * fraction) - 1]
  return {
    samples,
    n: sorted.length,
    min: sorted[0],
    p50: quantile(0.5),
    p95: quantile(0.95),
    max: sorted.at(-1),
  }
}

test('real API 200-node nary: native render/fit/selection/readable zoom and wheel/keyboard', async ({
  signedIn: page,
  identity,
  evidence,
}, info) => {
  const { graph } = await seedStar(identity.api)
  await attachJson(info, 'extracted-api-graph', graph)
  const loads: number[] = []
  const apiTimes: number[] = []
  const measurements: Record<string, unknown> = {
    evidenceMode: 'real-api-extraction',
    nodes: 200,
    edges: 199,
  }
  try {
    for (let index = 0; index < 5; index++) {
      const started = performance.now()
      const response = page.waitForResponse(
        (response) => new URL(response.url()).pathname === '/api/v1/extraction/graph-view',
      )
      await page.goto(`/graph?graph=${graph.graph_revision_id}&layout=nary`)
      const observedResponse = await response
      const browserGraph = await responseData<GraphView>(observedResponse)
      expect(browserGraph.nodes).toHaveLength(200)
      expect(browserGraph.edges).toHaveLength(199)
      await observedResponse.finished()
      const timings = observedResponse.request().timing()
      expect(timings.responseEnd).toBeGreaterThanOrEqual(0)
      apiTimes.push(timings.responseEnd)
      await expect(page.locator('.node-body')).toHaveCount(200)
      await expect(page.locator('.edge-group')).toHaveCount(199)
      await settleApi(page, evidence)
      await frames(page)
      loads.push(performance.now() - started)
    }
    expect(evidence.injections).toEqual([])
    await expect(page.locator('.graph-footer')).toContainText('当前显示 200 节点 / 199 关系')
    await page.getByRole('button', { name: '适应视图', exact: true }).click()
    await frames(page)
    const fit = await disks(page)
    measurements.fit = fit
    expect(fit.count).toBe(200)
    expect(fit.overlaps, 'Actual rendered circles do not overlap at fit').toEqual([])
    expect(fit.outside, 'All 200 actual circles fit inside the canvas').toEqual([])
    await capture(
      page,
      info,
      evidence,
      'nary-200-fit',
      '200 nodes / 199 edges from real API extraction, measured screen circles',
    )

    const canvas = page.locator('.canvas-scroll')
    const box = (await canvas.boundingBox())!
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    const beforeWheel = await camera(page)
    await page.mouse.wheel(36, 70)
    await expect.poll(async () => (await camera(page)).y).toBeCloseTo(beforeWheel.y - 70, 1)
    expect((await camera(page)).x).toBeCloseTo(beforeWheel.x - 36, 1)
    expect((await camera(page)).scale).toBe(beforeWheel.scale)
    await canvas.focus()
    const beforeKey = await camera(page)
    await page.keyboard.press('ArrowRight')
    expect((await camera(page)).x).toBeCloseTo(beforeKey.x - 48, 1)
    await page.keyboard.press('+')
    expect((await camera(page)).scale).toBeGreaterThan(beforeKey.scale)
    await page.keyboard.press('Home')
    await frames(page)
    expect((await disks(page)).overlaps).toEqual([])
    const screenAnchor = {
      x: Math.floor(box.x + box.width / 2),
      y: Math.floor(box.y + box.height / 2),
    }
    const anchor = { x: screenAnchor.x - box.x, y: screenAnchor.y - box.y }
    const beforeZoom = await camera(page)
    await page.mouse.move(screenAnchor.x, screenAnchor.y)
    await page.keyboard.down('Control')
    try {
      await page.mouse.wheel(0, -100)
    } finally {
      await page.keyboard.up('Control')
    }
    await expect.poll(async () => (await camera(page)).scale).toBeGreaterThan(beforeZoom.scale)
    const afterZoom = await camera(page)
    expect((anchor.x - afterZoom.x) / afterZoom.scale).toBeCloseTo(
      (anchor.x - beforeZoom.x) / beforeZoom.scale,
      1,
    )
    expect((anchor.y - afterZoom.y) / afterZoom.scale).toBeCloseTo(
      (anchor.y - beforeZoom.y) / beforeZoom.scale,
      1,
    )
    measurements.wheelAndKeyboard = { beforeWheel, beforeKey, beforeZoom, afterZoom }
    await canvas.focus()
    await page.keyboard.press('Home')
    await frames(page)

    const hubIri = graph.edges[0].subject
    const selected = page.locator(`.node[data-iri="${hubIri}"]`)
    const selectionBefore = await camera(page)
    await selected.locator('.node-body').click()
    await expect(selected).toHaveAttribute('aria-pressed', 'true')
    await expect(page.locator('.graph-inspector')).toContainText('高阶中心')
    const selectedFit = await disks(page)
    measurements.selectedFromFit = selectedFit
    measurements.selectionCamera = { before: selectionBefore, after: await camera(page) }
    expect((await camera(page)).scale).toBeGreaterThanOrEqual(0.8)
    const selectedTextPixels = await selected
      .locator('.node-name')
      .evaluate(
        (name) =>
          parseFloat(getComputedStyle(name).fontSize) * (name as SVGTextElement).getScreenCTM()!.a,
      )
    expect(selectedTextPixels).toBeGreaterThanOrEqual(10)
    await capture(
      page,
      info,
      evidence,
      'nary-200-selected-readable',
      'Real mouse selection from fitted overview enters readable zoom; circles measured',
    )
    expect
      .soft(selectedFit.overlaps, 'Selecting at fit should retain zero circle overlaps')
      .toEqual([])
    // Re-fit with the actual selection retained: auto focus must not hide enlargement collisions.
    await canvas.focus()
    await page.keyboard.press('Home')
    await frames(page)
    await expect(selected).toHaveAttribute('aria-pressed', 'true')
    const refittedSelection = await disks(page)
    measurements.selectedAtFit = refittedSelection
    expect(refittedSelection.count).toBe(200)
    expect(
      refittedSelection.overlaps,
      'Selected circles must also remain separated after re-fit',
    ).toEqual([])
    expect(refittedSelection.outside).toEqual([])
    await capture(
      page,
      info,
      evidence,
      'nary-200-selected-fit',
      'Selection retained at real fitted camera; circle enlargement respects neighbouring space',
    )
    // The global keyboard collection must select the actual next node, even after paint order changes.
    await selected.focus()
    await page.keyboard.press('Tab')
    const focusedIri = await page.evaluate(() => (document.activeElement as SVGElement).dataset.iri)
    expect(focusedIri).not.toBe(hubIri)
    await page.keyboard.press('Enter')
    await expect(page.locator(`.node[data-iri="${focusedIri}"]`)).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await page
      .locator('.graph-inspector')
      .getByRole('button', { name: '关闭', exact: true })
      .click()
    const fitCamera = await camera(page)
    for (let index = 0; index < 10 && (await camera(page)).scale < 1; index++)
      await page.getByRole('button', { name: '放大', exact: true }).click()
    await frames(page)
    const readableCamera = await camera(page)
    expect(readableCamera.scale).toBeGreaterThanOrEqual(1)
    await expect(page.locator('.node-name')).toHaveCount(200)
    const readable = await page.locator('.node-name').evaluateAll((names) =>
      names.map((name) => {
        const matrix = (name as SVGTextElement).getScreenCTM()!
        return {
          text: name.textContent,
          fontPixels: parseFloat(getComputedStyle(name).fontSize) * matrix.a,
          lines: name.querySelectorAll('tspan').length,
        }
      }),
    )
    expect(readable.every((name) => name.fontPixels >= 10 && name.lines <= 2)).toBe(true)
    expect(readable.some((name) => name.text?.includes('…'))).toBe(true)
    measurements.readableZoom = { fitCamera, readableCamera, text: readable }
    await capture(
      page,
      info,
      evidence,
      'nary-200-readable-zoom',
      'Real zoom controls restore readable, clipped labels; zoomed viewport is a subset',
    )
    await canvas.focus()
    await page.keyboard.press('Home')
    await frames(page)
    expect((await disks(page)).overlaps).toEqual([])
    expect((await disks(page)).outside).toEqual([])
  } finally {
    measurements.navigationToStableRenderedMs = distribution(loads)
    measurements.browserApiMs = distribution(apiTimes)
    measurements.browser = page.context().browser()?.version()
    measurements.viewport = page.viewportSize()
    await attachJson(info, 'capacity-metrics', measurements)
  }
})

async function designer(page: Page, api: Api) {
  const seeded = await seedOntology(api)
  const positions = {
    [seeded.types[0].id]: { x: 600, y: 500 },
    [seeded.types[1].id]: { x: 1000, y: 500 },
  }
  await responseData(
    await api.put(`/api/v1/ontologies/${seeded.ontology.id}/canvas`, { data: { positions } }),
  )
  await page.goto(`/ontology/designer?ontology=${seeded.ontology.id}`)
  await expect(page.locator('.canvas .node')).toHaveCount(2)
  const closePool = page.getByRole('button', { name: '关闭资源面板', exact: true })
  if (await closePool.isVisible()) await closePool.click()
  const inspector = page.locator('.inspector').getByRole('button', { name: '关闭', exact: true })
  if (await inspector.isVisible()) await inspector.click()
  await page.locator('.canvas-tools').getByRole('button', { name: '适应窗口', exact: true }).click()
  await frames(page)
  return {
    ...seeded,
    positions,
    node: page.locator(`.node[data-selection="${seeded.types[0].id}"]`),
  }
}

async function position(node: Locator) {
  return node.evaluate((element) => ({
    x: parseFloat((element as HTMLElement).style.left),
    y: parseFloat((element as HTMLElement).style.top),
  }))
}

async function observePointer(canvas: Locator, page: Page) {
  const prefix = uniqueName('native-pointer-')
  const event = page
    .waitForEvent('console', {
      predicate: (message) => message.text().startsWith(prefix),
      timeout: 10_000,
    })
    .then(
      (message) =>
        JSON.parse(message.text().slice(prefix.length)) as {
          pointerId: number
          pointerType: string
          isTrusted: boolean
        },
    )
  await canvas.evaluate((element, prefix) => {
    // Install observation before input; never dispatch events or change Vue/graph state.
    element.addEventListener(
      'pointerdown',
      (event) => {
        const pointer = event as PointerEvent
        // eslint-disable-next-line no-console -- Forward one trusted native input observation to Playwright.
        console.debug(
          `${prefix}${JSON.stringify({
            pointerId: pointer.pointerId,
            pointerType: pointer.pointerType,
            isTrusted: pointer.isTrusted,
          })}`,
        )
      },
      { capture: true, once: true },
    )
  }, prefix)
  return { event }
}

test('Designer real mouse PointerEvents: threshold, capture, Escape, cancel and layout-only save', async ({
  signedIn: page,
  identity,
  evidence,
}, info) => {
  const seeded = await designer(page, identity.api)
  const node = seeded.node
  const canvas = page.locator('.canvas')
  const original = await position(node)
  const beforeOntology = await getData<Ontology>(identity.api, `/ontologies/${seeded.ontology.id}`)
  const writes: string[] = []
  page.on('request', (request) => {
    if (request.method() !== 'GET' && request.url().includes('/api/v1/'))
      writes.push(`${request.method()} ${new URL(request.url()).pathname}`)
  })
  const start = async () => {
    const box = (await node.boundingBox())!
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    const observed = await observePointer(canvas, page)
    await page.mouse.down()
    return { box, event: await observed.event }
  }
  const clicked = await start()
  expect(clicked.event).toMatchObject({ pointerType: 'mouse', isTrusted: true })
  await page.mouse.move(
    clicked.box.x + clicked.box.width / 2 + 2,
    clicked.box.y + clicked.box.height / 2,
  )
  await page.mouse.up()
  expect(await position(node)).toEqual(original)
  await expect(page.getByRole('button', { name: '保存布局', exact: true })).toBeDisabled()
  await node.focus()
  await page.keyboard.press('Enter')
  await expect(node).toHaveAttribute('aria-pressed', 'true')
  const drag = await start()
  expect(
    await canvas.evaluate((element, id) => element.hasPointerCapture(id), drag.event.pointerId),
  ).toBe(true)
  await page.mouse.move(
    drag.box.x + drag.box.width / 2 + 60,
    drag.box.y + drag.box.height / 2 + 30,
    { steps: 6 },
  )
  await expect.poll(async () => (await position(node)).x).not.toBe(original.x)
  await capture(
    page,
    info,
    evidence,
    'designer-mouse-active-drag',
    'Native mouse PointerEvent and active pointer capture before Escape',
  )
  await page.keyboard.press('Escape')
  await expect.poll(() => position(node)).toEqual(original)
  expect(
    await canvas.evaluate((element, id) => element.hasPointerCapture(id), drag.event.pointerId),
  ).toBe(false)
  await page.mouse.up()
  await expect(node).not.toHaveClass(/dragging/)
  await expect(page.getByRole('button', { name: '保存布局', exact: true })).toBeDisabled()
  expect(writes).toEqual([])
  for (const action of ['cancel', 'save'] as const) {
    const move = await start()
    await page.mouse.move(
      move.box.x + move.box.width / 2 + 45,
      move.box.y + move.box.height / 2 + 20,
      { steps: 5 },
    )
    await page.mouse.up()
    const moved = await position(node)
    expect(moved.x).not.toBe(original.x)
    await expect(page.getByRole('button', { name: '保存布局', exact: true })).toBeEnabled()
    if (action === 'cancel') {
      await page.getByRole('button', { name: '恢复已保存布局', exact: true }).click()
      expect(await position(node)).toEqual(original)
      expect(writes).toEqual([])
    } else {
      const saved = page.waitForResponse(
        (response) =>
          response.request().method() === 'PUT' &&
          new URL(response.url()).pathname === `/api/v1/ontologies/${seeded.ontology.id}/canvas`,
      )
      await page.getByRole('button', { name: '保存布局', exact: true }).click()
      await responseData(await saved)
      const persisted = await getData<components['schemas']['CanvasLayoutOut']>(
        identity.api,
        `/ontologies/${seeded.ontology.id}/canvas`,
      )
      // DOM style serialisation rounds layout coordinates; the API retains full floating precision.
      const savedPoint = persisted.positions[String(seeded.types[0].id)] as {
        x: number
        y: number
      }
      expect(savedPoint.x).toBeCloseTo(moved.x, 3)
      expect(savedPoint.y).toBeCloseTo(moved.y, 3)
      expect(writes).toEqual([`PUT /api/v1/ontologies/${seeded.ontology.id}/canvas`])
    }
  }
  const afterOntology = await getData<Ontology>(identity.api, `/ontologies/${seeded.ontology.id}`)
  expect(afterOntology.edit_revision).toBe(beforeOntology.edit_revision)
  expect(afterOntology.current_revision).toBe(beforeOntology.current_revision)
  await capture(
    page,
    info,
    evidence,
    'designer-mouse-saved',
    'Real API save changes layout only; ontology semantic revisions are unchanged',
  )
  await attachJson(info, 'designer-mouse-metrics', {
    pointer: clicked.event,
    original,
    saved: await position(node),
    semanticRevision: afterOntology.current_revision,
    writes,
  })
})

test.describe('Chromium native touch protocol emulation (physical touch/pen hardware NOT_RUN)', () => {
  test.use({ hasTouch: true })
  test('Designer touch drag and pointercancel use browser-generated trusted PointerEvents', async ({
    signedIn: page,
    identity,
    evidence,
  }, info) => {
    const seeded = await designer(page, identity.api)
    const node = seeded.node
    const canvas = page.locator('.canvas')
    expect(await page.evaluate(() => navigator.maxTouchPoints)).toBeGreaterThan(0)
    const client = await page.context().newCDPSession(page)
    const original = await position(node)
    const box = (await node.boundingBox())!
    const x = box.x + box.width / 2,
      y = box.y + box.height / 2
    const observed = await observePointer(canvas, page)
    let touchActive = false
    try {
      await client.send('Input.dispatchTouchEvent', {
        type: 'touchStart',
        touchPoints: [{ x, y, id: 1 }],
      })
      touchActive = true
      const event = await observed.event
      expect(event).toMatchObject({ pointerType: 'touch', isTrusted: true })
      expect(
        await canvas.evaluate((element, id) => element.hasPointerCapture(id), event.pointerId),
      ).toBe(true)
      await client.send('Input.dispatchTouchEvent', {
        type: 'touchMove',
        touchPoints: [{ x: x + 55, y: y + 25, id: 1 }],
      })
      await expect.poll(async () => (await position(node)).x).not.toBe(original.x)
      await capture(
        page,
        info,
        evidence,
        'designer-touch-active',
        'Chromium trusted native touch-protocol emulation; no physical device claim',
      )
      await client.send('Input.dispatchTouchEvent', { type: 'touchCancel', touchPoints: [] })
      touchActive = false
      await expect.poll(() => position(node)).toEqual(original)
      await expect(node).not.toHaveClass(/dragging/)
      expect(
        await canvas.evaluate((element, id) => element.hasPointerCapture(id), event.pointerId),
      ).toBe(false)
      await expect(page.getByRole('button', { name: '保存布局', exact: true })).toBeDisabled()
      // A fresh gesture must work after cancellation and commit only the new movement.
      await client.send('Input.dispatchTouchEvent', {
        type: 'touchStart',
        touchPoints: [{ x, y, id: 2 }],
      })
      touchActive = true
      await client.send('Input.dispatchTouchEvent', {
        type: 'touchMove',
        touchPoints: [{ x: x + 40, y: y + 20, id: 2 }],
      })
      await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
      touchActive = false
      await expect(page.getByRole('button', { name: '保存布局', exact: true })).toBeEnabled()
      await page.getByRole('button', { name: '恢复已保存布局', exact: true }).click()
      expect(await position(node)).toEqual(original)
      await capture(
        page,
        info,
        evidence,
        'designer-touch-cancelled',
        'Touch cancel releases capture, restores origin and allows the next gesture',
      )
      await attachJson(info, 'designer-touch-metrics', {
        mode: 'Chromium CDP touch emulation; physical hardware NOT_RUN',
        event,
        original,
        cancelled: await position(node),
      })
    } finally {
      try {
        if (touchActive)
          await client.send('Input.dispatchTouchEvent', { type: 'touchCancel', touchPoints: [] })
      } finally {
        await client.detach()
      }
    }
  })
})
