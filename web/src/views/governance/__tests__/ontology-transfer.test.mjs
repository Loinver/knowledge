import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from '../../__tests__/view-harness.mjs'

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
