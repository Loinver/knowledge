import assert from 'node:assert/strict'
import { test } from 'node:test'

import { relationLabels } from '../graphPresentation.ts'

const field = (iri, name, labels = { 'zh-CN': '任职于', 'en-US': 'Works in' }) => ({
  iri,
  name,
  kind: 'RELATION',
  label_i18n: labels,
})
const graph = (predicates) => ({
  ontology_id: 1,
  ontology_revision: 2,
  instance_namespace: 'https://example.org/instances/',
  edges: predicates.map((predicate) => ({ predicate })),
})
const catalog = (fields, overrides = {}) => ({
  ontology_id: 1,
  ontology_revision: 2,
  stale: false,
  fields,
  ...overrides,
})
const resource = 'https://example.org/model/WorksIn'
const instance = 'https://example.org/instances/WorksIn'

test('frozen labels match exact IRIs, bare extraction names and the explicit namespace', () => {
  const fields = catalog([field(resource, 'WorksIn')], { stale: true })
  assert.deepEqual(
    {
      ...relationLabels(
        graph([resource, instance, 'WorksIn', 'https://other.org/WorksIn']),
        fields,
        'zh-CN',
        '未翻译',
      ),
    },
    {
      [resource]: '任职于',
      [instance]: '任职于',
      WorksIn: '任职于',
    },
  )
  assert.equal(
    relationLabels(graph([instance]), fields, 'en-US', 'Not translated')[instance],
    'Works in',
  )
})

test('ambiguous namespace aliases never override an exact relation or guess a translation', () => {
  const fields = catalog([
    field(resource, 'WorksIn'),
    field('https://other.org/WorksIn', 'WorksIn', { 'zh-CN': '参与' }),
  ])
  assert.deepEqual(
    { ...relationLabels(graph([resource, instance, 'WorksIn']), fields, 'zh-CN', '未翻译') },
    {
      [resource]: '任职于',
    },
  )
})

test('exact IRIs take priority over aliases even when their translation is absent', () => {
  const fields = catalog([field(resource, 'WorksIn'), field(instance, 'DifferentRelation', {})])
  assert.equal(
    relationLabels(graph([instance]), fields, 'zh-CN', '未翻译')[instance],
    'DifferentRelation · 未翻译',
  )
})

test('namespace aliases are scoped to the active result set without guessing IRI suffixes', () => {
  const fields = catalog([field(resource, 'WorksIn')])
  const current = {
    ...graph([instance, 'WorksIn', 'https://new.org/WorksIn']),
    instance_namespace: 'https://new.org/',
  }
  assert.deepEqual(
    { ...relationLabels(current, fields, 'zh-CN', '未翻译') },
    {
      WorksIn: '任职于',
      'https://new.org/WorksIn': '任职于',
    },
  )
  assert.equal(relationLabels(graph(['toString']), fields, 'zh-CN', '未翻译').toString, undefined)
})

test('missing translations are explicit, and mismatched versions cannot label another graph', () => {
  const fields = [field(resource, 'WorksIn', { 'zh-CN': '任职于', 'en-US': '  ' })]
  assert.equal(
    relationLabels(graph([instance]), catalog(fields), 'en-US', 'Not translated')[instance],
    'WorksIn · Not translated',
  )
  for (const overrides of [{ ontology_id: 2 }, { ontology_revision: 3 }])
    assert.deepEqual(
      { ...relationLabels(graph([instance]), catalog(fields, overrides), 'zh-CN', '未翻译') },
      {},
    )
  assert.deepEqual({ ...relationLabels(graph([instance]), null, 'zh-CN', '未翻译') }, {})
})

test('unloaded, failed and mismatched catalogs never inherit labels from Object.prototype', () => {
  const current = graph(['toString', 'constructor', '__proto__'])
  for (const fields of [null, catalog([], { ontology_revision: 3 }), catalog([])]) {
    const labels = relationLabels(current, fields, 'zh-CN', '未翻译')
    for (const edge of current.edges) assert.equal(labels[edge.predicate], undefined)
  }
  assert.equal(relationLabels(null, null, 'zh-CN', '未翻译').toString, undefined)
})
