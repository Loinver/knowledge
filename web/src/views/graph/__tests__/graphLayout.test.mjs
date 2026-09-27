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

test('cycle view isolates cycle members on the inner ring', () => {
  const nodes = [node('a', 'Ent'), node('b', 'Ent'), node('c', 'Ent'), node('solo', 'Ent')]
  const edges = [edge(1, 'a', 'b'), edge(2, 'b', 'a'), edge(3, 'solo', 'c')]
  const layout = layoutOf('cycle_view', nodes, edges)
  const byIri = new Map(layout.nodes.map((item) => [item.iri, item]))
  // 环上两实体靠近中心 (480, 330)；网格块整体右移
  const ringDist = Math.hypot(byIri.get('a').x - 480, byIri.get('a').y - 330)
  assert.ok(ringDist < 220)
  assert.ok(byIri.get('solo').x > 800, '环外节点应落入右侧网格块')
})

test('community groups connected components into separated blocks', () => {
  const nodes = [node('a', 'Person'), node('b', 'Person'), node('far', 'Person')]
  const edges = [edge(1, 'a', 'b')]
  const layout = layoutOf('community', nodes, edges)
  const byIri = new Map(layout.nodes.map((item) => [item.iri, item]))
  const pairGap = Math.hypot(
    byIri.get('a').x - byIri.get('b').x,
    byIri.get('a').y - byIri.get('b').y,
  )
  const crossGap = Math.abs(byIri.get('far').x - byIri.get('a').x)
  assert.ok(crossGap > pairGap, '不同社区必须比社区内节点更远')
})

test('impact tree reverses dependency direction', () => {
  const nodes = [node('root', 'App'), node('lib', 'Module')]
  const edges = [edge(1, 'lib', 'root')]
  const layout = layoutOf('impact', nodes, edges)
  const byIri = new Map(layout.nodes.map((item) => [item.iri, item]))
  // 依赖者 lib 排在 root 之下（root 是被依赖的根）
  assert.ok(byIri.get('lib').y > byIri.get('root').y)
})

test('geo groups nodes by region attribute and falls back to grid', () => {
  const nodes = [
    node('sh', 'Ent', 0, { region: '上海' }),
    node('sh2', 'Ent', 0, { region: '上海' }),
    node('bj', 'Ent', 0, { region: '北京' }),
    node('none', 'Ent'),
  ]
  const layout = layoutOf('geo', nodes, [])
  const byIri = new Map(layout.nodes.map((item) => [item.iri, item]))
  assert.ok(Math.abs(byIri.get('sh').y - byIri.get('sh2').y) < 1, '同城节点同一行')
  assert.ok(
    Math.abs(byIri.get('sh').y - byIri.get('bj').y) > 1 || byIri.get('bj').x !== byIri.get('sh').x,
  )
  // 无区域属性节点仍在布局中（退化块）
  assert.ok(byIri.get('none'))
})

test('sankey and chord aggregate to type level with counts', () => {
  const nodes = [node('a', 'Person'), node('b', 'Person'), node('c', 'Project')]
  const edges = [edge(1, 'a', 'c'), edge(2, 'b', 'c')]
  const sankeyLayout = layoutOf('sankey', nodes, edges)
  assert.equal(sankeyLayout.nodes.length, 2)
  const chordLayout = layoutOf('chord', nodes, edges)
  assert.equal(chordLayout.nodes.length, 2)
  const person = chordLayout.nodes.find((item) => item.iri === 'Person')
  assert.equal(person.attrs.__typeCount__, 2)
})

test('sunburst encodes types inner and instances outer with valid angles', () => {
  const nodes = [node('a', 'Person'), node('b', 'Person'), node('c', 'Project')]
  const layout = layoutOf('sunburst', nodes, [])
  const marks = layout.marks
  assert.equal(marks.filter((m) => m.id.startsWith('type:')).length, 2)
  const instances = marks.filter((m) => m.id.startsWith('inst:'))
  assert.equal(instances.length, 3)
  assert.ok(
    instances.every((m) => m.iri),
    '实例扇区必须可下钻',
  )
  assert.ok(
    marks.every((m) => !/NaN/.test(m.path)),
    '扇区路径不能有 NaN',
  )
  // 同类型同色
  const pa = marks.find((m) => m.id === 'inst:a')
  const pb = marks.find((m) => m.id === 'inst:b')
  assert.equal(pa.fill, pb.fill)
})

test('treemap places instance rects inside canvas without NaN', () => {
  const nodes = [
    node('a', 'Person'),
    node('b', 'Person'),
    node('c', 'Project'),
    node('d', 'Project'),
    node('e', 'Project'),
  ]
  const layout = layoutOf('treemap', nodes, [])
  const rects = layout.marks.filter((m) => m.kind === 'rect' && m.id.startsWith('inst:'))
  assert.equal(rects.length, 5)
  assert.equal(layout.marks.filter((m) => m.id.startsWith('type:')).length, 2)
  assert.ok(
    rects.every((m) => m.w > 0 && m.h > 0 && m.x - m.w / 2 >= 0 && m.x + m.w / 2 <= layout.width),
  )
})

test('pack nests instance circles inside type circles', () => {
  const nodes = [node('a', 'Person'), node('b', 'Person'), node('c', 'Project')]
  const layout = layoutOf('pack', nodes, [])
  const circles = layout.marks.filter((m) => m.kind === 'circle')
  assert.equal(circles.length, 5)
  const typeCircles = circles.filter((m) => m.id.startsWith('type:'))
  assert.ok(typeCircles.every((m) => m.r > 0))
  const instances = circles.filter((m) => m.id.startsWith('inst:'))
  assert.ok(instances.every((m) => m.r > 0))
})
