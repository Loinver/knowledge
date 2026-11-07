import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from '../../__tests__/view-harness.mjs'

test('import preview cannot authorize content edited while its request is pending', async (t) => {
  const first = deferred()
  const calls = []
  const ctx = await mount(
    'views/governance/components/OntologyRestore.vue',
    {
      '@/api/ontology-restore': {
        ontologyRestoreApi: {
          preview: (payload, signal) => {
            calls.push({ payload, signal })
            return first.promise
          },
        },
      },
    },
    'content,format,preview,loading,error,inspect',
  )
  t.after(ctx.stop)
  ctx.vm.content = 'original RDF'
  const pending = ctx.vm.inspect()
  assert.equal(ctx.vm.loading, true)
  ctx.vm.content = 'changed RDF'
  assert.equal(calls[0].signal.aborted, true)
  first.resolve({ can_apply: true, preview_digest: 'original' })
  await pending
  assert.equal(ctx.vm.preview, null)
  assert.equal(ctx.vm.loading, false)
})

test('import file read cannot replace newer content and oversized files are refused', async (t) => {
  const fileRead = deferred()
  const ctx = await mount(
    'views/governance/components/OntologyRestore.vue',
    { '@/api/ontology-restore': { ontologyRestoreApi: {} } },
    'content,format,preview,error,loadFile',
  )
  t.after(ctx.stop)
  const pending = ctx.vm.loadFile({
    target: { files: [{ size: 12, name: 'old.ttl', text: () => fileRead.promise }] },
  })
  ctx.vm.content = 'newer'
  fileRead.resolve('older')
  await pending
  assert.equal(ctx.vm.content, 'newer')
  await ctx.vm.loadFile({
    target: { files: [{ size: 65537, text: () => assert.fail('must not read oversized file') }] },
  })
  assert.match(ctx.vm.error, /64 KiB/)
  assert.equal(ctx.vm.preview, null)
})

test('restore applies only the reviewed payload once and requires a new preview after failure', async (t) => {
  const request = deferred()
  const calls = []
  const ctx = await mount(
    'views/governance/components/OntologyRestore.vue',
    {
      '@/api/ontology-restore': {
        ontologyRestoreApi: {
          apply: (payload) => {
            calls.push(payload)
            return request.promise
          },
        },
      },
    },
    'content,format,preview,applying,restored,error,apply',
  )
  t.after(ctx.stop)
  ctx.vm.content = 'reviewed RDF'
  await ctx.vm.apply()
  assert.equal(calls.length, 0)
  ctx.vm.preview = { can_apply: true, preview_digest: 'digest' }
  const pending = ctx.vm.apply()
  await ctx.vm.apply()
  assert.deepEqual(calls, [{ format: 'turtle', content: 'reviewed RDF', preview_digest: 'digest' }])
  assert.equal(ctx.vm.applying, true)
  request.reject({ code: 'KG.REVISION_CONFLICT' })
  await pending
  assert.equal(ctx.vm.preview, null)
  assert.equal(ctx.vm.restored, null)
  assert.match(ctx.vm.error, /KG.REVISION_CONFLICT/)
  assert.equal(ctx.vm.applying, false)
  await ctx.vm.apply()
  assert.equal(calls.length, 1)
})

test('frozen detail requests stay bound to resource and ontology revision', async (t) => {
  const first = deferred()
  const obsolete = deferred()
  const calls = []
  const ctx = await mount(
    'views/governance/components/OntologyHistory.vue',
    {
      '@/api/ontology-history': {
        ontologyHistoryApi: {
          contents: async (ontologyId, revision) => ({
            ontology_id: ontologyId,
            revision,
            resources: [],
            rules: [],
          }),
          resource: (ontologyId, revision, id, signal) => {
            calls.push({ ontologyId, revision, id, signal })
            return id === 1
              ? first.promise
              : id === 3
                ? obsolete.promise
                : Promise.resolve({ resource_id: 2 })
          },
        },
      },
    },
    'props,resource,rule,contents,detailLoading,open',
    '/',
    (source) =>
      source.replace(
        'defineProps<{ ontologyId: number; revision: number }>()',
        'ref({ ontologyId: 10, revision: 1 }).value',
      ),
  )
  t.after(ctx.stop)
  const pending = ctx.vm.open('resource', 1)
  await ctx.vm.open('resource', 2)
  assert.equal(calls[0].signal.aborted, true)
  first.resolve({ resource_id: 1 })
  await pending
  assert.equal(ctx.vm.resource.resource_id, 2)
  const late = ctx.vm.open('resource', 3)
  ctx.vm.props.revision = 2
  await settle()
  assert.equal(calls[2].signal.aborted, true)
  obsolete.resolve({ resource_id: 3 })
  await late
  assert.equal(ctx.vm.resource, null)
  assert.equal(ctx.vm.contents.revision, 2)
})
