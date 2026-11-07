import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from '../../__tests__/view-harness.mjs'

const entry = 'views/system/components/AssetAuditLogs.vue'
const expose =
  'data,error,loading,page,query,action,objectType,result,timeRange,search,reset,reload'

test('audit filters use server pagination, UTC ranges and reset to the first page', async (t) => {
  const calls = []
  const ctx = await mount(
    entry,
    {
      '@/api/asset-audit': {
        assetAuditApi: {
          page: async (query) => {
            calls.push(query)
            return { items: [{ id: query.page }], page: query.page, page_size: 20, total: 45 }
          },
        },
      },
    },
    expose,
  )
  t.after(ctx.stop)
  ctx.vm.page = 2
  await settle()
  assert.equal(calls.at(-1).page, 2)
  assert.equal(calls.at(-1).page_size, 20)
  ctx.vm.query = '  correlation-123  '
  ctx.vm.action = 'PUBLISH'
  ctx.vm.objectType = 'ONTOLOGY'
  ctx.vm.result = 'FAILED'
  ctx.vm.timeRange = [
    Date.parse('2026-11-01T08:00:00+08:00'),
    Date.parse('2026-11-02T08:00:00+08:00'),
  ]
  ctx.vm.search()
  await settle()
  assert.deepEqual(calls.at(-1), {
    q: 'correlation-123',
    action: 'PUBLISH',
    object_type: 'ONTOLOGY',
    result: 'FAILED',
    since: '2026-11-01T00:00:00.000Z',
    until: '2026-11-02T00:00:00.000Z',
    page: 1,
    page_size: 20,
  })
  ctx.vm.reset()
  await settle()
  assert.equal(calls.at(-1).q, undefined)
  assert.equal(calls.at(-1).since, undefined)
  assert.equal(calls.at(-1).object_type, undefined)
})

test('late audit responses cannot replace current filters or survive unmount', async (t) => {
  const pending = [deferred(), deferred(), deferred()]
  const signals = []
  const ctx = await mount(
    entry,
    {
      '@/api/asset-audit': {
        assetAuditApi: {
          page: (_query, signal) => {
            signals.push(signal)
            return pending[signals.length - 1].promise
          },
        },
      },
    },
    expose,
  )
  t.after(ctx.stop)
  ctx.vm.action = 'DELETE'
  ctx.vm.search()
  await settle()
  assert.equal(signals[0].aborted, true)
  pending[1].resolve({ items: [{ id: 2 }], total: 1, page: 1, page_size: 20 })
  await settle()
  pending[0].resolve({ items: [{ id: 1 }], total: 1, page: 1, page_size: 20 })
  await settle()
  assert.equal(ctx.vm.data.items[0].id, 2)
  ctx.vm.reload()
  await settle()
  ctx.stop()
  assert.equal(signals[2].aborted, true)
  pending[2].resolve({ items: [{ id: 3 }], total: 1, page: 1, page_size: 20 })
  await settle()
  assert.equal(ctx.vm.data, null)
})

test('failed audit reads clear previous records and allow an explicit retry', async (t) => {
  let count = 0
  const ctx = await mount(
    entry,
    {
      '@/api/asset-audit': {
        assetAuditApi: {
          page: async () => {
            count++
            if (count === 2) throw { code: 'AUTH.FORBIDDEN' }
            return { items: [{ id: count }], total: 1, page: 1, page_size: 20 }
          },
        },
      },
    },
    expose,
  )
  t.after(ctx.stop)
  assert.equal(ctx.vm.data.items[0].id, 1)
  ctx.vm.reload()
  await settle()
  assert.equal(ctx.vm.data, null)
  assert.match(ctx.vm.error, /AUTH.FORBIDDEN/)
  assert.equal(ctx.vm.loading, false)
  ctx.vm.reload()
  await settle()
  assert.equal(ctx.vm.error, '')
  assert.equal(ctx.vm.data.items[0].id, 3)
})
