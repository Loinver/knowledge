import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from '../../../../testing/view-harness.mjs'

const source = (id) => ({ id, name: `Source ${id}`, kind: 'sqlite', status: 'DISCONNECTED' })
async function setup(t, overrides = {}, role = 'EDITOR') {
  const calls = { list: [], create: [], update: [], remove: [], testStored: [], testConnection: [] }
  const api = Object.fromEntries(
    Object.keys(calls).map((name) => [
      name,
      async (...args) => {
        calls[name].push(args)
        if (overrides[name]) return overrides[name](...args)
        return name === 'list' ? [] : name === 'remove' ? undefined : { ok: true, id: 1 }
      },
    ]),
  )
  const ctx = await mount(
    'views/data-integration/sources/DataSourcesPage.vue',
    {
      '@/api/datasources': { datasourcesApi: api },
    },
    'auth,items,visible,query,appliedQuery,kindFilter,statusFilter,page,loading,error,load,search,resetSearch,showCreate,openCreate,form,formRef,createSource,createBusy,saving,formError,showEdit,openEdit,editingId,editForm,editFormRef,saveEdit,editBusy,savingEdit,editError,testConnection,testStored,removeSource,rowLocked,testingId',
    '/',
    undefined,
    role,
  )
  // These tests isolate handler ownership. sources-form.test uses the actual component refs.
  ctx.vm.formRef = { validate: async () => {}, restoreValidation() {} }
  ctx.vm.editFormRef = { validate: async () => {}, restoreValidation() {} }
  let stopped = false
  const stop = () => {
    if (!stopped) {
      stopped = true
      ctx.stop()
    }
  }
  t.after(stop)
  return { ...ctx, stop, calls }
}
function fill(vm) {
  vm.form.name = 'Source'
  vm.form.database = 'source.sqlite'
}

test('create close/reopen ignores old success/error/finally and current failure retains input', async (t) => {
  const requests = []
  const { vm, calls } = await setup(t, {
    create: () => {
      const d = deferred()
      requests.push(d)
      return d.promise
    },
  })
  vm.openCreate()
  fill(vm)
  const old = vm.createSource()
  await settle()
  vm.showCreate = false
  vm.openCreate()
  fill(vm)
  const current = vm.createSource()
  await settle()
  requests[0].resolve(source(1))
  await old
  assert.equal(vm.showCreate, true)
  assert.equal(vm.saving, true)
  assert.equal(calls.list.length, 1)
  requests[1].reject(new Error('current failure'))
  await current
  assert.equal(vm.saving, false)
  assert.equal(vm.form.name, 'Source')
  assert.ok(vm.formError)
  const stale = vm.createSource()
  await settle()
  vm.showCreate = false
  vm.openCreate()
  fill(vm)
  const fresh = vm.createSource()
  await settle()
  requests[2].reject(new Error('stale failure'))
  await stale
  assert.equal(vm.formError, '')
  assert.equal(vm.createBusy, true)
  requests[3].resolve(source(2))
  await fresh
  assert.equal(vm.showCreate, false)
  assert.equal(calls.create.length, 4)
  assert.equal(calls.list.length, 2)
})

test('edit captures ID and session, blocks stored tests on that ID, and preserves a new editor', async (t) => {
  const requests = []
  const { vm, calls } = await setup(t, {
    update: () => {
      const d = deferred()
      requests.push(d)
      return d.promise
    },
  })
  vm.openEdit(source(1))
  vm.editForm.credential = ' synthetic '
  const old = vm.saveEdit()
  await settle()
  await vm.testStored(source(1))
  await vm.removeSource(source(1))
  assert.equal(calls.testStored.length, 0)
  assert.equal(calls.remove.length, 0)
  vm.openEdit(source(2))
  vm.editForm.name = 'New draft'
  const current = vm.saveEdit()
  await settle()
  assert.deepEqual(calls.update[0], [1, { name: 'Source 1', credential: ' synthetic ' }])
  assert.deepEqual(calls.update[1], [2, { name: 'New draft' }])
  requests[0].reject(new Error('old editor'))
  await old
  assert.equal(vm.editError, '')
  assert.equal(vm.savingEdit, true)
  assert.equal(vm.editingId, 2)
  assert.equal(vm.editForm.name, 'New draft')
  requests[1].reject(new Error('new editor'))
  await current
  assert.ok(vm.editError)
  assert.equal(vm.showEdit, true)
  const retry = vm.saveEdit()
  await settle()
  vm.showEdit = false
  vm.openEdit(source(3))
  requests[2].resolve(source(2))
  await retry
  assert.equal(vm.showEdit, true)
  assert.equal(vm.editingId, 3)
  assert.equal(calls.list.length, 1)
})

test('stored test row owner isolates a new view and holds same-ID lock until the request settles', async (t) => {
  const requests = []
  const { vm, calls } = await setup(t, {
    testStored: () => {
      const d = deferred()
      requests.push(d)
      return d.promise
    },
  })
  const old = vm.testStored(source(1))
  vm.openEdit(source(1))
  assert.equal(vm.showEdit, false)
  await vm.search('new query')
  assert.equal(calls.testStored[0][0], 1)
  vm.openEdit(source(1))
  assert.equal(vm.showEdit, false, 'HTTP may still run after owner invalidation')
  const current = vm.testStored(source(2))
  requests[0].reject(new Error('old row'))
  await old
  assert.equal(vm.error, '')
  assert.equal(vm.testingId, 2)
  assert.equal(vm.rowLocked(1), false)
  requests[1].resolve({ ok: true })
  await current
  assert.equal(calls.list.length, 3)
  assert.equal(vm.testingId, null)
  vm.openEdit(source(1))
  assert.equal(vm.showEdit, true)
})

test('delete distinguishes undefined success from failure and rejects stale completion', async (t) => {
  const requests = []
  const { vm, calls } = await setup(t, {
    remove: () => {
      const d = deferred()
      requests.push(d)
      return d.promise
    },
  })
  const fail = vm.removeSource(source(1))
  requests[0].reject(new Error('RESOURCE_IN_USE'))
  assert.equal(await fail, false)
  assert.ok(vm.error)
  assert.equal(calls.list.length, 1)
  const old = vm.removeSource(source(1))
  await vm.search('elsewhere')
  requests[1].resolve(undefined)
  assert.equal(await old, false)
  assert.equal(calls.list.length, 2)
  const success = vm.removeSource(source(2))
  requests[2].resolve(undefined)
  assert.equal(await success, true)
  assert.equal(calls.list.length, 3)
})

test('query draft stays unapplied; older successes/errors cannot replace the current query', async (t) => {
  const requests = []
  const { vm } = await setup(t, {
    list: () => {
      const d = deferred()
      requests.push(d)
      return d.promise
    },
  })
  requests[0].resolve([source(1)])
  await settle()
  vm.query = 'unsubmitted'
  assert.equal(vm.visible.length, 1)
  assert.equal(vm.appliedQuery, '')
  const old = vm.search('first')
  assert.equal(vm.items.length, 0)
  const current = vm.search('second')
  requests[1].reject(new Error('old search'))
  await old
  assert.equal(vm.error, '')
  assert.equal(vm.loading, true)
  requests[2].resolve([source(2)])
  await current
  const refresh = vm.load()
  assert.equal(vm.items[0].id, 2, 'same-query refresh retains its snapshot')
  requests[3].reject(new Error('current query'))
  await refresh
  assert.ok(vm.error)
  assert.equal(vm.items[0].id, 2)
  const empty = vm.search('empty')
  requests[4].resolve([])
  await empty
  assert.equal(vm.error, '')
  assert.equal(vm.items.length, 0)
})

test('permission downgrade/unmount suppress continuations; VIEWER handlers never write', async (t) => {
  const request = deferred()
  const { vm, calls, stop } = await setup(t, { create: () => request.promise })
  vm.openCreate()
  fill(vm)
  const old = vm.createSource()
  await settle()
  vm.auth.user.role = 'VIEWER'
  request.resolve(source(1))
  await old
  assert.equal(vm.showCreate, true)
  assert.equal(calls.list.length, 1)
  vm.openEdit(source(1))
  await vm.createSource()
  await vm.saveEdit()
  await vm.removeSource(source(1))
  await vm.testStored(source(1))
  assert.equal(calls.create.length, 1)
  assert.equal(calls.update.length + calls.remove.length + calls.testStored.length, 0)
  // The temporary POST remains the existing read-only exception; no new VIEWER UI entry.
  await vm.testConnection()
  assert.equal(calls.testConnection.length, 1)
  vm.auth.user.role = 'EDITOR'
  const gate = deferred()
  vm.formRef.validate = () => gate.promise
  const pending = vm.createSource()
  stop()
  gate.resolve()
  await pending
  assert.equal(calls.create.length, 1)
})
