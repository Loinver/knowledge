import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from '../../../../testing/view-harness.mjs'

const failure = { code: 'KG.INTERNAL_ERROR' }
const result = (id, total = 61) => ({ items: [{ id }], total })

// Exercise the actual page script and watchers. Only API completion and the token
// event source are controlled; aborted requests deliberately remain completable.
export function queryIsolationTests(config) {
  async function setup(t) {
    const requests = []
    const listeners = new Set()
    let session = 'first-session'
    const read = (params, signal) => {
      const request = { ...deferred(), params, signal }
      requests.push(request)
      return request.promise
    }
    const ctx = await mount(
      config.entry,
      {
        '@/api/auth': { authApi: {} },
        [config.apiModule]: {
          [config.apiName]: { defaults: async () => [], [config.method]: read },
        },
        '@/api/tokens': {
          getSessionGeneration: () => session,
          getAccessToken: () => 'fixture-token',
          hasSession: () => true,
          clearTokens() {},
          storeTokens: () => true,
          subscribeTokens: (listener) => {
            listeners.add(listener)
            return () => listeners.delete(listener)
          },
        },
      },
      `items,total,loading,error,page,load,${config.expose},actor: useQueryTestAuth()`,
      '/',
      (source) =>
        source.replace(
          '<script setup lang="ts">',
          '<script setup lang="ts">\nimport { useAuthStore as useQueryTestAuth } from "@/stores/auth"',
        ),
      'ADMIN',
    )
    let stopped = false
    const stop = () => {
      if (!stopped) ctx.stop()
      stopped = true
    }
    t.after(stop)
    const last = () => requests.at(-1)
    const submit = async (q) => {
      ctx.vm[config.draft] = q
      void ctx.vm[config.submit]()
      await settle()
    }
    await submit('alpha')
    assert.equal(last().params.q, 'alpha')
    assert.equal(last().params.page_size, 20)
    last().resolve(result('alpha'))
    await settle()
    return {
      ...ctx,
      stop,
      requests,
      last,
      submit,
      tokens: (next = session) => {
        session = next
        for (const listener of [...listeners]) listener()
      },
    }
  }

  const snapshot = (ctx, id = 'alpha', total = 61) => {
    assert.deepEqual(
      ctx.vm.items.map((row) => row.id),
      id === null ? [] : [id],
    )
    assert.equal(ctx.vm.total, total)
  }
  const empty = (ctx) => snapshot(ctx, null, 0)

  test(`${config.name}: test_same_query_failure_retains_snapshot_and_draft_is_not_a_query`, async (t) => {
    const ctx = await setup(t)
    const before = ctx.requests.length
    ctx.vm[config.draft] = 'unsubmitted draft'
    await settle()
    snapshot(ctx)
    assert.equal(ctx.requests.length, before)
    const pending = ctx.vm.load()
    assert.equal(ctx.last().params.q, 'alpha')
    snapshot(ctx)
    ctx.last().reject(failure)
    await pending
    snapshot(ctx)
    assert.ok(ctx.vm.error)
    assert.equal(ctx.vm.loading, false)
    const retry = ctx.vm.load()
    snapshot(ctx)
    assert.equal(ctx.vm.error, '')
    ctx.last().resolve(result('fresh-alpha', 42))
    await retry
    snapshot(ctx, 'fresh-alpha', 42)
  })

  test(`${config.name}: test_changed_query_failure_cannot_show_previous_rows_or_total`, async (t) => {
    const ctx = await setup(t)
    ctx.vm[config.draft] = ' beta '
    void ctx.vm[config.submit]()
    empty(ctx)
    await settle()
    assert.equal(ctx.last().params.q, 'beta')
    assert.equal(ctx.vm.loading, true)
    ctx.last().reject(failure)
    await settle()
    empty(ctx)
    assert.ok(ctx.vm.error)
    assert.equal(ctx.vm.loading, false)
    const retry = ctx.vm.load()
    ctx.last().resolve({ items: [], total: 0 })
    await retry
    empty(ctx)
    assert.equal(ctx.vm.error, '')
  })

  test(`${config.name}: test_page_and_each_filter_have_independent_snapshots`, async (t) => {
    const ctx = await setup(t)
    const changes = [{ field: 'page', value: 2, key: 'page', expected: 2 }, ...config.filters]
    for (const change of changes) {
      ctx.vm[change.field] = change.value
      empty(ctx)
      if (config.manual) {
        if (change.field === 'page') void ctx.vm.load()
        else void ctx.vm[config.submit]()
      }
      await settle()
      assert.equal(ctx.last().params[change.key], change.expected, change.key)
      assert.equal(ctx.last().params.page_size, 20)
      assert.equal(ctx.vm.loading, true)
      ctx.last().reject(failure)
      await settle()
      empty(ctx)
      assert.ok(ctx.vm.error)
      const retry = ctx.vm.load()
      ctx.last().resolve(result('current-filter'))
      await retry
      snapshot(ctx, 'current-filter')
    }
  })

  for (const outcome of ['resolve', 'reject']) {
    test(`${config.name}: test_late_${outcome}_cannot_change_new_rows_error_or_loading`, async (t) => {
      const ctx = await setup(t)
      const first = ctx.vm.load()
      const stalePending = ctx.last()
      const second = ctx.vm.load()
      const staleSettled = ctx.last()
      await ctx.submit('beta')
      empty(ctx)
      const current = ctx.last()
      stalePending[outcome](outcome === 'resolve' ? result('stale') : failure)
      await first
      empty(ctx)
      assert.equal(ctx.vm.loading, true)
      assert.equal(ctx.vm.error, '')
      current.resolve(result('beta', 7))
      await settle()
      staleSettled[outcome](outcome === 'resolve' ? result('stale') : failure)
      await second
      snapshot(ctx, 'beta', 7)
      assert.equal(ctx.vm.error, '')
      assert.equal(ctx.vm.loading, false)
    })
  }

  test(`${config.name}: test_query_round_trip_does_not_revive_old_request_or_snapshot`, async (t) => {
    const ctx = await setup(t)
    const old = ctx.vm.load()
    const stale = ctx.last()
    await ctx.submit('beta')
    await ctx.submit('alpha')
    empty(ctx)
    stale.resolve(result('old-alpha'))
    await old
    empty(ctx)
    assert.equal(ctx.vm.loading, true)
    ctx.last().reject(failure)
    await settle()
    empty(ctx)
    assert.equal(ctx.vm.loading, false)
  })

  test(`${config.name}: test_actor_role_status_and_session_invalidate_same_query`, async (t) => {
    const ctx = await setup(t)
    const beforeRefresh = ctx.requests.length
    ctx.tokens()
    await settle()
    snapshot(ctx)
    assert.equal(ctx.requests.length, beforeRefresh, 'ordinary token refresh keeps ownership')
    for (const change of [
      () => (ctx.vm.actor.user.id = 'another-actor'),
      () => (ctx.vm.actor.user.status = 'DISABLED'),
      () => (ctx.vm.actor.user.role = 'VIEWER'),
      () => ctx.tokens('second-session'),
    ]) {
      const originalActor = { ...ctx.vm.actor.user }
      const old = ctx.vm.load()
      const stale = ctx.last()
      const before = ctx.requests.length
      change()
      empty(ctx)
      assert.equal(ctx.vm.error, '')
      await settle()
      stale.reject(failure)
      await old
      empty(ctx)
      assert.equal(ctx.vm.error, '')
      assert.equal(ctx.vm.loading, ctx.requests.length > before)
      // A permitted identity is restored independently of the expired request.
      ctx.vm.actor.user = {
        ...originalActor,
        id: 'restored-actor',
        role: 'ADMIN',
        status: 'ACTIVE',
      }
      await settle()
      empty(ctx)
      ctx.last().resolve(result('restored'))
      await settle()
      snapshot(ctx, 'restored')
    }
  })

  test(`${config.name}: test_unmount_discards_pending_completion_and_token_events`, async (t) => {
    const ctx = await setup(t)
    const pending = ctx.vm.load()
    const request = ctx.last()
    ctx.stop()
    const state = {
      items: ctx.vm.items,
      total: ctx.vm.total,
      error: ctx.vm.error,
      loading: ctx.vm.loading,
    }
    request.resolve(result('after-unmount'))
    await pending
    assert.deepEqual(
      { items: ctx.vm.items, total: ctx.vm.total, error: ctx.vm.error, loading: ctx.vm.loading },
      state,
    )
    const count = ctx.requests.length
    ctx.tokens('after-unmount')
    await settle()
    assert.equal(ctx.requests.length, count)
  })
}
