import assert from 'node:assert/strict'
import { test } from 'node:test'

import { compile, deferred, mount, settle } from '../../__tests__/view-harness.mjs'

const capabilities = {
  chat_configured: false,
  embedding_configured: false,
  supported_formats: ['txt', 'md', 'csv'],
  max_file_bytes: 2097152,
  max_documents_per_base: 100,
  max_chunks_per_document: 2000,
  max_chunks_per_base: 10000,
}
const base = (id) => ({ id, name: `Base ${id}`, revision: 1, archived: false, processing_count: 0 })
const search = (query) => ({
  query,
  items: [],
  total_matches: 0,
  coverage: { total_documents: 0 },
  ranking_version: 'test',
})
const stubs = (api) => ({
  '@/api/knowledge': {
    knowledgeApi: { capabilities: async () => capabilities, get: async (id) => base(id), ...api },
  },
})
const withoutCss = (source) => source.replace("import './knowledge.css'", '')

test('late query success and failure cannot replace the active search', async (t) => {
  const requests = []
  const ctx = await mount(
    'views/knowledge/KnowledgeSearch.vue',
    stubs({
      search: (id, payload, signal) => {
        const request = { ...deferred(), id, payload, signal }
        requests.push(request)
        return request.promise
      },
    }),
    'data,error,loading,q',
    '/entities/1?q=old',
    withoutCss,
  )
  t.after(ctx.stop)
  await ctx.router.push('/entities/2?q=new')
  await settle()
  assert.equal(requests.length, 2)
  assert.equal(requests[0].signal.aborted, true)
  requests[1].resolve(search('new'))
  await settle()
  requests[0].reject({ code: 'KG.LLM_UNAVAILABLE', params: { reason: 'model_timeout' } })
  await settle()
  assert.equal(ctx.vm.data.retrieval.query, 'new')
  assert.equal(ctx.vm.error, '')
  assert.equal(ctx.vm.loading, false)
})

test('opening evidence and changing result pages retain results and unsent query text', async (t) => {
  let reads = 0
  const ctx = await mount(
    'views/knowledge/KnowledgeSearch.vue',
    stubs({
      search: async (_id, payload) => {
        reads++
        return search(payload.q)
      },
    }),
    'data,q,mode',
    '/entities/1?q=accepted&mode=KEYWORD',
    withoutCss,
  )
  t.after(ctx.stop)
  const original = ctx.vm.data
  ctx.vm.q = 'draft question'
  await ctx.router.push('/entities/1?q=accepted&mode=KEYWORD&evidence=chunk&page=2')
  await settle()
  assert.equal(reads, 1)
  assert.equal(ctx.vm.data, original)
  assert.equal(ctx.vm.q, 'draft question')
  await ctx.router.push('/entities/1?q=accepted&mode=KEYWORD&page=2')
  await settle()
  assert.equal(reads, 1)
  assert.equal(ctx.vm.q, 'draft question')
})

test('model failures show their explicit reason and cannot become empty successful results', async (t) => {
  const ctx = await mount(
    'views/knowledge/KnowledgeSearch.vue',
    stubs({
      search: async () => {
        throw { code: 'KG.LLM_UNAVAILABLE', params: { reason: 'model_rate_or_quota_limit' } }
      },
    }),
    'data,error,loading',
    '/entities/1?q=test&mode=SEMANTIC',
    withoutCss,
  )
  t.after(ctx.stop)
  assert.equal(ctx.vm.data, null)
  assert.match(ctx.vm.error, /rate or quota limit/)
  assert.equal(ctx.vm.loading, false)
})

test('explicit search cancellation aborts the request and retains the editable query', async (t) => {
  const pending = deferred()
  let signal
  const ctx = await mount(
    'views/knowledge/KnowledgeSearch.vue',
    stubs({
      search: (_id, _payload, requestSignal) => {
        signal = requestSignal
        return pending.promise
      },
    }),
    'data,error,loading,q,cancel,cancelled',
    '/entities/1?q=long-running',
    withoutCss,
  )
  t.after(ctx.stop)
  ctx.vm.cancel()
  assert.equal(signal.aborted, true)
  assert.equal(ctx.vm.q, 'long-running')
  pending.resolve(search('late'))
  await settle()
  assert.equal(ctx.vm.data, null)
  assert.equal(ctx.vm.error, '')
  assert.equal(ctx.vm.loading, false)
  assert.equal(ctx.vm.cancelled, true)
})

test('VIEWER may read documents but mutation handlers cannot archive or upload', async (t) => {
  let writes = 0
  const ctx = await mount(
    'views/knowledge/KnowledgeBaseDetail.vue',
    stubs({
      documents: async () => ({ items: [], total: 0 }),
      archive: async () => {
        writes++
        return base(1)
      },
      upload: async () => {
        writes++
        return {}
      },
    }),
    'data,canWrite,canEdit,archive,upload',
    '/entities/1',
    withoutCss,
    'VIEWER',
  )
  t.after(ctx.stop)
  assert.equal(ctx.vm.data.base.id, 1)
  assert.equal(ctx.vm.canWrite, false)
  assert.equal(ctx.vm.canEdit, false)
  await ctx.vm.archive()
  await ctx.vm.upload({ target: { files: [{ name: 'test.txt', size: 12 }] } })
  assert.equal(writes, 0)
})

test('polling preserves inputs and action errors and stops after completion', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let reads = 0
  let running = true
  const ctx = await mount(
    'views/knowledge/KnowledgeBaseDetail.vue',
    stubs({
      get: async (id) => ({ ...base(id), processing_count: running ? 1 : 0 }),
      documents: async () => {
        reads++
        return { items: [], total: 0 }
      },
      archive: async () => {
        throw { code: 'KG.REVISION_CONFLICT', params: {} }
      },
    }),
    'data,q,archive,actionError',
    '/entities/1',
    withoutCss,
  )
  t.after(ctx.stop)
  ctx.vm.q = 'unsent filename'
  await ctx.vm.archive()
  const actionError = ctx.vm.actionError
  assert.notEqual(actionError, '')
  t.mock.timers.tick(2000)
  await settle()
  assert.equal(reads, 2)
  assert.equal(ctx.vm.q, 'unsent filename')
  assert.equal(ctx.vm.actionError, actionError)
  running = false
  t.mock.timers.tick(2000)
  await settle()
  assert.equal(reads, 3)
  t.mock.timers.tick(10000)
  await settle()
  assert.equal(reads, 3)
})

test('pending writes are owned by the route object and polling cleans up on unmount', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const write = deferred()
  let reads = 0
  const ctx = await mount(
    'views/knowledge/KnowledgeBaseDetail.vue',
    stubs({
      get: async (id) => ({ ...base(id), processing_count: 1 }),
      documents: async () => {
        reads++
        return { items: [], total: 0 }
      },
      archive: async () => write.promise,
    }),
    'data,archive,busy,notice,actionError',
    '/entities/1',
    withoutCss,
  )
  const saving = ctx.vm.archive()
  await ctx.router.push('/entities/2')
  await settle()
  write.resolve({ ...base(1), archived: true })
  await saving
  await settle()
  assert.equal(ctx.vm.data.base.id, 2)
  assert.equal(ctx.vm.notice, '')
  assert.equal(ctx.vm.busy, false)
  const count = reads
  ctx.stop()
  t.mock.timers.tick(4000)
  await settle()
  assert.equal(reads, count)
})

test('polling is bounded even when a processing task never terminates', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let reads = 0
  const ctx = await mount(
    'views/knowledge/KnowledgeBaseDetail.vue',
    stubs({
      get: async (id) => ({ ...base(id), processing_count: 1 }),
      documents: async () => {
        reads++
        return { items: [], total: 0 }
      },
    }),
    'paused',
    '/entities/1',
    withoutCss,
  )
  t.after(ctx.stop)
  for (let index = 0; index < 150; index++) {
    t.mock.timers.tick(2000)
    await settle()
  }
  assert.equal(reads, 150)
  assert.equal(ctx.vm.paused, true)
})

test('Unicode source offsets preserve astral characters and source markup as text', async () => {
  const { mod, cleanup } = await compile('views/knowledge/composables/useKnowledge.ts')
  try {
    assert.deepEqual(mod.evidenceSegments('😀前文\n证据🧪<script>\n后文', 4, 15), [
      '😀前文\n',
      '证据🧪<script>',
      '\n后文',
    ])
    assert.deepEqual(mod.evidenceSegments('ab', -2, 100), ['', 'ab', ''])
    assert.equal(mod.positivePage('-3'), 1)
  } finally {
    cleanup()
  }
})
