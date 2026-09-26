import assert from 'node:assert/strict'
import { test } from 'node:test'

import { graphPaths } from '../components/graphLayout.ts'
import { LAYOUT_IDS, resolveLayout } from '../components/layouts/index.ts'

const node = (iri, type, distance = 0, attrs = {}) => ({
  id: iri.charCodeAt(0),
  graph_revision_id: 1,
  iri,
  type_iri: type,
  row_key: iri,
  attrs,
  distance,
})
const edge = (id, subject, object_, kind = 'DIRECT', props = null, predicate = 'rel') => ({
  id,
  graph_revision_id: 1,
  subject,
  object_,
  predicate,
  kind,
  props,
})
const layoutOf = (id, nodes, edges = []) => resolveLayout(id, false).compute({ nodes, edges })

test('overview groups by type, retains isolated nodes, and stays inside its viewbox', () => {
  const nodes = [
    node('a', 'Person'),
    node('b', 'Project'),
    node('c', 'Person'),
    node('alone', 'Other'),
  ]
  const layout = layoutOf('type_grid', nodes)
  assert.equal(layout.nodes.length, nodes.length)
  assert.deepEqual(
    layout.groups.map((group) => group.type),
    ['Person', 'Project', 'Other'],
  )
  assert.ok(
    layout.nodes.every(
      (item) =>
        item.x >= 80 && item.x + 80 <= layout.width && item.y >= 26 && item.y + 26 <= layout.height,
    ),
  )
})

test('registry exposes every P0 form id and default fallback by center', () => {
  assert.deepEqual(LAYOUT_IDS, [
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
  ])
  assert.equal(resolveLayout(undefined, true).id, 'ring')
  assert.equal(resolveLayout(undefined, false).id, 'type_grid')
  assert.equal(resolveLayout('nonexistent', true).id, 'ring')
})

test('neighborhood puts root in the center and second degree outside first degree', () => {
  const layout = layoutOf('ring', [
    node('a', 'Person'),
    node('b', 'Person', 1),
    node('c', 'Project', 2),
  ])
  const [root, first, second] = layout.nodes
  assert.equal(root.x, layout.width / 2)
  assert.equal(root.y, layout.height / 2)
  const radius = (item) => Math.hypot(item.x - root.x, item.y - root.y)
  assert.ok(radius(second) > radius(first))
})

test('org tree layers child below parent with elbow overrides', () => {
  const nodes = [node('root', 'Dept'), node('child', 'Dept'), node('grand', 'Dept')]
  const edges = [
    edge(1, 'child', 'root', 'DIRECT', null, 'belongs_to'),
    edge(2, 'grand', 'child', 'DIRECT', null, 'belongs_to'),
  ]
  const layout = layoutOf('org_tree', nodes, edges)
  const byIri = new Map(layout.nodes.map((item) => [item.iri, item]))
  assert.ok(byIri.get('grand').y > byIri.get('child').y)
  assert.ok(byIri.get('child').y > byIri.get('root').y)
  // 树形折线覆写父边；其余边退回默认渲染
  assert.ok(layout.edgePaths[1].path.startsWith('M'))
  const paths = graphPaths(layout.nodes, edges, layout.edgePaths)
  assert.ok(paths.every((item) => !/NaN|Infinity/.test(item.path)))
})

test('org tree falls back to grid when every node sits on a cycle', () => {
  const nodes = [node('a', 'Dept'), node('b', 'Dept')]
  const edges = [edge(1, 'a', 'b'), edge(2, 'b', 'a')]
  const layout = layoutOf('org_tree', nodes, edges)
  assert.deepEqual(
    layout.groups.map((group) => group.type),
    ['Dept'],
  )
})

test('equity penetration layers shareholders above investees', () => {
  const nodes = [node('holder', 'Person'), node('target', 'Enterprise'), node('mid', 'Enterprise')]
  const edges = [
    edge(1, 'holder', 'mid', 'DIRECT', { pct: 50 }, 'holds_equity_in'),
    edge(2, 'mid', 'target', 'DIRECT', { pct: 40 }, 'holds_equity_in'),
  ]
  const layout = layoutOf('equity_tree', nodes, edges)
  const byIri = new Map(layout.nodes.map((item) => [item.iri, item]))
  assert.ok(byIri.get('holder').y < byIri.get('mid').y)
  assert.ok(byIri.get('mid').y < byIri.get('target').y)
})

test('timeline arranges lanes per type and orders by first date attribute', () => {
  const nodes = [
    node('early', 'Contract', 0, { signedDate: '2024-01-01' }),
    node('late', 'Contract', 0, { signedDate: '2024-06-01' }),
    node('person', 'Person', 0, { name: '无日期' }),
  ]
  const layout = layoutOf('timeline', nodes, [])
  const byIri = new Map(layout.nodes.map((item) => [item.iri, item]))
  assert.ok(byIri.get('late').x > byIri.get('early').x)
  assert.ok(byIri.get('person').x > byIri.get('late').x)
  assert.notEqual(byIri.get('early').y, byIri.get('person').y, '不同类型必须在不同泳道')
})

test('supply chain puts participants on opposite columns', () => {
  const nodes = [
    node('supplier', 'Enterprise'),
    node('buyer', 'Enterprise'),
    node('dual', 'Enterprise'),
  ]
  const edges = [edge(1, 'supplier', 'buyer'), edge(2, 'dual', 'buyer')]
  const layout = layoutOf('supply_chain', nodes, edges)
  const byIri = new Map(layout.nodes.map((item) => [item.iri, item]))
  assert.ok(byIri.get('supplier').x < byIri.get('buyer').x)
  assert.ok(byIri.get('dual').x < byIri.get('buyer').x)
})

test('schema aggregates instances into typed nodes with counts', () => {
  const nodes = [node('a', 'Person'), node('b', 'Person'), node('c', 'Project')]
  const edges = [
    edge(1, 'a', 'c', 'DIRECT', null, 'works_on'),
    edge(2, 'b', 'c', 'DIRECT', null, 'works_on'),
  ]
  const layout = layoutOf('schema', nodes, edges)
  assert.equal(layout.nodes.length, 2, '类型节点数 = 实体类型数')
  const person = layout.nodes.find((item) => item.iri === 'Person')
  assert.equal(person.attrs.__typeCount__, 2)
})

test('edge props are available to renderer and keep stable keys', () => {
  const layout = layoutOf('type_grid', [node('a', 'Person'), node('b', 'Project')])
  const paths = graphPaths(layout.nodes, [
    edge(1, 'a', 'b', 'DIRECT', { pct: '60' }, 'holds'),
    edge(2, 'a', 'b', 'DERIVED', { pct: '27.5' }, 'indirectly_holds'),
  ])
  assert.equal(paths[0].props.pct, '60')
  assert.equal(paths[1].kind, 'DERIVED')
  assert.equal(new Set(paths.map((item) => item.key)).size, 2)
})

test('parallel, reciprocal, and derived facts have separate curves and stable keys', () => {
  const layout = layoutOf('type_grid', [node('a', 'Person'), node('b', 'Project')])
  const edges = [
    edge(1, 'a', 'b'),
    edge(2, 'a', 'b'),
    edge(3, 'b', 'a'),
    edge(1, 'a', 'b', 'DERIVED'),
  ]
  const paths = graphPaths(layout.nodes, edges)
  assert.equal(paths.length, 4)
  assert.equal(new Set(paths.map((path) => path.key)).size, 4)
  assert.equal(new Set(paths.map((path) => path.path)).size, 4)
  assert.ok(paths.every((path) => !/NaN|Infinity/.test(path.path)))
})

test('self loops remain separate and empty graphs are valid', () => {
  const layout = layoutOf('type_grid', [node('a', 'Person')])
  const paths = graphPaths(layout.nodes, [edge(1, 'a', 'a'), edge(2, 'a', 'a')])
  assert.notEqual(paths[0].path, paths[1].path)
  assert.ok(paths.every((path) => path.path.includes(' C ')))
  assert.deepEqual(graphPaths([], []), [])
  assert.deepEqual(layoutOf('ring', []).nodes, [])
})
