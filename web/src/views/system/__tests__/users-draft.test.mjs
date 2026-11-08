import assert from 'node:assert/strict'
import { test } from 'node:test'

import { mount, settle } from '../../__tests__/view-harness.mjs'

test('user create/edit close requests preserve cancelled drafts, confirm discard and bypass confirmation after saving', async (t) => {
  const user = { id: 'other-user', username: 'other_user', role: 'VIEWER', status: 'ACTIVE' }
  const writes = []
  const ctx = await mount(
    'views/system/Users.vue',
    {
      '@/api/auth': {
        authApi: {
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
      },
    },
    'editing,editForm,showCreate,createForm,createVisible,editVisible,openEdit,openCreate,save,submitCreate',
    '/',
    undefined,
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
