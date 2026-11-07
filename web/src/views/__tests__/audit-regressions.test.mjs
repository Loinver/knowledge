import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from './view-harness.mjs'

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
test('task creation uses the latest selected mapping revision', async () => {
  const first = deferred(),
    second = deferred(),
    writes = []
  globalThis.window = { setInterval: () => 1, clearInterval: () => {} }
  const ctx = await mount(
    'views/extraction/ExtractionTasks.vue',
    {
      '@/api/extraction': {
        extractionApi: {
          tasks: async () => [],
          createTask: async (p) => {
            writes.push(p)
            return { id: 1 }
          },
        },
      },
      '@/api/mappings': {
        mappingsApi: {
          list: async () => [],
          published: (id) => (id === 1 ? first.promise : second.promise),
        },
      },
      '@/api/datasources': { datasourcesApi: { list: async () => [] } },
    },
    'chooseMapping,selectedMappingId,publishedRevisionId,selectedDatasourceId,canCreate,createTask',
  )
  const a = ctx.vm.chooseMapping(1),
    b = ctx.vm.chooseMapping(2)
  second.resolve({ id: 202 })
  await b
  first.resolve({ id: 101 })
  await a
  ctx.vm.selectedDatasourceId = 9
  assert.equal(ctx.vm.selectedMappingId, 2)
  assert.equal(ctx.vm.publishedRevisionId, 202)
  assert.equal(ctx.vm.canCreate, true)
  await ctx.vm.createTask()
  assert.equal(writes[0].mapping_revision_id, 202)
  ctx.stop()
  delete globalThis.window
})

test('task polling never starts after unmount during initial reads', async () => {
  const initial = deferred(),
    timers = [],
    clears = []
  globalThis.window = {
    setInterval: (fn) => {
      timers.push(fn)
      return timers.length
    },
    clearInterval: (id) => clears.push(id),
  }
  const ctx = await mount(
    'views/extraction/ExtractionTasks.vue',
    {
      '@/api/extraction': { extractionApi: { tasks: () => initial.promise } },
      '@/api/mappings': { mappingsApi: { list: async () => [] } },
      '@/api/datasources': { datasourcesApi: { list: async () => [] } },
    },
    'tasks',
  )
  ctx.stop()
  initial.resolve([])
  await settle()
  assert.equal(timers.length, 0)
  assert.deepEqual(clears, [])
  delete globalThis.window
})
