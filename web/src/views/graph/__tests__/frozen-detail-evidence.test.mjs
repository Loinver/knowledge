import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from '../../__tests__/view-harness.mjs'

const predicate = 'https://example.org/instances/WorksIn'
const fact = { id: 7, subject: 'A', predicate, object_: 'B' }
const evidenceItem = {
  id: 8,
  subject: 'A',
  predicate,
  object: 'B',
  source_id: 1,
  table_name: 'employees',
  row_key: 'A',
  columns: ['department_id'],
  run_id: 1,
}
const graph = (revision) => ({
  graph_revision_id: revision,
  ontology_id: 10,
  ontology_revision: revision + 10,
  instance_namespace: 'https://example.org/instances/',
  edges: [], // Labels must not depend on the bounded metadata read's edge subset.
})
const catalog = (revision, label = `Frozen ${revision}`) => ({
  ontology_id: 10,
  ontology_revision: revision,
  stale: true,
  fields: [
    {
      kind: 'RELATION',
      name: 'WorksIn',
      iri: 'https://example.org/model/WorksIn',
      label_i18n: { 'en-US': label, 'zh-CN': '任职于' },
    },
  ],
})
const trace = (revision) => ({
  graph_revision_id: revision,
  evidences: [evidenceItem],
  total_count: 1,
  quarantined_count: 0,
})

async function setup(t, page = 'GraphEntityDetail', api = {}, fields, start) {
  const viewReads = []
  const fieldReads = []
  const ctx = await mount(
    `views/graph/${page}.vue`,
    {
      '@/api/graph': {
        graphApi: {
          view: async (params) => {
            viewReads.push(params)
            return graph(params.graph_revision_id)
          },
          detail: async (iri, revision = 1) => ({
            entity: { iri, graph_revision_id: revision, attrs: {} },
            out_edges: [fact],
            in_edges: [{ ...fact, predicate: 'WorksIn' }],
            derived_edges: [{ ...fact, predicate: 'https://other.org/WorksIn' }],
          }),
          entityEvidence: async (_iri, revision = 1) => trace(revision),
          entityFusion: async () => null,
          factEvidence: async (_fact, revision = 1) => trace(revision),
          ...api,
        },
        viewTemplateApi: {
          fields: async (ontology, revision, signal) => {
            fieldReads.push({ ontology, revision, signal })
            return fields ? fields(ontology, revision, signal) : catalog(revision)
          },
        },
      },
      '@/api/mappings': {
        mappingsApi: { revision: async () => null, get: async () => null },
      },
    },
    page === 'GraphEntityDetail'
      ? 'data,evidence,frozenLabels,openChain,kbReturn'
      : 'data,mode,sourceId,reverseTable,reverseRowKey,reverseResult,runReverse,resolvedGraph,listContext,frozenLabels,showChain,chainItem,frozenChain,kbReturn',
    start ?? (page === 'GraphEntityDetail' ? '/entities/A?graph=1' : '/?iri=A'),
  )
  t.after(ctx.stop)
  return { ...ctx, viewReads, fieldReads }
}

const kbSearch = '/knowledge-bases/12/search?q=graph%20labels&source=7'

for (const page of ['GraphEntityDetail', 'GraphEvidence']) {
  test(`${page} only accepts local KB search return paths and preserves the encoded query`, async (t) => {
    const ctx = await setup(t, page)
    const path = page === 'GraphEntityDetail' ? '/entities/A' : '/'
    for (const target of [
      undefined,
      'https://example.org/knowledge-bases/12/search',
      '//example.org/knowledge-bases/12/search',
      '/knowledge-bases/0/search',
      '/knowledge-bases/01/search',
      '/knowledge-bases/-1/search',
      '/knowledge-bases/12/search/other',
      '/knowledge-bases/12/searching',
      [kbSearch, kbSearch],
      '/knowledge-bases/12/search',
      kbSearch,
    ]) {
      await ctx.router.push({ path, query: { graph: '1', iri: 'A', kbReturn: target } })
      await settle()
      const expected =
        target === kbSearch || target === '/knowledge-bases/12/search' ? target : undefined
      assert.equal(ctx.vm.kbReturn, expected)
      if (page === 'GraphEvidence') assert.equal(ctx.vm.listContext.kbReturn, expected)
    }
  })
}

test('detail resolves all fact predicates from its frozen pin and keeps evidence navigation raw', async (t) => {
  const ctx = await setup(
    t,
    'GraphEntityDetail',
    {},
    undefined,
    `/entities/A?graph=1&iri=A&kbReturn=${encodeURIComponent(kbSearch)}`,
  )
  assert.deepEqual(ctx.viewReads, [{ graph_revision_id: 1, node_limit: 1, edge_limit: 1 }])
  assert.equal(ctx.fieldReads[0].ontology, 10)
  assert.equal(ctx.fieldReads[0].revision, 11)
  assert.equal(ctx.vm.frozenLabels.name(predicate), 'Frozen 11')
  assert.equal(ctx.vm.frozenLabels.name('WorksIn'), 'Frozen 11')
  assert.equal(
    ctx.vm.frozenLabels.name('https://other.org/WorksIn'),
    'https://other.org/WorksIn · Not translated',
  )
  assert.equal(ctx.vm.evidence.data.value.evidences[0].predicate, predicate)
  ctx.router.addRoute({
    path: '/evidence',
    name: 'graph-evidence',
    component: { render: () => null },
  })
  ctx.vm.openChain(ctx.vm.evidence.data.value.evidences[0])
  await settle()
  assert.equal(ctx.router.currentRoute.value.query.predicate, predicate)
  assert.equal(ctx.router.currentRoute.value.query.graph, '1')
  assert.equal(ctx.router.currentRoute.value.query.iri, undefined)
  assert.equal(ctx.router.currentRoute.value.query.kbReturn, kbSearch)
})

test('detail A-B-A navigation ignores late catalogs even when the old A has the same pin', async (t) => {
  const first = deferred()
  const second = deferred()
  let calls = 0
  const ctx = await setup(t, 'GraphEntityDetail', {}, (_ontology, revision) => {
    calls++
    return calls === 1
      ? first.promise
      : calls === 2
        ? second.promise
        : catalog(revision, 'Newest A')
  })
  assert.match(ctx.vm.frozenLabels.name(predicate), /Not translated/)
  await ctx.router.push('/entities/B?graph=2')
  await settle()
  await ctx.router.push('/entities/A?graph=1')
  await settle()
  first.resolve(catalog(11, 'Late A'))
  second.resolve(catalog(12, 'Late B'))
  await settle()
  assert.ok(ctx.fieldReads.slice(0, 2).every((read) => read.signal.aborted))
  assert.equal(ctx.vm.frozenLabels.name(predicate), 'Newest A')
  assert.equal(ctx.vm.evidence.data.value.evidences[0].predicate, predicate)
})

test('late graph metadata never starts an obsolete ontology catalog request', async (t) => {
  const old = deferred()
  let oldSignal
  const ctx = await setup(t, 'GraphEntityDetail', {
    view: (params, signal) => {
      if (params.graph_revision_id !== 1) return Promise.resolve(graph(params.graph_revision_id))
      oldSignal = signal
      return old.promise
    },
  })
  await ctx.router.push('/entities/B?graph=2')
  await settle()
  old.resolve(graph(1))
  await settle()
  assert.equal(oldSignal.aborted, true)
  assert.deepEqual(
    ctx.fieldReads.map((read) => read.revision),
    [12],
  )
  assert.equal(ctx.vm.frozenLabels.name(predicate), 'Frozen 12')
})

test('catalog retry clears old labels on failure and restores only the pinned version', async (t) => {
  let fail = false
  const ctx = await setup(t, 'GraphEntityDetail', {}, (_ontology, revision) => {
    if (fail) throw { code: 'KG.INTERNAL_ERROR' }
    return catalog(revision)
  })
  fail = true
  ctx.vm.frozenLabels.reload()
  await settle()
  assert.equal(ctx.vm.frozenLabels.name(predicate), `${predicate} · Not translated`)
  assert.equal(ctx.vm.evidence.data.value.evidences[0].predicate, predicate)
  assert.match(ctx.vm.frozenLabels.error.value, /KG.INTERNAL_ERROR/)
  fail = false
  ctx.vm.frozenLabels.reload()
  await settle()
  assert.equal(ctx.vm.frozenLabels.name(predicate), 'Frozen 11')
  assert.equal(ctx.vm.frozenLabels.error.value, '')
  assert.ok(ctx.fieldReads.every((read) => read.revision === 11))
})

for (const invalid of ['missing pin', 'wrong graph', 'wrong ontology', 'wrong version']) {
  test(`invalid ${invalid} never uses current ontology labels`, async (t) => {
    const ctx = await setup(
      t,
      'GraphEntityDetail',
      {
        view: async () => ({
          ...graph(invalid === 'wrong graph' ? 2 : 1),
          ...(invalid === 'missing pin' ? { ontology_revision: null } : {}),
        }),
      },
      (_ontology, revision) => ({
        ...catalog(invalid === 'wrong version' ? revision + 1 : revision),
        ontology_id: invalid === 'wrong ontology' ? 20 : 10,
      }),
    )
    assert.equal(ctx.vm.frozenLabels.name(predicate), `${predicate} · Not translated`)
    assert.notEqual(ctx.vm.frozenLabels.error.value, '')
    if (invalid === 'missing pin' || invalid === 'wrong graph')
      assert.equal(ctx.fieldReads.length, 0)
  })
}

test('unversioned entity and fact evidence use returned graph pins and keep chain facts raw', async (t) => {
  const ctx = await setup(t, 'GraphEvidence', {
    entityEvidence: async () => trace(3),
    factEvidence: async () => trace(4),
  })
  assert.equal(ctx.vm.resolvedGraph, 3)
  assert.equal(ctx.vm.listContext.graph, 3)
  assert.equal(ctx.vm.frozenLabels.name(predicate), 'Frozen 13')
  ctx.vm.showChain(ctx.vm.data.evidences[0])
  assert.equal(ctx.vm.chainItem.predicate, predicate)
  assert.match(ctx.vm.frozenChain[0].value, /Frozen 13/)
  await ctx.router.push('/?subject=A&predicate=WorksIn&object=B')
  await settle()
  assert.equal(ctx.vm.resolvedGraph, 4)
  assert.equal(ctx.vm.chainItem, null)
  assert.equal(ctx.vm.frozenLabels.name(predicate), 'Frozen 14')
  assert.equal(ctx.vm.data.evidences[0].predicate, predicate)
  assert.deepEqual(
    ctx.viewReads.map((read) => read.graph_revision_id),
    [3, 4],
  )
})

test('reverse trace uses the returned graph and invalidates late source-row results', async (t) => {
  const late = deferred()
  let calls = 0
  let oldSignal
  const ctx = await setup(
    t,
    'GraphEvidence',
    {
      reverseTrace: async (params, revision, signal) => {
        assert.equal(revision, undefined)
        calls++
        if (calls === 1) {
          oldSignal = signal
          return late.promise
        }
        return { graph_revision_id: 9, facts: [evidenceItem], entities: [params.row_key] }
      },
    },
    undefined,
    `/?kbReturn=${encodeURIComponent(kbSearch)}`,
  )
  assert.deepEqual(ctx.viewReads, [])
  ctx.vm.mode = 'reverse'
  ctx.vm.sourceId = 1
  ctx.vm.reverseTable = 'employees'
  ctx.vm.reverseRowKey = 'A'
  const first = ctx.vm.runReverse()
  ctx.vm.reverseRowKey = 'B'
  await ctx.vm.runReverse()
  late.resolve({ graph_revision_id: 8, facts: [], entities: ['A'] })
  await first
  await settle()
  assert.equal(oldSignal.aborted, true)
  assert.equal(ctx.vm.reverseResult.graph_revision_id, 9)
  assert.equal(ctx.vm.listContext.graph, 9)
  assert.equal(ctx.vm.listContext.kbReturn, kbSearch)
  assert.equal(ctx.vm.frozenLabels.name(predicate), 'Frozen 19')
  assert.deepEqual(
    ctx.viewReads.map((read) => read.graph_revision_id),
    [9],
  )
  ctx.vm.reverseRowKey = 'C'
  await settle()
  assert.equal(ctx.vm.reverseResult, null)
  assert.deepEqual({ ...ctx.vm.frozenLabels.labels.value }, {})
})
