import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount } from './view-harness.mjs'

test('clause table uses its summary contract and editing reads the full detail', async (t) => {
  const brief = {
    id: 7,
    revision: 3,
    standard: 'SYNTHETIC',
    clause_number: '1',
    title_i18n: { 'zh-CN': '合成条款', 'en-US': 'Synthetic clause' },
    appendix_nature: 'NORMATIVE',
    product_fallback: null,
  }
  const detail = deferred()
  const reads = []
  const ctx = await mount(
    'views/governance/StandardClauses.vue',
    {
      '@/api/clauses': {
        clausesApi: {
          list: async () => ({ items: [brief], total: 1 }),
          get: (id) => {
            reads.push(id)
            return detail.promise
          },
        },
      },
    },
    'items,columns,openEdit,form,saved,showEditor,busy',
  )
  t.after(ctx.stop)
  assert.equal(
    ctx.vm.columns.find((column) => column.key === 'title').render(ctx.vm.items[0]),
    'Synthetic clause',
  )
  const editing = ctx.vm.openEdit(ctx.vm.items[0])
  assert.equal(ctx.vm.showEditor, false)
  assert.equal(ctx.vm.busy, true)
  detail.resolve({
    ...brief,
    self_authored_description: { 'zh-CN': '完整说明', 'en-US': 'Complete note' },
  })
  await editing
  assert.deepEqual(reads, [7])
  assert.equal(ctx.vm.saved.revision, 3)
  assert.equal(ctx.vm.form.self_authored_description['en-US'], 'Complete note')
  assert.equal(ctx.vm.showEditor, true)
  assert.equal(ctx.vm.busy, false)
})
