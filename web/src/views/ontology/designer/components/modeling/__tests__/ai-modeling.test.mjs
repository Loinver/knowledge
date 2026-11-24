import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

import { effectScope, reactive, ref } from 'vue'

import { compile, deferred, settle } from '../../../../../../testing/view-harness.mjs'

const built = await compile('views/ontology/designer/components/modeling/useAiModeling.ts')
const { useAiModeling, parseCandidateEditor, pretty } = built.mod

test('all six program checks have accurate translated coverage labels', () => {
  for (const language of ['zh-CN', 'en-US']) {
    const locale = JSON.parse(
      readFileSync(new URL(`../../../../../../locales/${language}.json`, import.meta.url), 'utf8'),
    )
    for (const code of ['M01', 'M02', 'M03', 'M04', 'M05', 'M06'])
      assert.equal(typeof locale.modeling.checks[code], 'string', `${language}:${code}`)
    assert.match(locale.modeling.checks.M02, /TBox.*OWL2RL/)
    assert.match(locale.modeling.checks.M03, /SHACL/)
    assert.match(
      locale.modeling.checks.M06,
      language === 'zh-CN' ? /不代表业务实例/ : /not business instance/,
    )
  }
})
const candidate = () => ({
  schema_version: 'ontology-candidate/1.0',
  context_token: 'synthetic-context',
  profile_echo: 'BUSINESS',
  scope: {
    goal_i18n: { 'zh-CN': '虚构测试', 'en-US': null },
    out_of_scope_i18n: [],
    assumptions_i18n: [],
  },
  ontology_metadata: null,
  resources: [],
  axioms: [],
  constraints: [],
  questions: [],
})
const proposal = (id = 'p1', ontologyId = 1, revision = 1) => ({
  id,
  ontology_id: ontologyId,
  target_draft_id: `ontology:${ontologyId}:working`,
  base_edit_revision: 8,
  revision,
  state: 'READY',
  candidate: candidate(),
  candidate_digest: `digest-${revision}`,
  provenance: { model_version: 'synthetic-only' },
  sources: {},
  stale: false,
  validation: null,
})
const report = (id = 'p1', revision = 1) => ({
  id: `report-${revision}`,
  proposal_id: id,
  proposal_revision: revision,
  candidate_digest: `digest-${revision}`,
  context_fingerprint: 'context-fingerprint',
  compiled_plan_digest: 'plan-digest',
  compiler_version: 'compiler/1',
  checks: [{ check_code: 'M01', state: 'PASS', required: true, coverage: 'synthetic', params: {} }],
  blocking_questions: [],
  can_apply: true,
  plan: { digest: 'plan-digest', resources: [] },
})
const receipt = (pending) => ({
  application_id: 'synthetic-application',
  proposal_id: pending?.proposalId ?? 'p1',
  proposal_revision: pending?.proposalRevision ?? 1,
  state: 'APPLIED_TO_DRAFT',
  target_draft_id: pending?.payload.target_draft_id ?? 'ontology:1:working',
  before_edit_revision: 8,
  after_edit_revision: 9,
  candidate_to_resource: {},
  validation_report_id: 'report-1',
  audit_correlation_id: 'synthetic-audit',
})
const memoryStorage = () => {
  const data = new Map()
  return {
    data,
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
    removeItem: (key) => data.delete(key),
  }
}

async function model(t, overrides = {}, shared = {}) {
  const context = reactive({ ontologyId: 1, draftId: 'ontology:1:working', baseEditRevision: 8 })
  const identity = ref(shared.identity ?? randomUUID())
  const writable = ref(true)
  const applied = []
  let keyCount = 0
  const api = {
    capabilities: async () => ({
      protocol_version: 'ontology-modeling/1.0',
      supported_profiles: ['BUSINESS'],
      profile_version: 'business/1',
      chat_configured: true,
      draft_only: true,
      allowed_constructs: {},
    }),
    list: async () => ({ items: [], total: 0 }),
    get: async (id) => proposal(id, context.ontologyId),
    create: async () => proposal('generated', context.ontologyId),
    update: async (id, revision, payload) => ({
      ...proposal(id, context.ontologyId, revision + 1),
      candidate: JSON.parse(payload.candidate_json),
    }),
    validate: async (id, revision) => report(id, revision),
    apply: async () => receipt(),
    applicationByKey: async () => null,
    discard: async (id) => ({ ...proposal(id, context.ontologyId), state: 'DISCARDED' }),
    ...overrides,
  }
  const scope = effectScope()
  const storage = shared.storage ?? memoryStorage()
  const state = scope.run(() =>
    useAiModeling(() => context, {
      api,
      namespacesApi: {
        list: async () => [
          { id: 1, prefix: 'synthetic', iri: 'https://example.org/', protected: false },
          { id: 2, protected: true },
        ],
      },
      identity: () => identity.value,
      canWrite: () => writable.value,
      storage,
      makeKey: () => `synthetic-key-${String(++keyCount).padStart(16, '0')}`,
      t: (key) => key,
      toMessage: (cause) => cause?.code || 'network',
      onApplied: (result) => applied.push(result),
      confirmChange: () => true,
      validateGenerate: shared.validateGenerate,
      validateCandidate: shared.validateCandidate,
    }),
  )
  t.after(() => scope.stop())
  await settle()
  return { state, api, context, identity, writable, storage, applied, stop: () => scope.stop() }
}
function authorize(state) {
  state.text.value = 'Synthetic requirements'
  state.namespaceIds.value = [1]
  state.authorizeTransfer.value = true
}

test('form validation blocks duplicate generation and cannot write after target or input changes', async (t) => {
  const pending = deferred()
  const calls = []
  const ctx = await model(
    t,
    { create: async () => calls.push('create') },
    { validateGenerate: () => pending.promise },
  )
  authorize(ctx.state)
  const first = ctx.state.generate()
  assert.equal(ctx.state.validatingForm.value, true)
  assert.equal(ctx.state.busy.value, null)
  await ctx.state.generate()
  ctx.context.ontologyId = 2
  pending.resolve()
  await first
  assert.deepEqual(calls, [])
  assert.equal(ctx.state.validatingForm.value, false)
})

test('candidate form rejection retains edits and validation completion cannot save changed text', async (t) => {
  const pending = deferred()
  const calls = []
  let rejects = true
  const ctx = await model(
    t,
    { update: async () => calls.push('update') },
    {
      validateCandidate: () =>
        rejects ? Promise.reject(new Error('FORM_INVALID')) : pending.promise,
    },
  )
  await ctx.state.selectProposal('p1')
  ctx.state.candidateJson.value = '{"changed":true}'
  ctx.state.editNote.value = 'Reason'
  await ctx.state.saveCandidate()
  assert.equal(ctx.state.candidateJson.value, '{"changed":true}')
  assert.deepEqual(calls, [])
  rejects = false
  const saving = ctx.state.saveCandidate()
  assert.equal(ctx.state.validatingForm.value, true)
  ctx.state.candidateJson.value = '{"newer":true}'
  pending.resolve()
  await saving
  assert.deepEqual(calls, [])
  assert.equal(ctx.state.validatingForm.value, false)
})
async function reviewed(state) {
  await state.selectProposal('p1')
  await state.validate()
  state.acceptPlan(true)
}

test('generation requires configured model, namespace and explicit authorization; no unsupported profile fallback', async (t) => {
  const calls = []
  const ctx = await model(t, {
    create: async (payload) => {
      calls.push(payload)
      return proposal()
    },
  })
  ctx.state.text.value = 'Synthetic'
  ctx.state.namespaceIds.value = [1]
  await ctx.state.generate()
  assert.deepEqual(calls, [])
  ctx.state.authorizeTransfer.value = true
  ctx.state.capabilities.value.chat_configured = false
  await ctx.state.generate()
  ctx.state.capabilities.value.chat_configured = true
  ctx.state.namespaceIds.value = [2]
  await ctx.state.generate()
  assert.deepEqual(calls, [])
  ctx.state.namespaceIds.value = [1]
  ctx.state.excerpts.value = [
    { id: 'excluded', title: 'Private', text: 'Not authorized', authorized: false },
    { id: 'included', title: 'Fixture', text: 'Synthetic only', authorized: true },
  ]
  await ctx.state.generate()
  assert.equal(calls.length, 1)
  assert.equal(calls[0].authorize_model_transfer, true)
  assert.equal(calls[0].target_draft_id, 'ontology:1:working')
  assert.deepEqual(calls[0].excerpts, [
    { title: 'Fixture', text: 'Synthetic only', authorized: true },
  ])
})

for (const fail of [false, true]) {
  test(`target switch suppresses late generation ${fail ? 'failure' : 'success'} and new loading cleanup`, async (t) => {
    const first = deferred(),
      second = deferred()
    const ctx = await model(t, {
      create: (payload) => (payload.target_ontology_id === 1 ? first.promise : second.promise),
    })
    authorize(ctx.state)
    const generatingOld = ctx.state.generate()
    Object.assign(ctx.context, { ontologyId: 2, draftId: 'ontology:2:working' })
    await settle()
    authorize(ctx.state)
    const generatingNew = ctx.state.generate()
    if (fail) first.reject({ code: 'KG.LLM_UNAVAILABLE' })
    else first.resolve(proposal('old'))
    await generatingOld
    assert.equal(ctx.state.busy.value, 'generate')
    assert.equal(ctx.state.error.value, '')
    assert.equal(ctx.state.selected.value, null)
    second.resolve(proposal('new', 2))
    await generatingNew
    assert.equal(ctx.state.selected.value.id, 'new')
  })
}

test('latest proposal read wins when responses complete out of order', async (t) => {
  const first = deferred(),
    second = deferred()
  const ctx = await model(t, { get: (id) => (id === 'first' ? first.promise : second.promise) })
  const openingFirst = ctx.state.selectProposal('first'),
    openingSecond = ctx.state.selectProposal('second')
  second.resolve(proposal('second'))
  await openingSecond
  first.resolve(proposal('first'))
  await openingFirst
  assert.equal(ctx.state.selected.value.id, 'second')
})

test('JSON editor rejects duplicate keys including escaped keys and submits exact candidate_json original text', async (t) => {
  for (const text of [
    '{"x":1,"x":2}',
    '{"x":1,"\\u0078":2}',
    '{"a":[{"x":1,"x":2}]}',
    '[]',
    'null',
  ])
    assert.throws(() => parseCandidateEditor(text))
  assert.deepEqual(parseCandidateEditor('{"a":{"x":1},"b":{"x":2}}'), { a: { x: 1 }, b: { x: 2 } })
  const writes = []
  const ctx = await model(t, {
    update: async (...args) => {
      writes.push(args)
      throw { code: 'KG.CANDIDATE_INVALID_STRUCTURE' }
    },
  })
  await ctx.state.selectProposal('p1')
  const original = ctx.state.selected.value
  ctx.state.candidateJson.value = '{"x":1,"x":2}'
  ctx.state.editNote.value = 'Synthetic note'
  await ctx.state.saveCandidate()
  assert.deepEqual(writes, [])
  const raw = '{\n "schema_version": "ontology-candidate/1.0", "changed": true\n}'
  ctx.state.candidateJson.value = raw
  await ctx.state.saveCandidate()
  assert.equal(writes[0][2].candidate_json, raw)
  assert.equal('candidate' in writes[0][2], false)
  assert.equal(ctx.state.candidateJson.value, raw)
  assert.equal(ctx.state.selected.value, original)
  assert.equal(ctx.state.error.value, 'KG.CANDIDATE_INVALID_STRUCTURE')
})

test('candidate edits invalidate validation and exact plan confirmation', async (t) => {
  const ctx = await model(t)
  await reviewed(ctx.state)
  assert.equal(ctx.state.canApply.value, true)
  ctx.state.candidateJson.value += ' '
  assert.equal(ctx.state.confirmedDigest.value, '')
  assert.equal(ctx.state.canApply.value, false)
  ctx.state.candidateJson.value = pretty(ctx.state.selected.value.candidate)
  assert.equal(ctx.state.canApply.value, false)
})

test('late validation cannot authorize a changed candidate or target', async (t) => {
  const pending = deferred()
  const ctx = await model(t, { validate: () => pending.promise })
  await ctx.state.selectProposal('p1')
  const validating = ctx.state.validate()
  ctx.state.candidateJson.value += ' '
  pending.resolve(report())
  await validating
  assert.equal(ctx.state.validation.value, null)
  assert.equal(ctx.state.canApply.value, false)
})

test('required NOT_RUN or VIOLATION, blocking questions and stale revisions cannot apply', async (t) => {
  const ctx = await model(t)
  await ctx.state.selectProposal('p1')
  for (const state of ['NOT_RUN', 'VIOLATION']) {
    ctx.api.validate = async () => ({ ...report(), checks: [{ ...report().checks[0], state }] })
    await ctx.state.validate()
    ctx.state.acceptPlan(true)
    assert.equal(ctx.state.canApply.value, false)
  }
  ctx.api.validate = async () => ({ ...report(), blocking_questions: ['q1'] })
  await ctx.state.validate()
  ctx.state.acceptPlan(true)
  assert.equal(ctx.state.canApply.value, false)
  ctx.api.validate = async () => report('p1', 2)
  await ctx.state.validate()
  ctx.state.acceptPlan(true)
  assert.equal(ctx.state.canApply.value, false)
  Object.assign(ctx.context, { baseEditRevision: 9 })
  assert.equal(ctx.state.selected.value, null)
  assert.equal(ctx.state.authorizeTransfer.value, false)
})

test('apply requires explicit matching plan digest and guards duplicate clicks', async (t) => {
  const pending = deferred(),
    calls = []
  const ctx = await model(t, {
    apply: (...args) => {
      calls.push(args)
      return pending.promise
    },
  })
  await ctx.state.selectProposal('p1')
  await ctx.state.validate()
  await ctx.state.apply()
  assert.deepEqual(calls, [])
  ctx.state.acceptPlan(true)
  const applying = ctx.state.apply()
  await ctx.state.apply()
  assert.equal(calls.length, 1)
  assert.equal(calls[0][2].confirmation.accepted_plan_digest, 'plan-digest')
  assert.equal(calls[0][2].compiled_plan_digest, 'plan-digest')
  pending.resolve(receipt(ctx.state.pendingApplication.value))
  await applying
  assert.equal(ctx.applied.length, 1)
  assert.equal(ctx.state.pendingApplication.value, null)
  assert.equal(ctx.state.selected.value.state, 'APPLIED')
})

test('unknown apply outcome survives closing; null query retains original key and explicit retry uses identical request', async (t) => {
  const calls = [],
    storage = memoryStorage(),
    identity = randomUUID()
  const ctx = await model(
    t,
    {
      apply: async (...args) => {
        calls.push(args)
        throw { code: '', status: 502 }
      },
    },
    { storage, identity },
  )
  await reviewed(ctx.state)
  await ctx.state.apply()
  const original = JSON.parse(JSON.stringify(ctx.state.pendingApplication.value))
  ctx.stop()
  const reopened = await model(
    t,
    {
      applicationByKey: async (key) => {
        assert.equal(key, original.key)
        return null
      },
      apply: async (...args) => {
        calls.push(args)
        return receipt(original)
      },
    },
    { storage, identity },
  )
  assert.equal(reopened.state.pendingApplication.value.key, original.key)
  await reopened.state.queryApplication()
  assert.equal(reopened.state.notice.value, 'modeling.outcomePending')
  assert.equal(reopened.state.pendingApplication.value.key, original.key)
  await reopened.state.selectProposal('p1')
  await reopened.state.retryApplication()
  assert.deepEqual(calls[1], calls[0])
  assert.equal(reopened.applied.length, 1)
})

test('obsolete apply success cannot refresh another target and its original receipt remains queryable', async (t) => {
  const pending = deferred()
  const ctx = await model(t, { apply: () => pending.promise })
  await reviewed(ctx.state)
  const applying = ctx.state.apply()
  const original = JSON.parse(JSON.stringify(ctx.state.pendingApplication.value))
  Object.assign(ctx.context, { ontologyId: 2, draftId: 'ontology:2:working' })
  await settle()
  pending.resolve(receipt(original))
  await applying
  assert.deepEqual(ctx.applied, [])
  assert.equal(ctx.state.application.value, null)
  Object.assign(ctx.context, { ontologyId: 1, draftId: 'ontology:1:working' })
  await settle()
  assert.equal(ctx.state.pendingApplication.value.key, original.key)
  ctx.api.applicationByKey = async () => receipt(original)
  await ctx.state.queryApplication()
  assert.equal(ctx.applied.length, 1)
})

test('identity changes cannot query another actor receipt; viewer cannot generate or apply', async (t) => {
  const ctx = await model(t, {
    apply: async () => {
      throw { code: '', status: 0 }
    },
  })
  await reviewed(ctx.state)
  await ctx.state.apply()
  ctx.identity.value = randomUUID()
  await settle()
  assert.equal(ctx.state.pendingApplication.value, null)
  ctx.writable.value = false
  await settle()
  authorize(ctx.state)
  assert.equal(ctx.state.canGenerate.value, false)
  assert.equal(ctx.state.canApply.value, false)
})

test('unmount invalidates readers and prevents later public actions from starting new requests', async (t) => {
  const read = deferred(),
    calls = []
  const ctx = await model(t, {
    get: () => {
      calls.push('get')
      return read.promise
    },
    create: async () => {
      calls.push('create')
      return proposal()
    },
  })
  const opening = ctx.state.selectProposal('p1')
  ctx.stop()
  read.resolve(proposal())
  await opening
  authorize(ctx.state)
  await ctx.state.generate()
  await ctx.state.selectProposal('p1')
  assert.equal(ctx.state.selected.value, null)
  assert.deepEqual(calls, ['get'])
})

test('production API keeps route methods, payloads, revision headers and idempotency keys', async () => {
  const calls = []
  const http = Object.fromEntries(
    ['get', 'post', 'put'].map((method) => [
      method,
      async (...args) => {
        calls.push({ method, args })
        return { data: null }
      },
    ]),
  )
  const apiModule = await compile('api/ontology-modeling.ts', { '@/api/client': { http } })
  try {
    const api = apiModule.mod.ontologyModelingApi
    await api.capabilities()
    await api.list(1, 2)
    await api.get('p1')
    await api.create({ authorize_model_transfer: true }, 'synthetic-idempotency-key')
    await api.update('p1', 3, { candidate_json: '{}', note: 'Test' })
    await api.validate('p1', 3, 'candidate-digest')
    await api.apply('p1', 3, { compiled_plan_digest: 'digest' }, 'original-apply-key')
    await api.applicationByKey('original-apply-key')
    await api.discard('p1', 3)
    assert.equal(calls[1].args[1].params.ontology_id, 1)
    assert.equal(calls[1].args[1].params.page, 2)
    assert.equal(calls[4].args[0], '/ai/ontology-modeling/proposals/p1/candidate')
    assert.deepEqual(calls[4].args[2].headers, { 'If-Match': '3' })
    assert.deepEqual(calls[5].args[1], { candidate_digest: 'candidate-digest' })
    assert.deepEqual(calls[6].args[2].headers, {
      'If-Match': '3',
      'Idempotency-Key': 'original-apply-key',
    })
    assert.equal(calls[7].args[1].params.key, 'original-apply-key')
    assert.equal(calls[8].args[0], '/ai/ontology-modeling/proposals/p1/discard')
  } finally {
    apiModule.cleanup()
  }
})
