import assert from 'node:assert/strict'
import { afterEach, beforeEach, test } from 'node:test'

import { deferred, mount, settle } from '../../__tests__/view-harness.mjs'

const rule = () => ({
  id: 1,
  revision: 3,
  identifier: 'SafetyRule',
  name_i18n: { 'zh-CN': '测试规则', 'en-US': 'Safety rule' },
  category: 'quality',
  source_kind: 'ENTERPRISE',
  source_reference: 'Policy 1',
  target_iri: 'https://example.org/Entity',
  severity: 'VIOLATION',
  language: 'SHACL',
  expression: 'original expression',
  execution: 'AUTO',
  positive_example: 'positive RDF',
  negative_example: 'negative RDF',
})
const template = (builtin = false) => ({
  id: 1,
  revision: 2,
  name: 'SafetyTemplate',
  label_i18n: { 'zh-CN': '测试模板', 'en-US': 'Safety template' },
  source: 'Policy 1',
  basis: 'Example domain',
  builtin,
  reference_count: 0,
  resources: [{ resource_id: 8, pinned_revision: 2 }],
})
const dictionary = () => ({
  id: 1,
  revision: 2,
  name: 'Status',
  label_i18n: { 'zh-CN': '状态', 'en-US': 'Status' },
  definition_i18n: { 'zh-CN': '状态定义', 'en-US': 'Status definition' },
  entries: [{ value: 'OPEN', label_i18n: { 'zh-CN': '开放', 'en-US': 'Open' } }],
})
const clone = (value) => JSON.parse(JSON.stringify(value))
const forbiddenCalls = []
const forbidden = (...args) => {
  forbiddenCalls.push(args)
  throw new Error('a read-only operation reached a write API')
}
beforeEach(() => {
  forbiddenCalls.length = 0
})
afterEach(() =>
  assert.equal(
    forbiddenCalls.length,
    0,
    'no forbidden API may be called, even if its rejection is caught',
  ),
)
const rulesStubs = (extra = {}) => ({
  '@/api/governance': {
    rulesApi: {
      list: async () => ({ items: [rule()], total: 1 }),
      get: async () => rule(),
      create: forbidden,
      update: forbidden,
      remove: forbidden,
      ...extra,
    },
  },
})
const templatesStubs = (item = template(), extra = {}) => ({
  '@/api/templates': {
    templatesApi: {
      list: async () => ({ items: [item], total: 1 }),
      get: async () => clone(item),
      resources: async () => [{ resource_id: 8, name: 'Entity', revisions: [1, 2, 3] }],
      ontologies: async () => [],
      create: forbidden,
      update: forbidden,
      copy: forbidden,
      fromOntology: forbidden,
      remove: forbidden,
      instantiate: forbidden,
      ...extra,
    },
  },
})

test('VIEWER can test saved rules but cannot create, update or delete them', async (t) => {
  const calls = []
  const ctx = await mount(
    'views/governance/GovernanceRules.vue',
    rulesStubs({
      test: async (item) => {
        calls.push(item)
        return { revision: 3, state: 'NOT_RUN' }
      },
    }),
    'canWrite,form,saved,showEditor,testResult,createRule,editRule,save,remove,runTest',
    '/',
    undefined,
    'VIEWER',
  )
  t.after(ctx.stop)
  assert.equal(ctx.vm.canWrite, false)
  ctx.vm.createRule()
  assert.equal(ctx.vm.showEditor, false)
  await ctx.vm.editRule(rule())
  await ctx.vm.runTest()
  assert.equal(calls.length, 1)
  assert.equal(ctx.vm.testResult.state, 'NOT_RUN')
  ctx.vm.form.expression = 'changed'
  await ctx.vm.save()
  await ctx.vm.remove()
  await ctx.vm.runTest()
  assert.equal(calls.length, 1, 'unsaved input cannot be tested as the saved revision')
})

test('rule expression and both examples invalidate results synchronously, including late responses', async (t) => {
  let response = Promise.resolve({ revision: 3, state: 'PASS' })
  const ctx = await mount(
    'views/governance/GovernanceRules.vue',
    rulesStubs({ test: () => response }),
    'form,testResult,editRule,runTest',
  )
  t.after(ctx.stop)
  for (const field of ['expression', 'positive_example', 'negative_example']) {
    await ctx.vm.editRule(rule())
    await ctx.vm.runTest()
    assert.equal(ctx.vm.testResult.state, 'PASS')
    ctx.vm.form[field] = `changed ${field}`
    assert.equal(ctx.vm.testResult, null)
    ctx.vm.form[field] = rule()[field]
    assert.equal(ctx.vm.testResult, null, 'reverting input must not revive old validation')
  }
  const request = deferred()
  response = request.promise
  const pending = ctx.vm.runTest()
  ctx.vm.form.positive_example = 'changed while pending'
  request.resolve({ revision: 3, state: 'PASS' })
  await pending
  assert.equal(ctx.vm.testResult, null)
})

test('rules retain all four backend test states without treating NOT_RUN or NA as PASS', async (t) => {
  let state = 'NOT_RUN'
  const ctx = await mount(
    'views/governance/GovernanceRules.vue',
    rulesStubs({ test: async () => ({ revision: 3, state }) }),
    'testResult,editRule,runTest',
  )
  t.after(ctx.stop)
  await ctx.vm.editRule(rule())
  for (state of ['NOT_RUN', 'NA', 'VIOLATION', 'PASS']) {
    await ctx.vm.runTest()
    assert.equal(ctx.vm.testResult.state, state)
  }
})

for (const role of ['EDITOR', 'ADMIN']) {
  test(`${role} can save a rule and revision conflicts preserve local input`, async (t) => {
    const writes = []
    let conflict = false
    const ctx = await mount(
      'views/governance/GovernanceRules.vue',
      rulesStubs({
        update: async (saved, input) => {
          if (conflict) throw { code: 'KG.REVISION_CONFLICT' }
          writes.push({ saved: clone(saved), input: clone(input) })
          return { ...input, id: saved.id, revision: saved.revision + 1 }
        },
      }),
      'canWrite,form,saved,error,editRule,save',
      '/',
      undefined,
      role,
    )
    t.after(ctx.stop)
    await ctx.vm.editRule(rule())
    ctx.vm.form.expression = 'updated expression'
    await ctx.vm.save()
    assert.equal(writes.length, 1)
    assert.equal(writes[0].saved.revision, 3)
    assert.equal(ctx.vm.saved.revision, 4)
    conflict = true
    ctx.vm.form.expression = 'unsaved conflict input'
    await ctx.vm.save()
    assert.equal(ctx.vm.form.expression, 'unsaved conflict input')
    assert.equal(ctx.vm.saved.revision, 4)
    assert.ok(ctx.vm.error)
  })
}

test('VIEWER clause handlers refuse writes even when invoked outside disabled buttons', async (t) => {
  const item = {
    id: 1,
    revision: 1,
    standard: 'ISO example',
    clause_number: '1',
    title_i18n: { 'zh-CN': '条款' },
    self_authored_description: { 'zh-CN': '自撰说明' },
    appendix_nature: 'NORMATIVE',
  }
  const ctx = await mount(
    'views/governance/StandardClauses.vue',
    {
      '@/api/clauses': {
        clausesApi: {
          list: async () => ({ items: [item], total: 1 }),
          get: async () => item,
          create: forbidden,
          update: forbidden,
          remove: forbidden,
        },
      },
    },
    'saved,showEditor,openCreate,openEdit,submit,remove',
    '/',
    undefined,
    'VIEWER',
  )
  t.after(ctx.stop)
  ctx.vm.openCreate()
  assert.equal(ctx.vm.showEditor, false)
  await ctx.vm.openEdit(item)
  assert.equal(ctx.vm.saved.id, item.id)
  await ctx.vm.submit()
  await ctx.vm.remove(item)
})

test('enum history stays frozen and cannot be submitted; VIEWER cannot mutate current entries', async (t) => {
  const current = dictionary()
  const history = {
    ...dictionary(),
    revision: 1,
    entries: [{ value: 'OLD', label_i18n: { 'zh-CN': '历史值' } }],
  }
  const stubs = {
    '@/api/enum-dictionaries': {
      enumDictionariesApi: {
        list: async () => ({ items: [current], total: 1 }),
        get: async () => current,
        revisions: async () => [current, history],
        references: async () => [{ enum_dict_revision: 1, latest_revision: 2 }],
        create: forbidden,
        update: forbidden,
        remove: forbidden,
      },
    },
  }
  for (const role of ['EDITOR', 'VIEWER']) {
    const ctx = await mount(
      'views/governance/EnumDictionaries.vue',
      stubs,
      'activeTab,form,references,selectedRevision,historyItem,showEditor,openCreate,openEdit,submit,remove',
      '/',
      undefined,
      role,
    )
    t.after(ctx.stop)
    if (role === 'VIEWER') {
      ctx.vm.openCreate()
      assert.equal(ctx.vm.showEditor, false)
    }
    await ctx.vm.openEdit(current)
    ctx.vm.activeTab = 'history'
    ctx.vm.selectedRevision = 1
    ctx.vm.form.entries[0].value = 'CHANGED'
    assert.equal(ctx.vm.historyItem.entries[0].value, 'OLD')
    assert.equal(ctx.vm.references[0].enum_dict_revision, 1)
    await ctx.vm.submit()
    if (role === 'VIEWER') {
      ctx.vm.activeTab = 'edit'
      await ctx.vm.submit()
      await ctx.vm.remove(current)
    }
  }
})

test('built-in template remains immutable and instantiation requires preview before a separate payload', async (t) => {
  const builtin = template(true)
  const before = clone(builtin)
  const calls = []
  const ctx = await mount(
    'views/governance/AssemblyTemplates.vue',
    templatesStubs(builtin, {
      instantiate: async (item, payload) => {
        calls.push({ item: clone(item), payload: clone(payload) })
        return { name: payload.name }
      },
    }),
    'form,readonly,instance,instanceStep,instanceTemplate,open,save,remove,prepareInstance,configureInstance,instantiate',
  )
  t.after(ctx.stop)
  await ctx.vm.open('edit', builtin)
  assert.equal(ctx.vm.readonly, true)
  ctx.vm.form.source = 'attempted change'
  await ctx.vm.save()
  await ctx.vm.remove()
  await ctx.vm.prepareInstance(builtin)
  assert.equal(ctx.vm.instanceStep, 'preview')
  ctx.vm.instance = {
    name: 'NewOntology',
    iri: 'https://example.org/new',
    labelZh: '新本体',
    labelEn: 'New ontology',
  }
  await ctx.vm.instantiate()
  assert.equal(calls.length, 0)
  ctx.vm.configureInstance()
  await ctx.vm.instantiate()
  assert.equal(calls.length, 1)
  assert.equal(calls[0].item.revision, 2)
  assert.deepEqual(calls[0].item.resources, before.resources)
  assert.equal(calls[0].payload.name, 'NewOntology')
  assert.deepEqual(builtin, before)
})

test('VIEWER may preview templates but cannot copy, instantiate, save or delete', async (t) => {
  const ctx = await mount(
    'views/governance/AssemblyTemplates.vue',
    templatesStubs(),
    'instance,instanceStep,editor,open,save,remove,prepareInstance,configureInstance,instantiate',
    '/',
    undefined,
    'VIEWER',
  )
  t.after(ctx.stop)
  for (const mode of ['create', 'copy', 'fromOntology']) {
    await ctx.vm.open(mode, template())
    assert.equal(ctx.vm.editor, false)
  }
  await ctx.vm.open('edit', template())
  await ctx.vm.save()
  await ctx.vm.remove()
  await ctx.vm.prepareInstance(template())
  ctx.vm.configureInstance()
  assert.equal(ctx.vm.instanceStep, 'preview')
  ctx.vm.instanceStep = 'configure'
  ctx.vm.instance = {
    name: 'NewOntology',
    iri: 'https://example.org/new',
    labelZh: '新本体',
    labelEn: '',
  }
  await ctx.vm.instantiate()
})

test('missing pinned members block template instantiation without substituting the latest revision', async (t) => {
  const ctx = await mount(
    'views/governance/AssemblyTemplates.vue',
    templatesStubs(template(), {
      resources: async () => [{ resource_id: 8, name: 'Entity', revisions: [3] }],
    }),
    'instanceStep,missingInstanceResources,prepareInstance,configureInstance,instantiate',
  )
  t.after(ctx.stop)
  await ctx.vm.prepareInstance(template())
  assert.equal(ctx.vm.missingInstanceResources, true)
  ctx.vm.configureInstance()
  assert.equal(ctx.vm.instanceStep, 'preview')
  await ctx.vm.instantiate()
})

test('VIEWER cannot perform import preview, import apply or template core verification', async (t) => {
  const restore = await mount(
    'views/governance/components/OntologyRestore.vue',
    {
      '@/api/ontology-restore': { ontologyRestoreApi: { preview: forbidden, apply: forbidden } },
    },
    'content,preview,loadFile,inspect,apply',
    '/',
    undefined,
    'VIEWER',
  )
  t.after(restore.stop)
  restore.vm.content = 'RDF'
  restore.vm.preview = { can_apply: true, preview_digest: 'digest' }
  await restore.vm.inspect()
  await restore.vm.apply()
  await restore.vm.loadFile({ target: { files: [{ size: 3, text: forbidden }] } })
  const core = await mount(
    'views/governance/components/TemplateCoreCheck.vue',
    {
      '@/api/clauses': { clausesApi: { all: async () => [] } },
      '@/api/templates': { templatesApi: { coreCheck: forbidden } },
    },
    'requirements,check',
    '/',
    undefined,
    'VIEWER',
  )
  t.after(core.stop)
  core.vm.requirements = [{ name: 'Entity', kind: 'ENTITY', standard_clause_id: 1 }]
  await core.vm.check()
})

test('failed governance lists keep errors distinct and retry can recover to empty', async (t) => {
  const request = deferred()
  let recovered = false
  const ctx = await mount(
    'views/governance/GovernanceRules.vue',
    rulesStubs({
      list: () => (recovered ? Promise.resolve({ items: [], total: 0 }) : request.promise),
    }),
    'loading,error,items,load',
  )
  t.after(ctx.stop)
  assert.equal(ctx.vm.loading, true)
  assert.equal(ctx.vm.error, '')
  request.reject({ code: 'NETWORK_ERROR' })
  await settle()
  assert.equal(ctx.vm.loading, false)
  assert.ok(ctx.vm.error)
  recovered = true
  await ctx.vm.load()
  assert.equal(ctx.vm.loading, false)
  assert.equal(ctx.vm.error, '')
  assert.deepEqual(ctx.vm.items, [])
})
