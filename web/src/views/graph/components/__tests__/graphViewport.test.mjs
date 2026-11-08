import assert from 'node:assert/strict'
import { test } from 'node:test'

import { graphPaths } from '../graphLayout.ts'
import {
  centerCamera,
  dragPosition,
  fitCamera,
  isDrag,
  MAX_SCALE,
  mergePositions,
  MIN_SCALE,
  NODE_RADIUS,
  nodeNameLines,
  pointBounds,
  resizeCamera,
  screenPoint,
  showGraphLabel,
  viewportBounds,
  wheelCamera,
  worldPoint,
  zoomAt,
} from '../graphViewport.ts'
import { resolveLayout } from '../layouts/index.ts'

const near = (actual, expected) =>
  assert.ok(Math.abs(actual - expected) < 1e-8, `${actual} ≠ ${expected}`)
const size = { width: 900, height: 600 }
const camera = { x: 31, y: -48, scale: 1.4 }
const anchor = { x: 360, y: 170 }
const wheel = (deltaX, deltaY, deltaMode = 0, modifiers = {}) => ({
  deltaX,
  deltaY,
  deltaMode,
  ctrlKey: false,
  metaKey: false,
  ...modifiers,
})
const node = (iri, x = 100, y = 100) => ({
  id: 1,
  graph_revision_id: 1,
  iri,
  type_iri: 'Thing',
  row_key: iri,
  attrs: { name: iri },
  distance: 0,
  x,
  y,
})
const edge = (id, subject = 'a', object_ = 'b', kind = 'DIRECT') => ({
  id,
  graph_revision_id: 1,
  subject,
  object_,
  predicate: 'https://example.org/rel',
  kind,
})

test('ordinary wheel pans in pixels, lines and pages without changing zoom', () => {
  assert.deepEqual(wheelCamera(camera, wheel(3, 5), anchor, size), { ...camera, x: 28, y: -53 })
  assert.deepEqual(wheelCamera(camera, wheel(-2, 3, 1), anchor, size), { ...camera, x: 63, y: -96 })
  assert.deepEqual(wheelCamera(camera, wheel(1, -1, 2), anchor, size), {
    ...camera,
    x: -869,
    y: 552,
  })
  assert.deepEqual(camera, { x: 31, y: -48, scale: 1.4 })
})

test('Ctrl and Meta wheel preserve the exact world point beneath the pointer', () => {
  for (const modifier of ['ctrlKey', 'metaKey']) {
    const result = wheelCamera(camera, wheel(0, -120, 0, { [modifier]: true }), anchor, size)
    const before = worldPoint(anchor, camera)
    const after = worldPoint(anchor, result)
    near(before.x, after.x)
    near(before.y, after.y)
    assert.ok(result.scale > camera.scale)
  }
  for (const scale of [-100, 999]) {
    const result = zoomAt(camera, anchor, scale)
    assert.equal(result.scale, scale < 0 ? MIN_SCALE : MAX_SCALE)
    near(worldPoint(anchor, result).x, worldPoint(anchor, camera).x)
  }
})

test('fit includes negative coordinates, centers visible bounds and keeps padding', () => {
  const bounds = pointBounds([
    { x: -400, y: -90 },
    { x: 780, y: 520 },
  ])
  const fitted = fitCamera(bounds, size)
  const left = screenPoint(bounds, fitted)
  const right = screenPoint({ x: bounds.x + bounds.width, y: bounds.y + bounds.height }, fitted)
  assert.ok(left.x >= 64 - 1e-8 && left.y >= 64 - 1e-8)
  assert.ok(right.x <= size.width - 64 + 1e-8 && right.y <= size.height - 64 + 1e-8)
  near((left.x + right.x) / 2, size.width / 2)
  assert.ok(Object.values(fitCamera(pointBounds([]), size)).every(Number.isFinite))
})

test('minimap location centers a world point without changing zoom; viewport inverts camera', () => {
  const focused = centerCamera(camera, { x: -120, y: 670 }, size)
  const centered = screenPoint({ x: -120, y: 670 }, focused)
  near(centered.x, size.width / 2)
  near(centered.y, size.height / 2)
  assert.equal(focused.scale, camera.scale)
  const visible = viewportBounds(camera, size)
  near(screenPoint(visible, camera).x, 0)
  near(
    screenPoint({ x: visible.x + visible.width, y: visible.y + visible.height }, camera).y,
    size.height,
  )
})

test('node drag uses screen threshold and inverse zoom, while camera drag uses screen pixels', () => {
  assert.equal(isDrag({ x: 0, y: 0 }, { x: 4, y: 0 }), false)
  assert.equal(isDrag({ x: 0, y: 0 }, { x: 3, y: 3 }), true)
  const start = { x: 300, y: 400 }
  const current = { x: 350, y: 420 }
  assert.deepEqual(dragPosition({ x: 100, y: 120 }, start, current, 0.5), { x: 200, y: 160 })
  assert.deepEqual(dragPosition(camera, start, current, 1), { x: 81, y: -28 })
})

test('inspector open and close preserve the center world point without zoom or cumulative drift', () => {
  const smaller = { width: 560, height: 550 }
  const resized = resizeCamera(camera, size, smaller)
  const before = worldPoint({ x: size.width / 2, y: size.height / 2 }, camera)
  const after = worldPoint({ x: smaller.width / 2, y: smaller.height / 2 }, resized)
  near(before.x, after.x)
  near(before.y, after.y)
  assert.equal(resized.scale, camera.scale)
  assert.deepEqual(resizeCamera(resized, smaller, size), camera)
})

test('incremental expansion and filtering preserve all existing and hidden coordinates', () => {
  const previous = { a: { x: 680, y: -180 }, hidden: { x: 200, y: 500 } }
  const expanded = mergePositions(previous, [node('a', 100, 100), node('b', 101, 100)], [edge(1)])
  assert.deepEqual(expanded.a, previous.a)
  assert.deepEqual(expanded.hidden, previous.hidden)
  assert.ok(Math.hypot(expanded.a.x - expanded.b.x, expanded.a.y - expanded.b.y) >= 96)
  assert.deepEqual(previous, { a: { x: 680, y: -180 }, hidden: { x: 200, y: 500 } })
  const filtered = mergePositions(expanded, [node('b', 900, 800)], [])
  const restored = mergePositions(filtered, [node('a'), node('b'), node('hidden')], [edge(1)])
  assert.deepEqual(restored, expanded)
})

test('full layout reset accepts new positions, and metadata never enters the position cache', () => {
  const points = mergePositions({}, [node('a', 12, 34)], [])
  assert.deepEqual(points, { a: { x: 12, y: 34 } })
  assert.deepEqual(mergePositions({}, [node('a', 99, 88)], []), { a: { x: 99, y: 88 } })
})

test('distant zoom reduces ordinary labels but always retains selected labels', () => {
  for (const kind of ['node', 'edge']) {
    assert.equal(showGraphLabel(0.2, false, kind), false)
    assert.equal(showGraphLabel(0.2, true, kind), true)
    assert.equal(showGraphLabel(1, false, kind), true)
  }
  assert.equal(showGraphLabel(0.55, false, 'node'), false)
  assert.equal(showGraphLabel(0.65, false, 'node'), true)
  assert.equal(showGraphLabel(0.55, false, 'edge'), false)
})

test('business names use at most two compact lines without splitting Unicode code points', () => {
  assert.deepEqual(nodeNameLines('北京示例科技有限公司研发中心'), ['北京示例科', '技有限公…'])
  assert.deepEqual(nodeNameLines('Short name'), ['Short name'])
  const lines = nodeNameLines('😀😀😀😀😀😀😀😀😀😀😀')
  assert.equal(lines.length, 2)
  assert.ok(!lines.some((line) => /[\uD800-\uDBFF](?![\uDC00-\uDFFF])/.test(line)))
})

test('circular edges clip at node boundary and self loops remain external with separate labels', () => {
  const nodes = [node('a', 100, 100), node('b', 500, 250)]
  const paths = graphPaths(nodes, [edge(1), edge(2, 'a', 'a'), edge(3, 'a', 'a')], undefined, {
    radius: NODE_RADIUS,
    originalNodes: nodes,
  })
  const values = paths[0].path.match(/-?\d*\.?\d+(?:e[+-]?\d+)?/gi).map(Number)
  near(Math.hypot(values[0] - 100, values[1] - 100), NODE_RADIUS)
  near(Math.hypot(values.at(-2) - 500, values.at(-1) - 250), NODE_RADIUS)
  assert.notEqual(paths[1].path, paths[2].path)
  assert.ok(paths[1].label.y < 100 - NODE_RADIUS && paths[2].label.y < paths[1].label.y)
})

test('reordered parallel/reciprocal/derived facts retain stable distinct curves and identities', () => {
  const nodes = [node('a'), node('b', 400, 200)]
  const edges = [edge(2), edge(1), edge(1, 'a', 'b', 'DERIVED'), edge(3, 'b', 'a')]
  const options = { radius: NODE_RADIUS, originalNodes: nodes }
  const paths = graphPaths(nodes, edges, undefined, options)
  const reversed = graphPaths(nodes, [...edges].reverse(), undefined, options)
  assert.deepEqual(paths, reversed)
  assert.equal(new Set(paths.map((item) => item.path)).size, 4)
  assert.equal(new Set(paths.map((item) => item.key)).size, 4)
})

test('tree overrides follow dragged endpoints and preserve fact direction including impact layout', () => {
  for (const id of ['org_tree', 'impact']) {
    const edges = [edge(1, 'a', 'b')]
    const layout = resolveLayout(id, false).compute({ nodes: [node('a'), node('b')], edges })
    const moved = layout.nodes.map((item) => ({ ...item, x: item.x + (item.iri === 'a' ? 99 : 0) }))
    const [path] = graphPaths(moved, edges, layout.edgePaths, {
      radius: NODE_RADIUS,
      originalNodes: layout.nodes,
    })
    const values = path.path.match(/-?\d*\.?\d+(?:e[+-]?\d+)?/gi).map(Number)
    const source = moved.find((item) => item.iri === 'a')
    const target = moved.find((item) => item.iri === 'b')
    near(Math.hypot(values[0] - source.x, values[1] - source.y), NODE_RADIUS)
    near(Math.hypot(values.at(-2) - target.x, values.at(-1) - target.y), NODE_RADIUS)
    assert.ok(!/NaN|Infinity/.test(path.path))
  }
})

test('coincident centers and absent endpoints do not produce invalid SVG paths', () => {
  const nodes = [node('a'), node('b')]
  const paths = graphPaths(nodes, [edge(1), edge(2, 'a', 'absent')], undefined, {
    radius: NODE_RADIUS,
    originalNodes: nodes,
  })
  assert.ok(!/NaN|Infinity/.test(paths[0].path))
  assert.equal(paths[1].path, '')
})
