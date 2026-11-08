import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from '../../__tests__/view-harness.mjs'

const clone = (value) => JSON.parse(JSON.stringify(value))
function confirmation(t) {
  const old = Object.getOwnPropertyDescriptor(globalThis, 'window')
  const messages = []
  const listeners = new Map()
  let accepted = false
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      confirm: (message) => {
        messages.push(message)
        return accepted
      },
      addEventListener: (event, listener) => listeners.set(event, listener),
      removeEventListener: (event) => listeners.delete(event),
    },
  })
  t.after(() => {
    if (old) Object.defineProperty(globalThis, 'window', old)
    else delete globalThis.window
  })
  return {
    messages,
    listeners,
    accept: (value) => {
      accepted = value
    },
  }
}
const rule = {
  id: 1,
  revision: 1,
  identifier: 'DraftRule',
  name_i18n: { 'zh-CN': '规则' },
  category: 'quality',
  source_kind: 'ENTERPRISE',
  source_reference: 'Policy 1',
  target_iri: 'https://example.org/Entity',
  severity: 'VIOLATION',
  language: 'OWL',
  execution: 'MANUAL',
  expression: 'initial expression',
  positive_example: '',
  negative_example: '',
}

test('rule editor retains cancelled changes, preserves failed saves and closes cleanly after a successful save', async (t) => {
  let reject = true
  const ctx = await mount(
    'views/governance/GovernanceRules.vue',
    {
      '@/api/governance': {
        rulesApi: {
          list: async () => ({ items: [], total: 0 }),
          get: async () => clone(rule),
          update: async (saved, input) => {
            if (reject) throw { code: 'KG.REVISION_CONFLICT' }
            return { ...clone(input), id: saved.id, revision: saved.revision + 1 }
          },
        },
      },
    },
    'form,showEditor,editorVisible,editRule,save',
  )
  t.after(ctx.stop)
  const dialog = confirmation(t)
  await ctx.vm.editRule(rule)
  await settle()
  ctx.vm.form.expression = 'keep this expression'
  ctx.vm.editorVisible = false
  assert.equal(ctx.vm.showEditor, true)
  assert.equal(ctx.vm.form.expression, 'keep this expression')
  await ctx.vm.save()
  ctx.vm.editorVisible = false
  assert.equal(dialog.messages.length, 2, 'rejected save does not clear the draft')
  reject = false
  await ctx.vm.save()
  ctx.vm.editorVisible = false
  assert.equal(ctx.vm.showEditor, false)
  assert.equal(dialog.messages.length, 2, 'successful save remains open but is clean')
})

test('clause create confirms abandonment and a server-normalized successful save is clean', async (t) => {
  const ctx = await mount(
    'views/governance/StandardClauses.vue',
    {
      '@/api/clauses': {
        clausesApi: {
          list: async () => ({ items: [], total: 0 }),
          create: async (input) => ({
            ...clone(input),
            id: 1,
            revision: 1,
            standard: input.standard.trim(),
          }),
        },
      },
    },
    'form,showEditor,editorVisible,openCreate,submit',
  )
  t.after(ctx.stop)
  const dialog = confirmation(t)
  ctx.vm.openCreate()
  await settle()
  ctx.vm.form.standard = 'draft'
  ctx.vm.editorVisible = false
  assert.equal(ctx.vm.showEditor, true)
  assert.equal(ctx.vm.form.standard, 'draft')
  dialog.accept(true)
  ctx.vm.editorVisible = false
  assert.equal(ctx.vm.showEditor, false)
  ctx.vm.openCreate()
  await settle()
  Object.assign(ctx.vm.form, {
    standard: ' Standard ',
    clause_number: '1',
    title_i18n: { 'zh-CN': '标题' },
    self_authored_description: { 'zh-CN': '说明' },
  })
  await ctx.vm.submit()
  ctx.vm.editorVisible = false
  assert.equal(ctx.vm.showEditor, false)
  assert.equal(ctx.vm.form.standard, 'Standard')
  assert.equal(dialog.messages.length, 2)
})

test('dictionary detail loading and history browsing do not create drafts; edits do and successful save bypasses confirmation', async (t) => {
  const item = {
    id: 1,
    revision: 1,
    name: 'Status',
    label_i18n: { 'zh-CN': '状态' },
    definition_i18n: { 'zh-CN': '说明' },
    entries: [{ value: 'OPEN', label_i18n: { 'zh-CN': '开放' } }],
  }
  const detail = deferred()
  const current = { ...clone(item), revision: 2, definition_i18n: { 'zh-CN': '最新说明' } }
  const ctx = await mount(
    'views/governance/EnumDictionaries.vue',
    {
      '@/api/enum-dictionaries': {
        enumDictionariesApi: {
          list: async () => ({ items: [item], total: 1 }),
          get: () => detail.promise,
          revisions: async () => [item, current],
          references: async () => [],
          update: async (saved, input) => ({
            ...clone(input),
            id: saved.id,
            revision: saved.revision + 1,
          }),
        },
      },
    },
    'form,showEditor,editorVisible,editorReady,activeTab,selectedRevision,openEdit,submit',
  )
  t.after(ctx.stop)
  const dialog = confirmation(t)
  const pending = ctx.vm.openEdit(item)
  await settle()
  assert.equal(ctx.vm.editorReady, false)
  detail.resolve(current)
  await pending
  await settle()
  ctx.vm.activeTab = 'history'
  ctx.vm.selectedRevision = 1
  ctx.vm.editorVisible = false
  assert.equal(ctx.vm.showEditor, false)
  assert.equal(dialog.messages.length, 0)
  await ctx.vm.openEdit(item)
  await settle()
  ctx.vm.form.entries[0].value = 'CLOSED'
  ctx.vm.editorVisible = false
  assert.equal(ctx.vm.showEditor, true)
  assert.equal(ctx.vm.form.entries[0].value, 'CLOSED')
  await ctx.vm.submit()
  assert.equal(ctx.vm.showEditor, false)
  assert.equal(dialog.messages.length, 1)
})

test('template editing and instance details protect drafts while built-in preview stays read-only', async (t) => {
  const item = {
    id: 1,
    revision: 1,
    name: 'DraftTemplate',
    label_i18n: { 'zh-CN': '模板' },
    source: 'Policy 1',
    basis: 'Example',
    builtin: false,
    reference_count: 0,
    resources: [],
  }
  const ctx = await mount(
    'views/governance/AssemblyTemplates.vue',
    {
      '@/api/templates': {
        templatesApi: {
          list: async () => ({ items: [item], total: 1 }),
          get: async () => clone(item),
          resources: async () => [],
          ontologies: async () => [],
          update: async (saved, input) => ({
            ...clone(input),
            id: saved.id,
            revision: saved.revision + 1,
            builtin: false,
            reference_count: 0,
          }),
          instantiate: async (_item, input) => ({ name: input.name }),
        },
      },
    },
    'form,editor,editorVisible,instance,instantiateVisible,instanceVisible,open,save,prepareInstance,configureInstance,instantiate',
  )
  t.after(ctx.stop)
  const dialog = confirmation(t)
  await ctx.vm.open('edit', item)
  await settle()
  ctx.vm.form.basis = 'draft basis'
  ctx.vm.editorVisible = false
  assert.equal(ctx.vm.editor, true)
  assert.equal(ctx.vm.form.basis, 'draft basis')
  await ctx.vm.save()
  ctx.vm.editorVisible = false
  assert.equal(ctx.vm.editor, false)
  assert.equal(dialog.messages.length, 1)
  await ctx.vm.prepareInstance(item)
  ctx.vm.configureInstance()
  await settle()
  ctx.vm.instance = {
    name: 'NewOntology',
    iri: 'https://example.org/new',
    labelZh: '新本体',
    labelEn: '',
  }
  ctx.vm.instanceVisible = false
  assert.equal(ctx.vm.instantiateVisible, true)
  assert.equal(ctx.vm.instance.name, 'NewOntology')
  await ctx.vm.instantiate()
  assert.equal(ctx.vm.instantiateVisible, false)
  assert.equal(dialog.messages.length, 2)
  item.builtin = true
  await ctx.vm.open('edit', item)
  await settle()
  ctx.vm.editorVisible = false
  assert.equal(ctx.vm.editor, false)
  assert.equal(dialog.messages.length, 2)
})

test('VIEWER rule browsing never confirms leaving read-only content', async (t) => {
  const ctx = await mount(
    'views/governance/GovernanceRules.vue',
    {
      '@/api/governance': {
        rulesApi: { list: async () => ({ items: [rule], total: 1 }), get: async () => clone(rule) },
      },
    },
    'form,showEditor,editorVisible,editRule',
    '/',
    undefined,
    'VIEWER',
  )
  t.after(ctx.stop)
  const dialog = confirmation(t)
  await ctx.vm.editRule(rule)
  await settle()
  ctx.vm.editorVisible = false
  assert.equal(ctx.vm.showEditor, false)
  assert.equal(dialog.messages.length, 0)
})

test('import keeps the draft after a rejected apply and clears reload protection only after a successful import', async (t) => {
  const dialog = confirmation(t)
  let reject = true
  const writes = []
  const ctx = await mount(
    'views/governance/components/OntologyRestore.vue',
    {
      '@/api/ontology-restore': {
        ontologyRestoreApi: {
          preview: async () => ({ can_apply: true, preview_digest: 'digest' }),
          apply: async (input) => {
            writes.push(clone(input))
            if (reject) throw { code: 'KG.REVISION_CONFLICT' }
            return { ontology_id: 1, current_revision: 1, source_revision: 1 }
          },
        },
      },
    },
    'content,preview,restored,error,inspect,apply',
  )
  t.after(ctx.stop)
  const reloadBlocked = () => {
    let blocked = false
    dialog.listeners.get('beforeunload')({
      preventDefault() {
        blocked = true
      },
    })
    return blocked
  }
  assert.equal(reloadBlocked(), false)
  ctx.vm.content = 'example RDF'
  assert.equal(reloadBlocked(), true)
  await ctx.vm.inspect()
  await ctx.vm.apply()
  assert.equal(ctx.vm.content, 'example RDF')
  assert.ok(ctx.vm.error)
  assert.equal(ctx.vm.restored, null)
  assert.equal(reloadBlocked(), true)
  reject = false
  await ctx.vm.inspect()
  await ctx.vm.apply()
  assert.equal(ctx.vm.restored.ontology_id, 1)
  assert.equal(ctx.vm.content, 'example RDF')
  assert.equal(reloadBlocked(), false)
  assert.equal(writes.length, 2)
  assert.equal(writes[1].preview_digest, 'digest')
  assert.equal(dialog.messages.length, 0, 'successful import never asks for abandonment')
  ctx.vm.content = 'new draft'
  assert.equal(reloadBlocked(), true)
})
