import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, settle } from '../../../../testing/view-harness.mjs'
import { mountC4 } from '../../../account/__tests__/c4-render-harness.mjs'

test('user create/edit close requests preserve cancelled drafts, confirm discard and bypass confirmation after saving', async (t) => {
  const user = { id: 'other-user', username: 'other_user', role: 'VIEWER', status: 'ACTIVE' }
  const writes = []
  const ctx = await mountC4(
    t,
    'views/system/users/UsersPage.vue',
    {
      users: async () => ({ items: [user], total: 1 }),
      createUser: async (input) => {
        writes.push(input)
        return { ...input, id: 'new-user' }
      },
      updateUser: async (id, input) => {
        writes.push(input)
        return { ...user, ...input, id }
      },
    },
    'editing,editForm,showCreate,createForm,createVisible,editVisible,openEdit,openCreate,save,submitCreate',
    'ADMIN',
  )
  t.after(ctx.stop)
  const original = Object.getOwnPropertyDescriptor(globalThis, 'window')
  const prompts = []
  let accept = false
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      confirm: (message) => {
        prompts.push(message)
        return accept
      },
      addEventListener() {},
      removeEventListener() {},
    },
  })
  t.after(() => {
    if (original) Object.defineProperty(globalThis, 'window', original)
    else delete globalThis.window
  })
  ctx.vm.openCreate()
  await settle()
  ctx.vm.createForm.username = 'unsaved_user'
  ctx.vm.createVisible = false
  assert.equal(ctx.vm.showCreate, true)
  assert.equal(ctx.vm.createForm.username, 'unsaved_user')
  accept = true
  ctx.vm.createVisible = false
  assert.equal(ctx.vm.showCreate, false)
  ctx.vm.openCreate()
  await settle()
  Object.assign(ctx.vm.createForm, {
    username: 'new_user',
    email: 'new@example.org',
    password: 'Test-Password-2026!',
  })
  await ctx.vm.submitCreate()
  assert.equal(ctx.vm.showCreate, false)
  assert.equal(prompts.length, 2)
  assert.equal(writes.length, 1)
  ctx.vm.openEdit(user)
  await settle()
  ctx.vm.editVisible = false
  assert.equal(ctx.vm.editing, null)
  assert.equal(prompts.length, 2, 'initial role/status are the baseline')
  ctx.vm.openEdit(user)
  await settle()
  ctx.vm.editForm.role = 'EDITOR'
  accept = false
  ctx.vm.editVisible = false
  assert.equal(ctx.vm.editing.id, user.id)
  assert.equal(ctx.vm.editForm.role, 'EDITOR')
  await ctx.vm.save()
  assert.equal(ctx.vm.editing, null)
  assert.equal(prompts.length, 3)
  assert.equal(writes.length, 2)
})

test('obsolete user creation cannot close or release a new session pending creation', async (t) => {
  const pending = [deferred(), deferred()]
  let calls = 0
  const ctx = await mountC4(
    t,
    'views/system/users/UsersPage.vue',
    {
      users: async () => ({ items: [], total: 0 }),
      createUser: () => pending[calls++].promise,
    },
    'openCreate,submitCreate,createForm,showCreate,creating,createError,auth',
  )
  ctx.vm.openCreate()
  Object.assign(ctx.vm.createForm, {
    username: 'first_user',
    email: 'first@example.org',
    password: 'LongEnough1',
  })
  await settle()
  const first = ctx.vm.submitCreate()
  await settle()
  await ctx.vm.submitCreate()
  assert.equal(calls, 1)
  ctx.vm.auth.user = { id: 'second_actor', role: 'ADMIN' }
  await settle()
  ctx.vm.openCreate()
  Object.assign(ctx.vm.createForm, {
    username: 'second_user',
    email: 'second@example.org',
    password: 'LongEnough1',
  })
  await settle()
  const second = ctx.vm.submitCreate()
  await settle()
  assert.equal(calls, 2)
  pending[0].resolve({ id: 'first_user' })
  await first
  assert.equal(ctx.vm.showCreate, true)
  assert.equal(ctx.vm.createForm.username, 'second_user')
  assert.equal(ctx.vm.creating, true)
  pending[1].resolve({ id: 'second_user' })
  await second
  assert.equal(ctx.vm.showCreate, false)
})
