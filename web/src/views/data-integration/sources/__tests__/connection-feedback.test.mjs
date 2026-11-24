import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from '../../../../testing/view-harness.mjs'

async function connectionForm(t) {
  const requests = []
  const ctx = await mount(
    'views/data-integration/sources/DataSourcesPage.vue',
    {
      '@/api/datasources': {
        datasourcesApi: {
          list: async () => [],
          testConnection: (payload, signal) => {
            const pending = deferred()
            requests.push({ ...pending, payload, signal })
            // Deliberately ignore cancellation to verify response ownership too.
            return pending.promise
          },
        },
      },
    },
    'form,formRef,showCreate,openCreate,testConnection,testResult,formError,testing',
  )
  let stopped = false
  const stop = () => {
    if (stopped) return
    stopped = true
    ctx.stop()
  }
  t.after(stop)
  ctx.vm.openCreate()
  // This suite isolates response ownership; real Form/Field validation is covered
  // by sources-form.test.mjs. The page now awaits its real form ref before testing.
  ctx.vm.formRef = { validate: async () => {}, restoreValidation() {} }
  ctx.vm.form.name = 'Source'
  ctx.vm.form.database = 'source.sqlite'
  return { ...ctx, stop, requests }
}

test('connection feedback is invalidated by connection edits, but not the display name', async (t) => {
  const { vm, requests } = await connectionForm(t)
  const pending = vm.testConnection()
  await settle()
  requests[0].resolve({ ok: true, table_count: 17 })
  await pending
  vm.form.name = 'Renamed source'
  await settle()
  assert.equal(vm.testResult.table_count, 17)
  vm.form.credential = 'changed-credential'
  assert.equal(vm.testResult, null)
  assert.equal(vm.formError, '')
})

test('A to B to A cannot restore a stale result or clear a newer loading state', async (t) => {
  const { vm, requests } = await connectionForm(t)
  const first = vm.testConnection()
  await settle()
  vm.form.database = 'other.sqlite'
  vm.form.database = 'source.sqlite'
  assert.equal(requests[0].signal.aborted, true)
  const second = vm.testConnection()
  await settle()
  requests[0].resolve({ ok: true, table_count: 99 })
  await first
  assert.equal(vm.testResult, null)
  assert.equal(vm.testing, true)
  requests[1].resolve({ ok: false })
  await second
  assert.deepEqual(vm.testResult, { ok: false })
  assert.equal(vm.testing, false)
})

test('closing and reopening rejects stale failures while the current request remains usable', async (t) => {
  const { vm, requests } = await connectionForm(t)
  const first = vm.testConnection()
  await settle()
  vm.showCreate = false
  assert.equal(requests[0].signal.aborted, true)
  vm.openCreate()
  vm.form.name = 'Reopened source'
  vm.form.database = 'source.sqlite'
  const second = vm.testConnection()
  await settle()
  requests[0].reject(new Error('stale connection failure'))
  await first
  assert.equal(vm.formError, '')
  assert.equal(vm.testing, true)
  requests[1].reject(new Error('current connection failure'))
  await second
  assert.notEqual(vm.formError, '')
  assert.equal(vm.testing, false)
  const retry = vm.testConnection()
  await settle()
  assert.equal(vm.formError, '')
  requests[2].resolve({ ok: true, table_count: 17 })
  await retry
  assert.equal(vm.testResult.table_count, 17)
})

test('leaving the page aborts connection testing and ignores its late response', async (t) => {
  const { vm, requests, stop } = await connectionForm(t)
  const pending = vm.testConnection()
  await settle()
  // Unmount the component without invoking its draft-close confirmation.
  stop()
  requests[0].resolve({ ok: true, table_count: 99 })
  await pending
  assert.equal(requests[0].signal.aborted, true)
  assert.equal(vm.testResult, null)
  assert.equal(vm.testing, false)
})
