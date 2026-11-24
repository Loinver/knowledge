import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, settle } from '../../../testing/view-harness.mjs'
import { find, input, mountC4, submit } from './c4-render-harness.mjs'

test('profile validates actual fields, retains failed draft, and sends explicit null to clear', async (t) => {
  const calls = []
  let fail = true
  const user = {
    id: 'actor',
    role: 'ADMIN',
    username: 'test_actor',
    display_name: 'Initial',
    avatar_url: null,
  }
  const view = await mountC4(
    t,
    'views/account/ProfilePage.vue',
    {
      me: async () => user,
      updateProfile: async (payload) => {
        calls.push(payload)
        if (fail) throw { code: 'KG.INTERNAL_ERROR' }
        return { ...user, ...payload }
      },
    },
    'model,submit,cancel,error,saving,auth',
  )
  const display = view.field(view.i18n.global.t('account.displayName'))
  const avatar = view.field(view.i18n.global.t('account.avatarUrl'))
  await input(display, 'x'.repeat(33))
  await input(avatar, 'invalid URL')
  await view.vm.submit()
  assert.equal(calls.length, 0)
  assert.equal(view.tree.activeElement, display)
  assert.equal(view.invalid().length, 2)
  await input(display, ' Changed ')
  await input(avatar, '')
  await view.vm.submit()
  assert.equal(view.vm.model.display_name, ' Changed ')
  assert.ok(view.vm.error)
  assert.equal(view.vm.saving, false)
  fail = false
  await input(display, '')
  await view.vm.submit()
  assert.deepEqual(calls.at(-1), { display_name: null, avatar_url: null })
  assert.equal(view.vm.auth.user.display_name, null)
  assert.equal(view.vm.error, '')
})

test('password fields validate mismatch and preserve input on failure; duplicate and stale writes are ignored', async (t) => {
  const pending = deferred()
  let calls = 0
  let fail = true
  const view = await mountC4(
    t,
    'views/account/SecurityPage.vue',
    {
      changePassword: async () => {
        calls++
        if (fail) throw { code: 'KG.INTERNAL_ERROR' }
        return pending.promise
      },
    },
    'model,submit,error,saving,auth',
  )
  Object.assign(view.vm.model, {
    old_password: 'old',
    new_password: 'LongEnough1',
    confirm: 'wrong',
  })
  await settle()
  await view.vm.submit()
  assert.equal(calls, 0)
  assert.equal(view.invalid().length, 1)
  const confirm = view.field(view.i18n.global.t('auth.confirmPassword'))
  assert.equal(view.tree.activeElement, confirm)
  await input(confirm, 'LongEnough1')
  await view.vm.submit()
  assert.equal(view.vm.model.old_password, 'old')
  assert.ok(view.vm.error)
  fail = false
  const first = view.vm.submit()
  await settle()
  await view.vm.submit()
  assert.equal(calls, 2)
  assert.equal(view.vm.saving, true)
  view.vm.auth.user = { id: 'new-actor', role: 'ADMIN' }
  await settle()
  assert.equal(view.vm.saving, false)
  view.vm.model.old_password = 'new-session-input'
  pending.resolve({})
  await first
  assert.equal(view.vm.model.old_password, 'new-session-input')
  assert.equal(view.notices.length, 0)
})

test('login actual fields block invalid requests and retain credentials after rejected login', async (t) => {
  let calls = 0
  const view = await mountC4(
    t,
    'views/auth/LoginPage.vue',
    {
      config: async () => ({ registration_enabled: false }),
      login: async () => {
        calls++
        throw { code: 'AUTH.INVALID_CREDENTIALS' }
      },
    },
    'model,submit,error,submitting',
  )
  await view.vm.submit()
  assert.equal(calls, 0)
  assert.equal(view.invalid().length, 2)
  assert.equal(view.tree.activeElement, view.field(view.i18n.global.t('auth.account')))
  Object.assign(view.vm.model, { account: 'example_user', password: 'synthetic-password' })
  await settle()
  await view.vm.submit()
  assert.equal(calls, 1)
  assert.equal(view.vm.model.password, 'synthetic-password')
  assert.ok(view.vm.error)
  assert.equal(view.vm.submitting, false)
  assert.deepEqual(view.session.redirects, [])
})

test('reset without token cannot write; confirmation validation and obsolete token response protect route', async (t) => {
  const pending = deferred()
  const calls = []
  const view = await mountC4(
    t,
    'views/auth/ResetPasswordPage.vue',
    {
      resetPassword: async (...args) => {
        calls.push(args)
        return pending.promise
      },
    },
    'model,submit,error,loading',
  )
  Object.assign(view.vm.model, { password: 'LongEnough1', confirm: 'LongEnough1' })
  await view.vm.submit()
  assert.equal(calls.length, 0)
  view.session.route.query.token = 'synthetic-token-A'
  view.session.route.fullPath = '/reset-password?token=A'
  await settle()
  Object.assign(view.vm.model, { password: 'LongEnough1', confirm: 'wrong' })
  await settle()
  await view.vm.submit()
  assert.equal(calls.length, 0)
  view.vm.model.confirm = 'LongEnough1'
  await settle()
  const first = view.vm.submit()
  await settle()
  await view.vm.submit()
  assert.deepEqual(calls, [['synthetic-token-A', 'LongEnough1']])
  view.session.route.query.token = 'synthetic-token-B'
  view.session.route.fullPath = '/reset-password?token=B'
  pending.resolve({})
  await first
  assert.deepEqual(view.session.redirects, [])
})

test('registration config gates real fields, validation and rejected write retain the same draft', async (t) => {
  let calls = 0
  const view = await mountC4(
    t,
    'views/auth/RegisterPage.vue',
    {
      config: async () => ({ registration_enabled: true, password_min_length: 8 }),
      register: async () => {
        calls++
        throw { code: 'KG.INTERNAL_ERROR' }
      },
    },
    'model,submit,error',
  )
  Object.assign(view.vm.model, {
    username: 'invalid space',
    email: 'not-email',
    password: 'short',
    confirm: 'different',
  })
  await settle()
  await view.vm.submit()
  assert.equal(calls, 0)
  assert.equal(view.invalid().length, 4)
  Object.assign(view.vm.model, {
    username: 'example_user',
    email: 'example@example.org',
    password: 'LongEnough1',
    confirm: 'LongEnough1',
  })
  await settle()
  await view.vm.submit()
  assert.equal(calls, 1)
  assert.ok(view.vm.error)
  assert.equal(view.vm.model.email, 'example@example.org')
  assert.deepEqual(view.session.redirects, [])
})

test('forgot password fails closed, validates email and native submit sends exactly one request', async (t) => {
  let enabled = false
  const pending = deferred()
  let calls = 0
  const view = await mountC4(
    t,
    'views/auth/ForgotPasswordPage.vue',
    {
      config: async () => ({ password_reset_enabled: enabled }),
      forgotPassword: () => {
        calls++
        return pending.promise
      },
    },
    'model,submit,loadConfig,loading,sent',
  )
  view.vm.model.email = 'example@example.org'
  await view.vm.submit()
  assert.equal(calls, 0)
  enabled = true
  await view.vm.loadConfig()
  await settle()
  view.vm.model.email = 'invalid'
  await settle()
  await view.vm.submit()
  assert.equal(calls, 0)
  assert.equal(view.invalid().length, 1)
  view.vm.model.email = 'example@example.org'
  await settle()
  const form = find(view.tree, (n) => n.type === 'form')[0]
  await submit(form)
  assert.equal(calls, 1)
  await submit(form)
  assert.equal(calls, 1)
  pending.resolve({ reset_token: null })
  await settle()
  assert.equal(view.vm.sent, true)
  assert.equal(view.vm.loading, false)
})
