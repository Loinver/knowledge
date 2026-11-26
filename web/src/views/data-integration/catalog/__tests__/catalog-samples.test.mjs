import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from './catalog-harness.mjs'

const props = { datasourceId: 7, schema: 'main', table: 'employees', snapshotId: 1 }
const expose = 'requested,data,error,loading,reload'

test('catalog samples are explicitly requested, bounded, and discarded on table or snapshot changes', async (t) => {
  const calls = []
  const view = await mount(
    'components/CatalogSamples.vue',
    {
      datasourcesApi: {
        preview: (payload, signal) => {
          const call = { payload, signal, ...deferred() }
          calls.push(call)
          return call.promise
        },
      },
    },
    expose,
    '/catalog',
    'EDITOR',
    props,
  )
  t.after(view.stop)
  assert.equal(calls.length, 0)
  view.vm.requested = true
  await settle()
  assert.deepEqual(calls[0].payload, {
    datasource_id: 7,
    schema: 'main',
    table: 'employees',
    limit: 5,
    offset: 0,
  })
  assert.equal(view.vm.loading, true)
  await view.updateProps({ table: 'departments' })
  assert.equal(calls[0].signal.aborted, true)
  assert.equal(view.vm.requested, false)
  calls[0].resolve({ rows: [{ private_name: 'obsolete' }] })
  await settle()
  assert.equal(view.vm.data, null)
  assert.equal(view.vm.loading, false)
  view.vm.requested = true
  await settle()
  assert.equal(calls[1].payload.table, 'departments')
  calls[1].resolve({ rows: [{ id: 1 }] })
  await settle()
  assert.deepEqual(view.vm.data.rows, [{ id: 1 }])
  await view.updateProps({ snapshotId: 2 })
  assert.equal(view.vm.data, null)
  assert.equal(view.vm.requested, false)
  assert.equal(calls.length, 2)
})

test('sample errors remain errors, retry recovers, and unmount prevents a late sample result', async (t) => {
  let fails = true
  const pending = deferred()
  let signal
  const view = await mount(
    'components/CatalogSamples.vue',
    {
      datasourcesApi: {
        preview: (_payload, currentSignal) => {
          signal = currentSignal
          return fails ? Promise.reject({ code: 'KG.SOURCE_UNREACHABLE' }) : pending.promise
        },
      },
    },
    expose,
    '/catalog',
    'VIEWER',
    props,
  )
  t.after(view.stop)
  view.vm.requested = true
  await settle()
  assert.match(view.vm.error, /KG.SOURCE_UNREACHABLE/)
  assert.equal(view.vm.data, null)
  assert.equal(view.vm.loading, false)
  fails = false
  view.vm.reload()
  await settle()
  assert.equal(view.vm.error, '')
  view.stop()
  assert.equal(signal.aborted, true)
  pending.resolve({ rows: [{ id: 99 }] })
  await settle()
  assert.equal(view.vm.data, null)
})
