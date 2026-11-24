import assert from 'node:assert/strict'
import { test } from 'node:test'

import { graphPaths, resolveLayout } from '../components/graphLayout.ts'
import { nodeDisplayScales } from '../components/graphViewportPolicy.ts'

const node = (iri, id) => ({
  id,
  iri,
  graph_revision_id: 1,
  type_iri: 'urn:example:Company',
  row_key: iri,
  attrs: { name: iri },
  distance: 0,
})
const edge = (id, subject, object_, kind = 'DIRECT') => ({
  id,
  subject,
  object_,
  kind,
  predicate: 'urn:example:owns',
  graph_revision_id: 1,
  props: null,
})
const context = {
  config: { hierarchy_relation_iri: 'urn:example:owns' },
  fields: [{ iri: 'urn:example:owns', name: 'owns', kind: 'RELATION' }],
}
const model = () => ({
  nodes: [node('a', 1), node('b', 2), node('c', 3)],
  edges: [edge(11, 'a', 'b'), edge(12, 'b', 'c'), edge(13, 'a', 'c')],
})
const identity = (item) => `${item.kind}:${item.id}`
const point = (path, t) => {
  assert.match(path, /^M .* Q /)
  const [sx, sy, cx, cy, ex, ey] = path.match(/-?\d*\.?\d+(?:e[+-]?\d+)?/gi).map(Number)
  return {
    x: (1 - t) ** 2 * sx + 2 * (1 - t) * t * cx + t ** 2 * ex,
    y: (1 - t) ** 2 * sy + 2 * (1 - t) * t * cy + t ** 2 * ey,
  }
}
const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y)
const sample = (path) => Array.from({ length: 801 }, (_, index) => point(path, index / 800))
const geometryByIdentity = (paths) =>
  Object.fromEntries(
    paths.map((item) => [identity(item), item]).sort(([a], [b]) => a.localeCompare(b)),
  )
const render = (layout, nodes = layout.nodes, scale = 1, important = new Set()) => {
  const scales = nodeDisplayScales(nodes, important, scale)
  const radius = (item) => 42 * scales.get(item.iri)
  const paths = graphPaths(nodes, layout.edges, layout.edgePaths, {
    radius,
    originalNodes: layout.nodes,
    avoidNodes: true,
    scale,
  })
  return { paths, radius }
}
function assertClearance(paths, nodes, radius, scale, margin = 7 / scale) {
  for (const path of paths) {
    const points = sample(path.path)
    for (const node of nodes.filter(
      (node) => node.iri !== path.subject && node.iri !== path.object_,
    )) {
      assert.ok(
        Math.min(...points.map((point) => distance(point, node))) > radius(node) + margin,
        `${identity(path)} crosses ${node.iri} or its hit margin at scale ${scale}`,
      )
    }
    const source = nodes.find((node) => node.iri === path.subject)
    const target = nodes.find((node) => node.iri === path.object_)
    assert.ok(Math.abs(distance(points[0], source) - radius(source)) < 1e-7)
    assert.ok(Math.abs(distance(points.at(-1), target) - radius(target)) < 1e-7)
    assert.ok(distance(point(path.path, 0.5), path.label) < 1e-7)
    for (const point of points) {
      assert.ok(Number.isFinite(point.x) && Number.isFinite(point.y))
      assert.ok(point.x >= path.bounds.x - 1e-7 && point.y >= path.bounds.y - 1e-7)
      assert.ok(point.x <= path.bounds.x + path.bounds.width + 1e-7)
      assert.ok(point.y <= path.bounds.y + path.bounds.height + 1e-7)
    }
  }
}
function assertExclusiveHit(paths, nodes, radius, scale) {
  const samples = new Map(paths.map((item) => [identity(item), sample(item.path)]))
  for (const path of paths) {
    const otherPoints = paths
      .filter((other) => identity(other) !== identity(path))
      .flatMap((other) => samples.get(identity(other)))
    // A continuous, usable centerline segment is outside other edges' 7px half hit strokes.
    let run = 0
    let longest = 0
    let previous = null
    for (const point of samples.get(identity(path))) {
      const clear =
        otherPoints.every((other) => distance(point, other) * scale > 8) &&
        nodes.every((node) => distance(point, node) > radius(node) + 2 / scale)
      run = clear && previous ? run + distance(point, previous) * scale : 0
      longest = Math.max(longest, run)
      previous = clear ? point : null
    }
    assert.ok(
      longest >= 6,
      `${identity(path)} needs a separate visible hit segment at scale ${scale}`,
    )
  }
}

for (const mode of ['equity_tree', 'clan_tree']) {
  for (const scale of [0.5, 1, 3]) {
    test(`test_${mode}_multilevel_facts_have_clear_independent_hit_segments_at_${scale}`, () => {
      const graph = model()
      const before = structuredClone(graph)
      const layout = resolveLayout(mode, false).compute(graph, context)
      assert.equal(layout.nodes.length, 3)
      assert.equal(layout.edges.length, 3)
      const { paths, radius } = render(layout, layout.nodes, scale)
      assertClearance(paths, layout.nodes, radius, scale)
      assertExclusiveHit(paths, layout.nodes, radius, scale)
      assert.deepEqual(paths.map(identity).sort(), graph.edges.map(identity).sort())
      assert.deepEqual(graph, before, 'routing never changes source facts or node data')
    })
  }

  test(`test_${mode}_same_numeric_kinds_and_parallel_facts_keep_separate_routes`, () => {
    const graph = model()
    graph.edges.push(edge(13, 'a', 'c', 'DERIVED'), edge(14, 'a', 'c'))
    const layout = resolveLayout(mode, false).compute(graph, context)
    const { paths, radius } = render(layout)
    assertClearance(paths, layout.nodes, radius, 1)
    assertExclusiveHit(paths, layout.nodes, radius, 1)
    const reversed = { ...layout, edges: [...layout.edges].reverse() }
    assert.deepEqual(
      geometryByIdentity(render(reversed, [...layout.nodes].reverse()).paths),
      geometryByIdentity(paths),
    )
    assert.deepEqual(paths.map(identity).sort(), graph.edges.map(identity).sort())
  })

  test(`test_${mode}_source_target_obstacle_drag_and_restore_use_current_geometry`, () => {
    const layout = resolveLayout(mode, false).compute(model(), context)
    const before = structuredClone(layout)
    const initial = render(layout).paths
    for (const iri of ['a', 'b', 'c']) {
      const moved = layout.nodes.map((node) =>
        node.iri === iri ? { ...node, x: node.x + 35, y: node.y + 20 } : node,
      )
      const { paths, radius } = render(layout, moved, 0.5, new Set(['b']))
      assertClearance(paths, moved, radius, 0.5)
      assertExclusiveHit(paths, moved, radius, 0.5)
      assert.notEqual(
        paths.find((path) => path.id === 13).path,
        initial.find((path) => path.id === 13).path,
      )
    }
    assert.deepEqual(
      render(layout).paths,
      initial,
      'restoring the same node positions restores routes',
    )
    assert.deepEqual(layout, before)
  })

  test(`test_${mode}_minimum_scale_and_selected_obstacle_stay_finite_and_clear`, () => {
    const layout = resolveLayout(mode, false).compute(model(), context)
    const { paths, radius } = render(layout, layout.nodes, 0.12, new Set(['b']))
    const long = paths.filter((path) => path.id === 13)
    assertClearance(long, layout.nodes, radius, 0.12, 0)
    // Short adjacent edges at minimum zoom need not have a full independent 14px strip.
    assert.ok(paths.every((path) => !/NaN|Infinity/.test(path.path)))
  })
}

test('test_routing_preserves_reciprocal_direction_self_loops_and_missing_endpoints', () => {
  const nodes = [
    { ...node('a', 1), x: 0, y: 0 },
    { ...node('b', 2), x: 0, y: 170 },
    { ...node('c', 3), x: 0, y: 340 },
  ]
  const edges = [
    edge(1, 'a', 'c'),
    edge(1, 'c', 'a', 'DERIVED'),
    edge(2, 'a', 'a'),
    edge(3, 'a', 'absent'),
  ]
  const options = { radius: 42, originalNodes: nodes, avoidNodes: true, scale: 1 }
  const paths = graphPaths(nodes, edges, undefined, options)
  assertClearance(paths.slice(0, 2), nodes, () => 42, 1)
  assertExclusiveHit(paths.slice(0, 2), nodes, () => 42, 1)
  assert.deepEqual(
    geometryByIdentity(graphPaths(nodes, [...edges].reverse(), undefined, options)),
    geometryByIdentity(paths),
  )
  const legacy = graphPaths(nodes, edges, undefined, { radius: 42, originalNodes: nodes })
  assert.equal(paths.find((path) => path.id === 2).path, legacy.find((path) => path.id === 2).path)
  assert.equal(paths.find((path) => path.id === 3).path, '')
})

test('test_dragging_third_party_node_into_previously_clear_path_recomputes_route', () => {
  const nodes = [
    { ...node('a', 1), x: 0, y: 0 },
    { ...node('b', 2), x: 200, y: 170 },
    { ...node('c', 3), x: 0, y: 340 },
  ]
  const layout = { nodes, edges: [edge(1, 'a', 'c')] }
  const initial = render(layout).paths
  const moved = nodes.map((node) => (node.iri === 'b' ? { ...node, x: 0 } : node))
  const { paths, radius } = render(layout, moved)
  assert.notEqual(paths[0].path, initial[0].path)
  assertClearance(paths, moved, radius, 1)
  assert.deepEqual(render(layout).paths, initial)
})

test('test_routing_is_opt_in_and_existing_tree_overrides_remain_authoritative', () => {
  for (const mode of ['org_tree', 'impact']) {
    const graph = { nodes: [node('a', 1), node('c', 3)], edges: [edge(1, 'a', 'c')] }
    const layout = resolveLayout(mode, false).compute(graph)
    const options = { radius: 42, originalNodes: layout.nodes }
    const legacy = graphPaths(layout.nodes, graph.edges, layout.edgePaths, options)
    assert.deepEqual(
      graphPaths(layout.nodes, graph.edges, layout.edgePaths, { ...options, avoidNodes: true }),
      legacy,
    )
  }
  const layout = resolveLayout('equity_tree', false).compute(model(), context)
  const legacy = graphPaths(layout.nodes, layout.edges, layout.edgePaths, {
    radius: 42,
    originalNodes: layout.nodes,
  })
  assert.equal(legacy.find((path) => path.id === 13).path, 'M 140 122 Q 140 250 140 378')
})

test('test_coincident_or_trapped_endpoints_keep_bounded_finite_geometry', () => {
  const nodes = [
    { ...node('a', 1), x: 0, y: 0 },
    { ...node('b', 2), x: 0, y: 0 },
    { ...node('c', 3), x: 0, y: 300 },
  ]
  for (const edges of [[edge(1, 'a', 'b')], [edge(1, 'a', 'c')]]) {
    const paths = graphPaths(nodes, edges, undefined, {
      radius: 42,
      originalNodes: nodes,
      avoidNodes: true,
    })
    assert.ok(paths.every((path) => !/NaN|Infinity/.test(path.path)))
  }
})
