import assert from 'node:assert/strict'
import { test } from 'node:test'

import { resolveLayout } from '../components/layouts/index.ts'
import { fieldsFor, nodeTime, semanticValue, utcTime } from '../components/layouts/semanticView.ts'

function fixture(suffix) {
  const keys = ['measure', 'time', 'lat', 'lon']
  const fields = keys.map((key) => ({
    iri: `https://example.org/${suffix}/${key}`,
    name: `${key}_${suffix}`,
    kind: 'PROPERTY',
    type_iri: 'Unit',
    datatype: key === 'time' ? 'date' : 'decimal',
  }))
  fields.push({
    iri: `https://example.org/${suffix}/parent`,
    name: `parent_${suffix}`,
    kind: 'RELATION',
  })
  const config = {
    semantic_version: 1,
    hierarchy_relation_iri: fields[4].iri,
    measure_property_iri: fields[0].iri,
    time_property_iri: fields[1].iri,
    latitude_property_iri: fields[2].iri,
    longitude_property_iri: fields[3].iri,
  }
  const nodes = [0, 1, 2].map((index) => ({
    iri: `node${index}`,
    type_iri: 'Unit',
    row_key: `${index}`,
    distance: 0,
    attrs: Object.fromEntries(
      fields
        .slice(0, 4)
        .map((field, i) => [
          field.name,
          [index === 0 ? 9 : 1, `2024-01-0${index + 1}T00:00:00Z`, 10 + index, 20 + index][i],
        ]),
    ),
  }))
  const edges = [
    { id: 90, subject: 'node0', object_: 'node2', predicate: 'noise', kind: 'DIRECT' },
    { id: 1, subject: 'node1', object_: 'node0', predicate: fields[4].iri, kind: 'DIRECT' },
    { id: 2, subject: 'node2', object_: 'node1', predicate: fields[4].iri, kind: 'DIRECT' },
  ]
  return { graph: { nodes, edges }, context: { config, fields } }
}
const run = (id, fixture) => resolveLayout(id, false).compute(fixture.graph, fixture.context)
const geometry = (layout) => ({
  nodes: layout.nodes.map(({ iri, x, y }) => ({ iri, x, y })),
  groups: layout.groups.map(({ type, y }) => ({ type, y })),
  marks: layout.marks,
  edgePaths: layout.edgePaths,
})

test('same-named inherited properties require an exact IRI attribute', () => {
  const fields = ['Parent', 'Child'].map((owner) => ({
    iri: `https://example.org/${owner}/Score`,
    name: 'Score',
    kind: 'PROPERTY',
    type_iri: 'https://example.org/Child',
    type_name: 'Child',
    datatype: 'decimal',
  }))
  const node = { type_iri: 'https://example.org/instances#Child', attrs: { Score: 999 } }
  for (const field of fields)
    assert.equal(
      semanticValue(node, field.iri, fields, 'https://example.org/instances#'),
      undefined,
    )
  node.attrs[fields[0].iri] = 42
  assert.equal(semanticValue(node, fields[0].iri, fields, 'https://example.org/instances#'), 42)
  assert.equal(
    semanticValue(node, fields[1].iri, fields, 'https://example.org/instances#'),
    undefined,
  )
})

test('frozen semantic bindings resolve explicit extraction namespace for relations and properties', () => {
  const value = fixture('canonical')
  value.context.instanceNamespace = 'https://example.org/instances#'
  for (const field of value.context.fields) {
    if (field.kind === 'PROPERTY') field.type_name = 'Unit'
  }
  for (const node of value.graph.nodes) node.type_iri = `${value.context.instanceNamespace}Unit`
  for (const edge of value.graph.edges.slice(1))
    edge.predicate = `${value.context.instanceNamespace}parent_canonical`
  const hierarchy = run('org_tree', value)
  assert.equal(hierarchy.nodes.length, 3)
  assert.deepEqual(
    hierarchy.edges.map((edge) => edge.id),
    [1, 2],
  )
  assert.equal(run('pack', value).marks.filter((mark) => mark.iri).length, 3)
  assert.equal(nodeTime(value.graph.nodes[0], value.context), utcTime('2024-01-01'))
  assert.equal(
    semanticValue(
      value.graph.nodes[0],
      value.context.config.measure_property_iri,
      value.context.fields,
    ),
    undefined,
  )
  value.context.instanceNamespace = 'https://example.org/unrelated#'
  assert.deepEqual(run('org_tree', value).notices, [{ key: 'noRelation' }])
  for (const edge of value.graph.edges.slice(1)) edge.predicate = 'parent_canonical'
  assert.equal(run('org_tree', value).edges.length, 2)
})

for (const id of [
  'org_tree',
  'indent_tree',
  'equity_tree',
  'control_chain',
  'clan_tree',
  'impact',
  'sunburst',
  'treemap',
  'pack',
  'timeline',
  'gantt',
  'geo',
]) {
  test(`${id}: two differently named isomorphic graphs produce equal configured geometry`, () => {
    const a = run(id, fixture('original'))
    const b = run(id, fixture('renamed'))
    assert.deepEqual(geometry(a), geometry(b))
    assert.ok(a.nodes.length || a.marks.length)
    assert.doesNotMatch(JSON.stringify(geometry(a)), /NaN|Infinity/)
  })
}

test('only configured hierarchy relation controls parent edges and layout', () => {
  const value = fixture('a')
  const result = run('org_tree', value)
  assert.deepEqual(
    result.edges.map((edge) => edge.id),
    [1, 2],
  )
  assert.equal(result.edgePaths[90], undefined)
  const byIri = new Map(result.nodes.map((node) => [node.iri, node]))
  assert.ok(byIri.get('node0').y < byIri.get('node1').y)
  assert.ok(byIri.get('node1').y < byIri.get('node2').y)
})

test('configured hierarchy rejects cyclic and ambiguous parent relations explicitly', () => {
  const value = fixture('a')
  value.graph.edges.push({ ...value.graph.edges[1], id: 3, subject: 'node0', object_: 'node2' })
  assert.deepEqual(run('org_tree', value).notices, [{ key: 'invalidHierarchy' }])
  assert.deepEqual(run('org_tree', value).nodes, [])
  value.graph.edges.pop()
  value.graph.edges.push({ ...value.graph.edges[1], id: 3, subject: 'node2', object_: 'node0' })
  assert.deepEqual(run('org_tree', value).notices, [{ key: 'invalidHierarchy' }])
})

test('numeric packing actually uses the selected positive measure, not instance counts', () => {
  const value = fixture('a')
  const result = run('pack', value)
  const radius = result.marks.filter((mark) => mark.iri).map((mark) => mark.r)
  assert.ok(Math.abs(radius[0] / radius[1] - 3) < 0.0001)
  value.graph.nodes[0].attrs.measure_a = '9'
  value.graph.nodes[1].attrs.measure_a = -1
  value.graph.nodes[2].attrs.measure_a = 0
  const invalid = run('pack', value)
  assert.deepEqual(invalid.nodes, [])
  assert.equal(invalid.marks, undefined)
  assert.deepEqual(invalid.notices[0], { key: 'invalidMeasure', count: 3 })
})

test('ISO dates are UTC; timestamps require an explicit zone and preserve sub-day precision', () => {
  assert.equal(utcTime('1970-01-01'), 0)
  assert.equal(utcTime('2024-01-01T00:00Z'), utcTime('2024-01-01'))
  assert.equal(utcTime('2024-01-01T00:00:00.123456Z'), utcTime('2024-01-01T00:00:00.123Z'))
  assert.equal(utcTime('2024-01-01T08:00:00+08:00'), utcTime('2024-01-01T00:00:00Z'))
  for (const invalid of [
    '2024-02-30',
    '2023-02-29',
    '2024-13-01',
    '2024-01-01junk',
    '2024-01-01T00:00:00',
    '2024-01-01T24:00:00Z',
    '2024-01-01T00:60:00Z',
    '2024-01-01T00:00:00+99:00',
    '',
    1704067200000,
  ]) {
    assert.equal(utcTime(invalid), null, String(invalid))
  }
  assert.notEqual(utcTime('2024-01-01T00:00:00.001Z'), utcTime('2024-01-01T00:00:00.002Z'))
})

for (const id of ['timeline', 'gantt']) {
  test(`${id} excludes invalid selected dates even if another date looks valid`, () => {
    const value = fixture('a')
    value.graph.nodes[0].attrs = { time_a: '2024-02-30', distraction: '2024-01-01' }
    value.graph.nodes[1].attrs = { time_a: '2024-01-01T00:00:00', distraction: '2024-01-02' }
    const result = run(id, value)
    assert.deepEqual(
      result.nodes.map((node) => node.iri),
      ['node2'],
    )
    assert.deepEqual(result.notices[0], { key: 'invalidTime', count: 2 })
  })
}

test('WGS84 uses explicit numeric fields with fixed world projection and rejects bad coordinates', () => {
  const value = fixture('a')
  value.graph.nodes[0].attrs.lat_a = 0
  value.graph.nodes[0].attrs.lon_a = 0
  value.graph.nodes[1].attrs.lat_a = 91
  value.graph.nodes[2].attrs.lon_a = '120'
  const result = run('geo', value)
  assert.deepEqual(
    result.nodes.map(({ iri, x, y }) => ({ iri, x, y })),
    [{ iri: 'node0', x: 620, y: 340 }],
  )
  assert.deepEqual(result.notices[0], { key: 'invalidCoordinates', count: 2 })
  for (const invalid of [null, false, NaN, Infinity, '', 181, -181]) {
    value.graph.nodes[0].attrs.lon_a = invalid
    assert.equal(run('geo', value).nodes.length, 0)
  }
})

test('missing and unsupported configuration has explicit notices; only legacy retains heuristics', () => {
  const value = fixture('a')
  value.context.config = {}
  assert.deepEqual(run('timeline', value).notices, [{ key: 'missing' }])
  assert.equal(run('timeline', value).nodes.length, 0)
  value.context.legacy = true
  assert.equal(run('timeline', value).nodes.length, 3)
  assert.deepEqual(run('timeline', value).notices, [{ key: 'legacy' }])
  value.context.stale = true
  assert.equal(run('timeline', value).nodes.length, 0)
  assert.deepEqual(run('timeline', value).notices, [{ key: 'stale' }])
  const unknown = run('unknown-layout', fixture('a'))
  assert.deepEqual(unknown.notices, [{ key: 'unsupported' }])
})

test('snapshot IRI/name bindings never guess property suffixes or accept wrong types', () => {
  const value = fixture('a')
  const node = value.graph.nodes[0]
  delete node.attrs.time_a
  node.attrs.time = '2024-01-01'
  assert.equal(nodeTime(node, value.context), null)
  node.attrs[value.context.config.time_property_iri] = '2024-01-02'
  assert.equal(nodeTime(node, value.context), utcTime('2024-01-02'))
  node.type_iri = 'Other'
  assert.equal(
    semanticValue(node, value.context.config.time_property_iri, value.context.fields),
    undefined,
  )
  assert.equal(fieldsFor('measure_property_iri', value.context.fields).length, 3)
})
