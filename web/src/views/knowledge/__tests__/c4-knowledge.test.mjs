import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from '../../../testing/view-harness.mjs'

const base = (id) => ({ id, name: `Base ${id}`, revision: 1, archived: false })
const searchResult = (q) => ({
  query: q,
  items: Array.from({ length: 21 }, (_, i) => ({ chunk_id: `chunk-${i}` })),
  total_matches: 21,
})
const apiStub = (api) => ({
  '@/api/knowledge': {
    knowledgeApi: {
      get: async (id) => base(id),
      capabilities: async () => ({ chat_configured: false, embedding_configured: false }),
      ...api,
    },
  },
})

test('same-query failure retains accepted hits and page, but a new query cannot reuse them', async (t) => {
  let fail = false
  const ctx = await mount(
    'views/knowledge/KnowledgeSearchPage.vue',
    apiStub({
      search: async (_id, payload) => {
        if (fail) throw { code: 'KG.INVALID_REQUEST' }
        return searchResult(payload.q)
      },
    }),
    'current,data,error,reload,page,hits,q',
    '/entities/1?q=accepted&page=2',
  )
  t.after(ctx.stop)
  assert.equal(ctx.vm.page, 2)
  const accepted = ctx.vm.current
  fail = true
  ctx.vm.reload()
  await settle()
  assert.equal(ctx.vm.data, null)
  assert.equal(ctx.vm.current, accepted)
  assert.equal(ctx.vm.page, 2)
  assert.equal(ctx.vm.hits[0].chunk_id, 'chunk-10')
  assert.notEqual(ctx.vm.error, '')
  await ctx.router.push('/entities/1?q=different')
  await settle()
  assert.equal(ctx.vm.current, null)
  assert.equal(ctx.vm.q, 'different')
})

test('base validation blocks invalid writes; failure retains the draft and duplicate submissions send once', async (t) => {
  const write = deferred()
  const calls = []
  const ctx = await mount(
    'views/knowledge/components/BaseEditor.vue',
    apiStub({
      create: (payload, signal) => {
        calls.push({ payload, signal })
        return write.promise
      },
    }),
    'form,formRef,save,open,busy,error',
    '/',
    undefined,
    'EDITOR',
    { show: true },
  )
  t.after(ctx.stop)
  ctx.vm.formRef = {
    validate: async () => {
      throw new Error('FORM_INVALID')
    },
  }
  await ctx.vm.save()
  assert.equal(calls.length, 0)
  ctx.vm.form = { name: ' accepted name ', description: 'draft description' }
  ctx.vm.formRef = { validate: async () => {} }
  const pending = ctx.vm.save()
  await settle()
  await ctx.vm.save()
  assert.equal(calls.length, 1)
  assert.equal(calls[0].payload.name, 'accepted name')
  write.reject({ code: 'KG.REVISION_CONFLICT' })
  await pending
  assert.equal(ctx.vm.open, true)
  assert.equal(ctx.vm.form.description, 'draft description')
  assert.notEqual(ctx.vm.error, '')
  assert.equal(ctx.vm.busy, false)
})

test('a base save cannot close a reopened editor or accept completion after permission loss', async (t) => {
  const calls = []
  const ctx = await mount(
    'views/knowledge/components/BaseEditor.vue',
    apiStub({
      create: (_payload, signal) => {
        const call = { ...deferred(), signal }
        calls.push(call)
        return call.promise
      },
    }),
    'form,formRef,save,open,busy,error,auth',
    '/',
    undefined,
    'EDITOR',
    { show: true },
  )
  t.after(ctx.stop)
  ctx.vm.formRef = { validate: async () => {} }
  ctx.vm.form.name = 'first'
  const old = ctx.vm.save()
  await settle()
  ctx.vm.open = false
  ctx.vm.open = true
  ctx.vm.form.name = 'new draft'
  assert.equal(calls[0].signal.aborted, true)
  calls[0].resolve(base(1))
  await old
  assert.equal(ctx.vm.open, true)
  assert.equal(ctx.vm.form.name, 'new draft')
  const newer = ctx.vm.save()
  await settle()
  ctx.vm.auth.user.role = 'VIEWER'
  assert.equal(calls[1].signal.aborted, true)
  calls[1].resolve(base(2))
  await newer
  assert.equal(ctx.vm.open, true)
  assert.equal(ctx.vm.busy, false)
  await ctx.vm.save()
  assert.equal(calls.length, 2)
})

test('permission revoked during field validation prevents the base request', async (t) => {
  let writes = 0
  const validation = deferred()
  const ctx = await mount(
    'views/knowledge/components/BaseEditor.vue',
    apiStub({
      create: async () => {
        writes++
        return base(1)
      },
    }),
    'form,formRef,save,auth,open',
    '/',
    undefined,
    'EDITOR',
    { show: true },
  )
  t.after(ctx.stop)
  ctx.vm.form.name = 'valid'
  ctx.vm.formRef = { validate: () => validation.promise }
  const pending = ctx.vm.save()
  ctx.vm.auth.user.role = 'VIEWER'
  validation.resolve()
  await pending
  assert.equal(writes, 0)
  assert.equal(ctx.vm.open, true)
})
