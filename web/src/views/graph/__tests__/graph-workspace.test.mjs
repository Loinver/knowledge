import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from '../../__tests__/view-harness.mjs'

const node = (iri) => ({
  id: iri.charCodeAt(0),
  iri,
  type_iri: 'Type',
  row_key: iri,
  attrs: { name: iri },
  distance: 0,
})
const edge = (id, subject, object_) => ({
  id,
  subject,
  object_,
  predicate: 'knows',
  kind: 'DIRECT',
  graph_revision_id: 1,
})
const graph = (nodes = ['a'], edges = [], revision = 1) => ({
  graph_revision_id: revision,
  run_id: 1,
  ontology_id: null,
  ontology_revision: null,
  entity_total: 4,
  quarantine_count: 0,
  truncated: false,
  type_counts: [],
  nodes: nodes.map(node),
  edges,
})
async function setup(overrides = {}) {
  return mount(
    'views/graph/GraphBrowse.vue',
    {
      '@/api/graph': {
        graphApi: {
          view: async () => graph(),
          entities: async () => ({ items: [] }),
          recommendations: async () => ({ recommendations: [] }),
          ...overrides,
        },
        viewTemplateApi: {},
      },
    },
    'data,loading,error,reload,selectedIri,selectedEdge,selectNode,selectEdge,expandSelected,collapseSelected,branches,excludedTypes,showEvidence,evidence,pathFrom,pathTo,pathResult,findPath',
    '/?graph=1',
  )
}

test('selection is local and shared branch nodes survive collapse', async () => {
  let calls = 0
  const ctx = await setup({
    view: async (params) => {
      calls++
      if (params.center === 'a')
        return graph(['a', 'b', 'c'], [edge(1, 'a', 'b'), edge(2, 'a', 'c')])
      if (params.center === 'b')
        return graph(['b', 'c', 'd'], [edge(3, 'b', 'c'), edge(4, 'b', 'd')])
      return graph()
    },
  })
  try {
    ctx.vm.selectNode('a')
    assert.equal(calls, 1)
    assert.equal(ctx.router.currentRoute.value.query.center, undefined)
    await ctx.vm.expandSelected()
    ctx.vm.selectNode('b')
    await ctx.vm.expandSelected()
    ctx.vm.selectNode('a')
    ctx.vm.collapseSelected()
    assert.deepEqual(
      ctx.vm.data.nodes.map((n) => n.iri),
      ['a', 'b', 'c', 'd'],
    )
    assert.deepEqual(
      ctx.vm.data.edges.map((e) => e.id),
      [3, 4],
    )
  } finally {
    ctx.stop()
  }
})

test('filter invalidates pending expansion; refresh failure retains the visible graph', async () => {
  const pending = deferred()
  let branchSignal,
    fail = false
  const ctx = await setup({
    view: async (params, signal) => {
      if (params.center) {
        branchSignal = signal
        return pending.promise
      }
      if (fail) throw { code: 'KG.INTERNAL_ERROR' }
      return graph()
    },
  })
  try {
    ctx.vm.selectNode('a')
    const expansion = ctx.vm.expandSelected()
    ctx.vm.excludedTypes = ['Hidden']
    await settle()
    assert.equal(branchSignal.aborted, true)
    pending.resolve(graph(['a', 'b']))
    await expansion
    assert.equal(ctx.vm.branches.size, 0)
    fail = true
    ctx.vm.reload()
    await settle()
    assert.equal(ctx.vm.data.nodes.length, 1)
    assert.notEqual(ctx.vm.error, '')
  } finally {
    ctx.stop()
  }
})

test('late evidence and path responses cannot replace a newer selection or endpoint', async () => {
  const oldEvidence = deferred(),
    oldPath = deferred()
  let evidenceSignal, pathSignal
  const ctx = await setup({
    view: async () => graph(['a', 'b']),
    entityEvidence: (iri, _revision, signal) => {
      if (iri === 'a') {
        evidenceSignal = signal
        return oldEvidence.promise
      }
      return Promise.resolve({
        graph_revision_id: 1,
        evidences: [],
        total_count: 0,
        quarantined_count: 0,
        entity: { iri: 'b' },
      })
    },
    path: (_id, _params, signal) => {
      pathSignal = signal
      return oldPath.promise
    },
  })
  try {
    ctx.vm.selectNode('a')
    ctx.vm.showEvidence = true
    await settle()
    ctx.vm.selectNode('b')
    ctx.vm.showEvidence = true
    await settle()
    oldEvidence.resolve({ entity: { iri: 'a' }, total_count: 99 })
    await settle()
    assert.equal(evidenceSignal.aborted, true)
    assert.equal(ctx.vm.evidence.data.value.entity.iri, 'b')
    ctx.vm.pathFrom = 'a'
    ctx.vm.pathTo = 'b'
    const request = ctx.vm.findPath()
    ctx.vm.pathTo = 'c'
    await settle()
    oldPath.resolve({ found: true, nodes: ['a', 'b'] })
    await request
    assert.equal(pathSignal.aborted, true)
    assert.equal(ctx.vm.pathResult, null)
  } finally {
    ctx.stop()
  }
})

test('clearing type filters recomputes retained branches and restores hidden selection', async () => {
  const requests = []
  const ctx = await setup({
    view: async (params) => {
      requests.push({ ...params })
      if (params.excluded_types.includes('Type')) return graph([])
      return params.center === 'a' ? graph(['a', 'b'], [edge(1, 'a', 'b')]) : graph()
    },
  })
  try {
    ctx.vm.selectNode('a')
    await ctx.vm.expandSelected()
    ctx.vm.selectNode('b')
    ctx.vm.excludedTypes = ['Type']
    await settle()
    assert.deepEqual(ctx.vm.data.nodes, [])
    assert.equal(
      ctx.vm.selectedIri,
      'b',
      'temporary invisibility does not discard selection intent',
    )
    ctx.vm.excludedTypes = []
    await settle()
    assert.deepEqual(
      ctx.vm.data.nodes.map((item) => item.iri),
      ['a', 'b'],
    )
    assert.equal(ctx.vm.selectedIri, 'b')
    assert.equal(ctx.vm.branches.size, 1)
    assert.ok(
      requests.some((request) => request.center === 'a' && request.excluded_types.includes('Type')),
      'branch traversal uses the same exclusions as the base graph',
    )
  } finally {
    ctx.stop()
  }
})

test('refresh cancels pending expansion before taking ownership of the branch snapshot', async () => {
  const expansionResult = deferred()
  const refreshResult = deferred()
  let reads = 0
  let expansionSignal
  const ctx = await setup({
    view: async (params, signal) => {
      if (params.center) {
        expansionSignal = signal
        return expansionResult.promise
      }
      return reads++ === 0 ? graph() : refreshResult.promise
    },
  })
  try {
    ctx.vm.selectNode('a')
    const expanding = ctx.vm.expandSelected()
    ctx.vm.reload()
    await settle()
    assert.equal(expansionSignal.aborted, true)
    expansionResult.resolve(graph(['a', 'b'], [edge(1, 'a', 'b')]))
    await expanding
    assert.deepEqual(
      ctx.vm.data.nodes.map((item) => item.iri),
      ['a'],
    )
    assert.equal(ctx.vm.selectedIri, 'a')
    refreshResult.resolve(graph())
    await settle()
    assert.equal(ctx.vm.branches.size, 0)
    assert.equal(ctx.vm.selectedIri, 'a')
    await ctx.vm.expandSelected()
    assert.deepEqual(
      ctx.vm.data.nodes.map((item) => item.iri),
      ['a', 'b'],
    )
  } finally {
    ctx.stop()
  }
})

test('collapse is guarded while refresh owns an existing expanded branch', async () => {
  const refreshResult = deferred()
  let reads = 0
  const ctx = await setup({
    view: async (params) => {
      if (params.center) return graph(['a', 'b'], [edge(1, 'a', 'b')])
      return reads++ === 0 ? graph() : refreshResult.promise
    },
  })
  try {
    ctx.vm.selectNode('a')
    await ctx.vm.expandSelected()
    ctx.vm.reload()
    await settle()
    ctx.vm.collapseSelected()
    assert.equal(ctx.vm.branches.size, 1)
    refreshResult.resolve(graph())
    await settle()
    ctx.vm.collapseSelected()
    assert.equal(ctx.vm.branches.size, 0)
    assert.deepEqual(
      ctx.vm.data.nodes.map((item) => item.iri),
      ['a'],
    )
  } finally {
    ctx.stop()
  }
})
