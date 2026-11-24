import assert from 'node:assert/strict'
import { test } from 'node:test'

import { effectScope, ref } from 'vue'

import { compile, deferred } from '../../testing/view-harness.mjs'

test('old success, failure and cleanup never affect a reopened editing session', async (t) => {
  const built = await compile('composables/useOwnedMutation.ts')
  t.after(built.cleanup)
  const scope = effectScope()
  t.after(() => scope.stop())
  const identity = ref('open:1:revision:7')
  const state = scope.run(() =>
    built.mod.useOwnedMutation(
      () => identity.value,
      (error) => error.code,
    ),
  )
  const first = deferred()
  let firstSignal
  const old = state.run((signal) => {
    firstSignal = signal
    return first.promise
  })
  identity.value = 'closed:1'
  identity.value = 'open:2:revision:9'
  assert.equal(firstSignal.aborted, true)
  const second = deferred()
  const fresh = state.run(() => second.promise)
  first.resolve({ id: 1, revision: 8 })
  assert.equal(await old, undefined)
  assert.equal(state.busy.value, true)
  assert.equal(state.error.value, '')
  second.resolve({ id: 2, revision: 10 })
  assert.deepEqual(await fresh, { id: 2, revision: 10 })
  assert.equal(state.busy.value, false)

  const lateFailure = deferred()
  const failed = state.run(() => lateFailure.promise)
  identity.value = 'open:3:revision:11'
  const pending = deferred()
  const current = state.run(() => pending.promise)
  lateFailure.reject({ code: 'KG.REVISION_CONFLICT' })
  assert.equal(await failed, undefined)
  assert.equal(state.error.value, '')
  assert.equal(state.busy.value, true)
  pending.resolve({ id: 3 })
  assert.deepEqual(await current, { id: 3 })
})

test('a duplicate submit sends one write; a current failure retains caller input', async (t) => {
  const built = await compile('composables/useOwnedMutation.ts')
  t.after(built.cleanup)
  const scope = effectScope()
  t.after(() => scope.stop())
  const draft = { limit: 0, enabled: false, name: 'Retained draft' }
  const state = scope.run(() =>
    built.mod.useOwnedMutation(
      () => 'session:1',
      (error) => error.code,
    ),
  )
  const response = deferred()
  let count = 0
  const write = () => {
    count++
    return response.promise
  }
  const first = state.run(write)
  assert.equal(await state.run(write), undefined)
  assert.equal(count, 1)
  response.reject({ code: 'KG.REVISION_CONFLICT' })
  assert.equal(await first, undefined)
  assert.equal(state.error.value, 'KG.REVISION_CONFLICT')
  assert.deepEqual(draft, { limit: 0, enabled: false, name: 'Retained draft' })
  assert.equal(state.busy.value, false)
})

test('unmount cancels ownership and a late response stays unaccepted', async (t) => {
  const built = await compile('composables/useOwnedMutation.ts')
  t.after(built.cleanup)
  const scope = effectScope()
  const state = scope.run(() => built.mod.useOwnedMutation(() => 'session:1', String))
  const response = deferred()
  let signal
  const pending = state.run((current) => {
    signal = current
    return response.promise
  })
  scope.stop()
  assert.equal(signal.aborted, true)
  response.resolve('late')
  assert.equal(await pending, undefined)
  assert.equal(state.busy.value, false)
})
