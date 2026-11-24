import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from '../../../../../../testing/view-harness.mjs'

async function designer(t, validate) {
  const ontology = {
    id: 1,
    name: 'Fictional',
    label_i18n: { 'en-US': 'Fictional' },
    status: 'PUBLISHED',
    current_revision: 7,
    edit_revision: 8,
    working_draft_id: 'ontology:1:working',
  }
  const ctx = await mount(
    'views/ontology/designer/DesignerPage.vue',
    {
      '@/api/ontology': {
        ontologyApi: {
          list: async () => [ontology],
          get: async () => ontology,
          refs: async () => [],
          getCanvas: async () => ({ positions: {} }),
        },
      },
      '@/api/entity-types': { entityTypesApi: { list: async () => [] } },
      '@/api/relations': { relationsApi: { list: async () => [] } },
      '@/api/domains': { domainsApi: { list: async () => [] } },
      '@/api/governance': { rulesApi: { all: async () => [] } },
      '@/api/ontology-history': {
        ontologyHistoryApi: { contents: async () => ({ resources: [], rules: [] }) },
      },
      '@/api/validation': {
        validationApi: {
          validateOntology: validate,
          getResults: async () => [{ check_code: 'A01', state: 'NOT_RUN' }],
        },
      },
    },
    'canEdit,canValidate,runValidation,changeRevision,validationReport,validationResults,validating,frozenRevision',
  )
  t.after(ctx.stop)
  return ctx
}

test('Designer validates WORKING explicitly and selected historical revision as PUBLISHED', async (t) => {
  const calls = []
  const ctx = await designer(t, async (id, options) => {
    calls.push({ id, options })
    return { report_id: 1, summary: { pass: 0, violation: 0, na: 0, not_run: 1 } }
  })
  await ctx.vm.runValidation()
  assert.deepEqual(calls[0], { id: 1, options: { target: 'WORKING' } })
  await ctx.vm.changeRevision(3)
  assert.equal(ctx.vm.canEdit, false)
  assert.equal(ctx.vm.canValidate, true)
  await ctx.vm.runValidation()
  assert.deepEqual(calls[1], { id: 1, options: { target: 'PUBLISHED', revision: 3 } })
  assert.equal(ctx.vm.validationResults[0].state, 'NOT_RUN')
})

test('late historical validation cannot replace a different selected revision or clear its busy state', async (t) => {
  const old = deferred(),
    current = deferred()
  let calls = 0
  const ctx = await designer(t, () => (++calls === 1 ? old.promise : current.promise))
  await ctx.vm.changeRevision(2)
  const first = ctx.vm.runValidation()
  await ctx.vm.changeRevision(3)
  const second = ctx.vm.runValidation()
  old.resolve({ report_id: 2 })
  await first
  assert.equal(ctx.vm.validating, true)
  assert.equal(ctx.vm.validationReport, null)
  current.resolve({ report_id: 3 })
  await second
  assert.equal(ctx.vm.validationReport.report_id, 3)
  assert.equal(ctx.vm.validating, false)
  await settle()
})
