import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from '../../../../testing/view-harness.mjs'

const report = (id, extra = {}) => ({
  report_id: id,
  scope: 'INSTANCE',
  target_id: 1,
  target_revision: 1,
  summary: { pass: 1, violation: 1, na: 1, not_run: 1 },
  ...extra,
})
const results = ['PASS', 'VIOLATION', 'NA', 'NOT_RUN'].map((state, index) => ({
  check_code: `A0${index + 1}`,
  state,
  focus_node: `https://example.org/${index}`,
  rule_id: `rule-${index}`,
  detail: { evidence_ids: [index + 1] },
}))
async function setup(t, overrides = {}, role = 'EDITOR', start = '/') {
  const writes = []
  const ctx = await mount(
    'views/ontology/validation/ValidationReportsPage.vue',
    {
      '@/api/ontology': {
        ontologyApi: { list: async () => [{ id: 7, name: 'Ontology7', current_revision: 4 }] },
      },
      '@/api/validation': {
        validationApi: {
          revisions: async () => [{ id: 1, is_current: true }],
          validateGraph: async (id) => {
            writes.push(['graph', id])
            return report(id)
          },
          validateOntology: async (...args) => {
            writes.push(['ontology', ...args])
            return report(7)
          },
          getReport: async (id) => report(id),
          getResults: async () => results,
          ...overrides,
        },
      },
    },
    'scope,selectedGraphId,selectedOntologyId,ontologyTarget,ontologyRevision,runValidation,reportId,report,results,filteredResults,stateFilter,readouts,running,loadResults,loadingResults,resultsError,selectedResult',
    start,
    undefined,
    role,
  )
  t.after(ctx.stop)
  return { ...ctx, writes }
}

test('working and selected frozen ontology validation send explicit target and revision', async (t) => {
  const ctx = await setup(t)
  ctx.vm.scope = 'ONTOLOGY'
  await settle()
  ctx.vm.selectedOntologyId = 7
  await ctx.vm.runValidation()
  ctx.vm.ontologyTarget = 'PUBLISHED'
  ctx.vm.ontologyRevision = 2
  await ctx.vm.runValidation()
  assert.deepEqual(ctx.writes, [
    ['ontology', 7, { target: 'WORKING' }],
    ['ontology', 7, { target: 'PUBLISHED', revision: 2 }],
  ])
})

test('late graph validation cannot replace a new ontology report or clear its busy state', async (t) => {
  const graph = deferred(),
    ontology = deferred()
  const ctx = await setup(t, {
    validateGraph: () => graph.promise,
    validateOntology: () => ontology.promise,
  })
  ctx.vm.selectedGraphId = 1
  const first = ctx.vm.runValidation()
  await settle()
  ctx.vm.scope = 'ONTOLOGY'
  await settle()
  ctx.vm.selectedOntologyId = 7
  const second = ctx.vm.runValidation()
  await settle()
  graph.resolve(report(1))
  await first
  assert.equal(ctx.vm.reportId, null)
  assert.equal(ctx.vm.running, true)
  ontology.resolve(report(7))
  await second
  await settle()
  assert.equal(ctx.vm.reportId, 7)
  assert.equal(ctx.vm.running, false)
  assert.deepEqual(ctx.vm.results, results)
})

test('double activation issues one request and viewer cannot issue either validation write', async (t) => {
  const pending = deferred()
  let requests = 0
  const ctx = await setup(t, {
    validateGraph: () => {
      requests++
      return pending.promise
    },
  })
  ctx.vm.selectedGraphId = 1
  const first = ctx.vm.runValidation()
  await ctx.vm.runValidation()
  await settle()
  assert.equal(requests, 1)
  pending.resolve(report(1))
  await first
  const viewer = await setup(t, {}, 'VIEWER')
  viewer.vm.selectedGraphId = 1
  await viewer.vm.runValidation()
  viewer.vm.scope = 'ONTOLOGY'
  await settle()
  viewer.vm.selectedOntologyId = 7
  await viewer.vm.runValidation()
  assert.deepEqual(viewer.writes, [])
})

test('four-state readouts are unknown before a report and filters retain focus and evidence detail', async (t) => {
  const ctx = await setup(t, {}, 'EDITOR', '/?graph=1')
  assert.equal(ctx.vm.selectedGraphId, 1)
  assert.deepEqual(
    ctx.vm.readouts.map((item) => item.count),
    [undefined, undefined, undefined, undefined],
  )
  await ctx.vm.runValidation()
  await settle()
  assert.deepEqual(
    ctx.vm.readouts.map((item) => [item.state, item.count]),
    ['PASS', 'VIOLATION', 'NA', 'NOT_RUN'].map((state) => [state, 1]),
  )
  for (const result of results) {
    ctx.vm.stateFilter = result.state
    assert.deepEqual(ctx.vm.filteredResults, [result])
  }
  ctx.vm.selectedResult = results[3]
  ctx.vm.selectedGraphId = 2
  assert.equal(ctx.vm.reportId, null)
  assert.equal(ctx.vm.selectedResult, null)
  assert.deepEqual(ctx.vm.results, [])
})

test('same-report result refresh ignores obsolete failure and retains the latest structured rows', async (t) => {
  const first = deferred(),
    second = deferred()
  let reads = 0
  const ctx = await setup(t, {
    getResults: () => {
      reads++
      return reads === 1 ? Promise.resolve(results) : reads === 2 ? first.promise : second.promise
    },
  })
  ctx.vm.selectedGraphId = 1
  await ctx.vm.runValidation()
  const older = ctx.vm.loadResults(),
    newer = ctx.vm.loadResults()
  second.resolve([results[3]])
  await newer
  first.reject({ code: 'KG.FORBIDDEN' })
  await older
  assert.deepEqual(ctx.vm.results, [results[3]])
  assert.equal(ctx.vm.resultsError, '')
  assert.equal(ctx.vm.loadingResults, false)
})
