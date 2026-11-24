import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from '../../../../testing/view-harness.mjs'

const entry = 'views/data-integration/mapping/components/ExtractionSuggestions.vue'
const expose =
  'generate,apply,discard,toggle,items,selected,loading,validating,busyId,error,notice,auth,matchedEvidence'
async function suggestions(t, api, props, role = 'EDITOR') {
  const view = await mount(
    entry,
    { '@/api/ai': { aiApi: api, suggestionPayloadLines: () => [] } },
    expose,
    '/',
    undefined,
    role,
    {
      kind: 'DOCUMENT_FACTS',
      title: 'Suggestions',
      targetId: 1,
      text: 'original evidence',
      ...props,
    },
  )
  t.after(view.stop)
  return view
}

test('invalid AI source context makes zero generation or fact writes', async (t) => {
  const writes = []
  const { vm } = await suggestions(
    t,
    {
      extractDocument: async () => writes.push('generate'),
      apply: async () => writes.push('apply'),
    },
    { text: '', reviewOnly: true, validateContext: async () => false },
  )
  await vm.generate()
  vm.selected = [1]
  await vm.apply(1)
  assert.deepEqual(writes, [])
  assert.equal(vm.validating, false)
  assert.equal(vm.loading, false)
})

test('AI context validation prevents duplicate generation and role downgrade prevents writing', async (t) => {
  const validation = deferred()
  const writes = []
  const { vm } = await suggestions(
    t,
    { extractDocument: async () => writes.push('generate') },
    { validateContext: () => validation.promise },
  )
  const pending = vm.generate()
  await settle()
  assert.equal(vm.validating, true)
  await vm.generate()
  vm.auth.user.role = 'VIEWER'
  validation.resolve(true)
  await pending
  assert.deepEqual(writes, [])
})

test('AI generation blocks applying stale suggestions and review-only never persists facts', async (t) => {
  const generating = deferred()
  const writes = []
  const { vm } = await suggestions(
    t,
    {
      extractDocument: () => generating.promise,
      apply: async (id) => writes.push(['apply', id]),
      discard: async (id) => writes.push(['discard', id]),
    },
    { reviewOnly: true },
  )
  vm.items = [{ id: 1, title: 'Old suggestion' }]
  vm.selected = [1]
  const pending = vm.generate()
  await vm.apply(1)
  await vm.discard(1)
  vm.toggle(1)
  assert.deepEqual(vm.selected, [1])
  assert.deepEqual(writes, [])
  generating.resolve([
    { id: 2, title: 'New suggestion', payload: { evidence: 'original evidence' } },
  ])
  await pending
  assert.equal(vm.matchedEvidence(vm.items[0]), 'original evidence')
  vm.toggle(2)
  await vm.apply(2)
  assert.deepEqual(writes, [])
})

test('fusion editor keeps numeric zero for validation and clears stale display on external null', async (t) => {
  const updates = []
  const { vm, stop } = await mount(
    'views/data-integration/mapping/components/FusionPolicyEditor.vue',
    {},
    'priority,nullPolicy,conflictPolicy,update',
    '/',
    undefined,
    'EDITOR',
    {
      modelValue: { priority: 1, null_policy: 'KEEP', conflict_policy: 'PRIORITY' },
      'onUpdate:modelValue': (value) => updates.push(value),
    },
  )
  t.after(stop)
  vm.priority = 0
  vm.update()
  const internal = updates.at(-1)
  assert.equal(internal.priority, 0)
  assert.equal(internal.null_policy, 'KEEP')
  vm.$.props.modelValue = null
  await settle()
  assert.equal(vm.priority, null)
  assert.equal(vm.nullPolicy, null)
  assert.equal(vm.conflictPolicy, null)
})
