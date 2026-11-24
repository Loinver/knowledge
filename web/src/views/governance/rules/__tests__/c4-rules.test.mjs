import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from '../../../../testing/view-harness.mjs'

test('governance tests preserve NOT_RUN and discard results invalidated by draft edits', async (t) => {
  const requests = []
  const rule = {
    id: 1,
    revision: 2,
    identifier: 'example',
    name_i18n: { 'zh-CN': '示例' },
    category: 'test',
    source_kind: 'ENTERPRISE',
    source_reference: 'example',
    target_iri: 'urn:example',
    severity: 'VIOLATION',
    language: 'OWL',
    expression: 'example',
    execution: 'MANUAL',
    positive_example: '',
    negative_example: '',
  }
  const ctx = await mount(
    'views/governance/rules/GovernanceRulesPage.vue',
    {
      '@/api/governance': {
        rulesApi: {
          list: async () => ({ items: [rule], total: 1 }),
          get: async () => rule,
          test: () => {
            const request = deferred()
            requests.push(request)
            return request.promise
          },
        },
      },
    },
    'editRule,form,runTest,testResult,stateType,busy',
  )
  t.after(ctx.stop)
  await ctx.vm.editRule(rule)
  const first = ctx.vm.runTest()
  requests[0].resolve({ revision: 2, state: 'NOT_RUN', positive: null, negative: null })
  await first
  assert.equal(ctx.vm.testResult.state, 'NOT_RUN')
  assert.equal(ctx.vm.stateType('NOT_RUN'), 'warning')
  assert.equal(ctx.vm.stateType('NA'), 'default')
  const second = ctx.vm.runTest()
  ctx.vm.form.expression = 'new draft'
  requests[1].resolve({ revision: 2, state: 'PASS' })
  await second
  await settle()
  assert.equal(ctx.vm.testResult, null)
  assert.equal(ctx.vm.busy, false)
})
