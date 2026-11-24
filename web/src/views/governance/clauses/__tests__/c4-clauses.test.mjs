import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from '../../../../testing/view-harness.mjs'

const stub = (api) => ({
  '@/api/clauses': { clausesApi: { list: async () => ({ items: [], total: 0 }), ...api } },
})
const fill = (ctx) => {
  ctx.vm.form.standard = 'EXAMPLE-1'
  ctx.vm.form.clause_number = '1.1'
  ctx.vm.form.title_i18n['zh-CN'] = '示例条款'
  ctx.vm.form.self_authored_description['zh-CN'] = '自撰示例说明'
}

test('clause editor preserves NORMATIVE in options, labels and create payload', async (t) => {
  const calls = []
  const ctx = await mount(
    'views/governance/clauses/StandardClausesPage.vue',
    stub({
      create: async (input) => {
        calls.push(input)
        return { ...input, id: 1, revision: 1 }
      },
    }),
    'form,formRef,openCreate,submit,natureOptions,columns,saved',
  )
  t.after(ctx.stop)
  ctx.vm.openCreate()
  fill(ctx)
  await settle()
  ctx.vm.formRef = { validate: async () => {}, restoreValidation() {} }
  await ctx.vm.submit()
  assert.equal(calls[0].appendix_nature, 'NORMATIVE')
  assert.deepEqual(
    ctx.vm.natureOptions.map((option) => option.value),
    ['NORMATIVE', 'INFORMATIVE'],
  )
  assert.equal(ctx.vm.natureOptions[0].label, 'Normative')
  const nature = ctx.vm.columns.find((column) => column.key === 'appendix_nature')
  assert.equal(nature.render({ appendix_nature: 'NORMATIVE' }), 'Normative')
  assert.equal(nature.render({ appendix_nature: 'INFORMATIVE' }), 'Informative')
  assert.equal(ctx.vm.saved.appendix_nature, 'NORMATIVE')
})

test('failed clause save keeps the form and stale completion cannot change a new session', async (t) => {
  const requests = []
  const ctx = await mount(
    'views/governance/clauses/StandardClausesPage.vue',
    stub({
      create: (payload) => {
        const request = { ...deferred(), payload }
        requests.push(request)
        return request.promise
      },
    }),
    'form,formRef,openCreate,submit,showEditor,saved,error,busy',
  )
  t.after(ctx.stop)
  ctx.vm.openCreate()
  fill(ctx)
  await settle()
  ctx.vm.formRef = { validate: async () => {}, restoreValidation() {} }
  const failed = ctx.vm.submit()
  await settle()
  await ctx.vm.submit()
  assert.equal(requests.length, 1)
  requests[0].reject({ code: 'KG.REVISION_CONFLICT' })
  await failed
  assert.equal(ctx.vm.showEditor, true)
  assert.equal(ctx.vm.form.standard, 'EXAMPLE-1')
  assert.notEqual(ctx.vm.error, '')
  const old = ctx.vm.submit()
  await settle()
  ctx.vm.showEditor = false
  ctx.vm.openCreate()
  fill(ctx)
  ctx.vm.form.standard = 'NEW-2'
  requests[1].resolve({ ...requests[1].payload, id: 1, revision: 1 })
  await old
  assert.equal(ctx.vm.saved, null)
  assert.equal(ctx.vm.showEditor, true)
  assert.equal(ctx.vm.form.standard, 'NEW-2')
  assert.equal(ctx.vm.busy, false)
})
