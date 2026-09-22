import assert from 'node:assert/strict'
import { test } from 'node:test'

import { graphPaths, layoutGraph } from '../graphLayout.ts'

const node = (iri, type, distance = 0) => ({
  id: iri.charCodeAt(0), graph_revision_id: 1, iri, type_iri: type, row_key: iri, attrs: {}, distance,
})
const edge = (id, subject, object_, kind = 'DIRECT') => ({
  id, graph_revision_id: 1, subject, object_, predicate: 'https://example.org/rel', kind,
})

test('overview groups by type, retains isolated nodes, and stays inside its viewbox', () => {
  const nodes = [node('a', 'Person'), node('b', 'Project'), node('c', 'Person'), node('alone', 'Other')]
  const layout = layoutGraph(nodes, false)
  assert.equal(layout.nodes.length, nodes.length)
  assert.deepEqual(layout.groups.map((group) => group.type), ['Person', 'Project', 'Other'])
  assert.ok(layout.nodes.every((item) => item.x >= 80 && item.x + 80 <= layout.width && item.y >= 26 && item.y + 26 <= layout.height))
})

test('neighborhood puts root in the center and second degree outside first degree', () => {
  const layout = layoutGraph([node('a', 'Person'), node('b', 'Person', 1), node('c', 'Project', 2)], true)
  const [root, first, second] = layout.nodes
  assert.equal(root.x, layout.width / 2)
  assert.equal(root.y, layout.height / 2)
  const radius = (item) => Math.hypot(item.x - root.x, item.y - root.y)
  assert.ok(radius(second) > radius(first))
})

test('parallel, reciprocal, and derived facts have separate curves and stable keys', () => {
  const layout = layoutGraph([node('a', 'Person'), node('b', 'Project')], false)
  const edges = [edge(1, 'a', 'b'), edge(2, 'a', 'b'), edge(3, 'b', 'a'), edge(1, 'a', 'b', 'DERIVED')]
  const paths = graphPaths(layout.nodes, edges)
  assert.equal(paths.length, 4)
  assert.equal(new Set(paths.map((path) => path.key)).size, 4)
  assert.equal(new Set(paths.map((path) => path.path)).size, 4)
  assert.ok(paths.every((path) => !/NaN|Infinity/.test(path.path)))
})

test('self loops remain separate and empty graphs are valid', () => {
  const layout = layoutGraph([node('a', 'Person')], false)
  const paths = graphPaths(layout.nodes, [edge(1, 'a', 'a'), edge(2, 'a', 'a')])
  assert.notEqual(paths[0].path, paths[1].path)
  assert.ok(paths.every((path) => path.path.includes(' C ')))
  assert.deepEqual(graphPaths([], []), [])
  assert.deepEqual(layoutGraph([], true).nodes, [])
})
