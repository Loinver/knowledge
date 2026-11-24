import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { test } from 'node:test'

import { renderToString } from '@vue/server-renderer'
import { createSSRApp, h, reactive, watch } from 'vue'
import { createI18n } from 'vue-i18n'

import { mount as mountForm } from '../../../../testing/view-harness.mjs'
import { load as loadReal, root } from '../../relation-types/__tests__/c1-render-harness.mjs'
import { deferred, mount, settle } from './configuration-harness.mjs'

const entry = 'views/semantic-assets/configuration/assembly-templates/AssemblyTemplatesPage.vue'
const template = (id = 1, extra = {}) => ({
  id,
  name: `Template${id}`,
  label_i18n: { 'zh-CN': '模板', 'en-US': 'Template' },
  source: 'Example policy',
  basis: 'Example clause',
  builtin: false,
  revision: 7,
  reference_count: 0,
  resources: [{ resource_id: 11, pinned_revision: 2 }],
  ...extra,
})
const expose =
  'items,total,page,query,search,filter,loading,busy,error,listError,initialized,notice,editor,editorVisible,mode,saved,form,catalog,resourceId,resourceRevision,ontologyId,ontologyRevision,readonly,resourcesEditable,instanceTemplate,instantiateVisible,instanceStep,instance,instanceVisible,missingInstanceResources,open,save,remove,prepareInstance,configureInstance,instantiate,addResource,doSearch,clearSearch,changeFilter,resetSearch,load,editorFormRef,instanceFormRef,editorModel,editorFormRules,instanceFormRules,editorValidation,instanceValidation,catalogLoading,catalogError'

async function setup(overrides = {}, role = 'EDITOR') {
  const api = {
    list: async () => ({ items: [template()], total: 61, page: 1, page_size: 20 }),
    get: async (id) => template(id),
    resources: async () => [
      {
        resource_id: 11,
        name: 'Employee',
        iri: 'https://example.org/Employee',
        kind: 'ENTITY',
        revisions: [1, 2, 3],
        label_i18n: {},
      },
    ],
    ontologies: async () => [{ id: 5, name: 'Enterprise', current_revision: 4 }],
    create: async (input) => template(2, input),
    update: async (item, input) => template(item.id, { ...input, revision: item.revision + 1 }),
    copy: async (_item, input) => template(2, input),
    fromOntology: async (input) => template(2, input),
    remove: async () => {},
    instantiate: async () => ({ id: 9, name: 'Created', template: template() }),
    ...overrides,
  }
  return mount(entry, { '@/api/templates': { templatesApi: api } }, expose, '/', undefined, role)
}

test('template remote pages retain server total; search, clear and kind filters reset page before loading', async () => {
  const calls = []
  const view = await setup({
    list: async (params) => {
      calls.push({ ...params })
      return { items: [template(params.page)], total: 61, page: params.page, page_size: 20 }
    },
  })
  try {
    view.vm.page = 3
    await settle()
    assert.equal(view.vm.items[0].id, 3)
    assert.equal(view.vm.total, 61)
    view.vm.query = ' New '
    await settle()
    assert.equal(calls.at(-1).q, '')
    view.vm.doSearch()
    await settle()
    assert.deepEqual(calls.at(-1), { q: 'New', page: 1, builtin: undefined })
    view.vm.page = 2
    await settle()
    view.vm.changeFilter('custom')
    await settle()
    assert.equal(calls.at(-1).page, 1)
    assert.equal(calls.at(-1).builtin, false)
    view.vm.page = 2
    await settle()
    view.vm.clearSearch()
    await settle()
    assert.equal(calls.at(-1).q, '')
    assert.equal(calls.at(-1).page, 1)
  } finally {
    view.stop()
  }
})

test('obsolete template list successes and errors cannot replace the latest remote query', async () => {
  const calls = []
  const view = await setup({
    list: (params, signal) => {
      const request = deferred()
      calls.push({ ...request, params, signal })
      return request.promise
    },
  })
  try {
    view.vm.query = 'Latest'
    view.vm.doSearch()
    await settle()
    assert.equal(calls[0].signal.aborted, true)
    calls[1].resolve({ items: [template(2)], total: 81 })
    await settle()
    calls[0].reject({ code: 'KG.REVISION_CONFLICT' })
    await settle()
    assert.equal(view.vm.items[0].id, 2)
    assert.equal(view.vm.total, 81)
    assert.equal(view.vm.error, '')
    assert.equal(view.vm.loading, false)
  } finally {
    view.stop()
  }
})

test('newest template detail wins over earlier success and earlier failure', async () => {
  for (const reject of [false, true]) {
    const old = deferred()
    const view = await setup({
      get: (id) => (id === 1 ? old.promise : Promise.resolve(template(id))),
    })
    try {
      const first = view.vm.open('edit', template(1))
      await view.vm.open('edit', template(2))
      if (reject) old.reject({ code: 'KG.REVISION_CONFLICT' })
      else old.resolve(template(1))
      await first
      assert.equal(view.vm.saved.id, 2)
      assert.equal(view.vm.form.name, 'Template2')
      assert.equal(view.vm.error, '')
      assert.equal(view.vm.busy, false)
    } finally {
      view.stop()
    }
  }
})

test('template writes preserve target revision, sibling member pins and independent payload snapshots', async () => {
  const writes = []
  const response = deferred()
  const view = await setup({
    update: (item, input) => {
      writes.push({ item, input })
      return response.promise
    },
  })
  try {
    await view.vm.open('edit', template())
    view.vm.form.name = 'Changed'
    const first = view.vm.save()
    await view.vm.save()
    assert.equal(writes.length, 1)
    assert.equal(writes[0].item.revision, 7)
    assert.deepEqual(writes[0].input.resources, [{ resource_id: 11, pinned_revision: 2 }])
    view.vm.form.resources[0].pinned_revision = 3
    assert.equal(writes[0].input.resources[0].pinned_revision, 2)
    response.resolve(template(1, { name: 'Changed', revision: 8 }))
    await first
    assert.equal(view.vm.saved.revision, 8)
    assert.equal(view.vm.form.resources[0].pinned_revision, 2)
  } finally {
    view.stop()
  }
})

test('closing an editor invalidates an old save success or failure without clearing the next write busy state', async () => {
  for (const reject of [false, true]) {
    const old = deferred()
    const latest = deferred()
    let calls = 0
    const view = await setup({ update: () => (++calls === 1 ? old.promise : latest.promise) })
    try {
      await view.vm.open('edit', template(1))
      const first = view.vm.save()
      view.vm.editor = false
      await view.vm.open('edit', template(2))
      view.vm.form.name = 'Latest'
      const second = view.vm.save()
      if (reject) old.reject({ code: 'KG.REVISION_CONFLICT' })
      else old.resolve(template(1, { revision: 8 }))
      await first
      assert.equal(view.vm.saved.id, 2)
      assert.equal(view.vm.form.name, 'Latest')
      assert.equal(view.vm.error, '')
      assert.equal(view.vm.busy, true)
      latest.resolve(template(2, { name: 'Latest', revision: 8 }))
      await second
      assert.equal(view.vm.busy, false)
    } finally {
      view.stop()
    }
  }
})

test('failed template save preserves the full editable draft and target revision', async () => {
  const view = await setup({
    update: async () => {
      throw { code: 'KG.REVISION_CONFLICT' }
    },
  })
  try {
    await view.vm.open('edit', template())
    view.vm.form.basis = 'Unsaved basis'
    await view.vm.save()
    assert.equal(view.vm.form.basis, 'Unsaved basis')
    assert.equal(view.vm.saved.revision, 7)
    assert.equal(view.vm.editor, true)
    assert.notEqual(view.vm.error, '')
    assert.equal(view.vm.busy, false)
  } finally {
    view.stop()
  }
})

test('builtin templates and viewers stay read-only while copy retains frozen member pins', async () => {
  let writes = 0
  const view = await setup({
    get: async () => template(1, { builtin: true }),
    update: async () => {
      writes++
    },
    remove: async () => {
      writes++
    },
  })
  try {
    await view.vm.open('edit', template())
    assert.equal(view.vm.readonly, true)
    assert.equal(view.vm.resourcesEditable, false)
    await view.vm.save()
    await view.vm.remove()
    assert.equal(writes, 0)
    await view.vm.open('copy', template())
    assert.equal(view.vm.resourcesEditable, false)
    assert.deepEqual(view.vm.form.resources, [{ resource_id: 11, pinned_revision: 2 }])
  } finally {
    view.stop()
  }
  const viewer = await setup(
    {
      update: async () => {
        writes++
      },
    },
    'VIEWER',
  )
  try {
    await viewer.vm.open('edit', template())
    await viewer.vm.save()
    await viewer.vm.open('create')
    assert.equal(viewer.vm.mode, 'edit')
    assert.equal(viewer.vm.resourcesEditable, false)
    assert.equal(writes, 0)
  } finally {
    viewer.stop()
  }
})

test('resource and ontology selections retain numeric versions; missing member versions prevent instantiation', async () => {
  let writes = 0
  const view = await setup({
    instantiate: async () => {
      writes++
    },
  })
  try {
    await view.vm.open('create')
    view.vm.resourceId = 11
    await settle()
    assert.equal(view.vm.resourceRevision, 3)
    view.vm.resourceRevision = 2
    view.vm.addResource()
    assert.deepEqual(view.vm.form.resources, [{ resource_id: 11, pinned_revision: 2 }])
    await view.vm.open('fromOntology')
    view.vm.ontologyId = 5
    await settle()
    assert.equal(view.vm.ontologyRevision, 4)
    view.vm.instanceTemplate = template(1, {
      resources: [{ resource_id: 11, pinned_revision: 99 }],
    })
    view.vm.instantiateVisible = true
    view.vm.configureInstance()
    assert.equal(view.vm.instanceStep, 'preview')
    view.vm.instanceStep = 'configure'
    view.vm.instance = {
      name: 'Enterprise',
      iri: 'https://example.org/Enterprise',
      labelZh: '企业',
      labelEn: '',
    }
    await view.vm.instantiate()
    assert.equal(writes, 0)
    assert.equal(view.vm.missingInstanceResources, true)
  } finally {
    view.stop()
  }
})

test('old instantiation cannot close a newer preview; revisions stay attached to its original request', async () => {
  const response = deferred()
  const writes = []
  const view = await setup({
    instantiate: (item, input) => {
      writes.push({ item, input })
      return response.promise
    },
  })
  try {
    await view.vm.prepareInstance(template(1))
    view.vm.configureInstance()
    view.vm.instance = {
      name: 'Enterprise',
      iri: 'https://example.org/Enterprise',
      labelZh: '企业',
      labelEn: '',
    }
    const pending = view.vm.instantiate()
    await view.vm.instantiate()
    assert.equal(writes.length, 1)
    assert.equal(writes[0].item.revision, 7)
    assert.deepEqual(writes[0].input.label_i18n, { 'zh-CN': '企业' })
    view.vm.instantiateVisible = false
    await view.vm.prepareInstance(template(2))
    response.resolve({ name: 'Obsolete', template: template(1) })
    await pending
    assert.equal(view.vm.instantiateVisible, true)
    assert.equal(view.vm.instanceTemplate.id, 2)
    assert.equal(view.vm.notice, '')
  } finally {
    view.stop()
  }
})

test('core checks preserve NOT_RUN and VIOLATION and ignore results after requirement identity changes', async () => {
  const calls = []
  const view = await mount(
    'views/semantic-assets/configuration/assembly-templates/components/TemplateCoreCheck.vue',
    {
      '@/api/clauses': {
        clausesApi: { all: async () => [{ id: 1, standard: 'Example', clause_number: '1' }] },
      },
      '@/api/templates': {
        templatesApi: {
          coreCheck: (id, input) => {
            const request = deferred()
            calls.push({ ...request, id, input })
            return request.promise
          },
        },
      },
    },
    'props,requirements,result,error,loading,check',
    '/',
    (source) =>
      source.replace('defineProps<{ templateId: number }>()', 'ref({ templateId: 1 }).value'),
  )
  try {
    view.vm.requirements[0] = { name: 'Employee', kind: 'ENTITY', standard_clause_id: 1 }
    const first = view.vm.check()
    await view.vm.check()
    assert.equal(calls.length, 1)
    calls[0].resolve({
      template_id: 1,
      template_revision: 7,
      all_core_present: true,
      standards_conformance: 'NOT_RUN',
      items: [],
    })
    await first
    assert.equal(view.vm.result.standards_conformance, 'NOT_RUN')
    const old = view.vm.check()
    view.vm.props.templateId = 2
    const latest = view.vm.check()
    calls[1].resolve({ template_id: 1, standards_conformance: 'PASS' })
    await old
    assert.equal(view.vm.result, null)
    assert.equal(view.vm.loading, true)
    calls[2].resolve({
      template_id: 2,
      template_revision: 8,
      all_core_present: false,
      standards_conformance: 'VIOLATION',
      items: [],
    })
    await latest
    assert.equal(view.vm.result.standards_conformance, 'VIOLATION')
    view.vm.requirements[0].name = 'Department'
    assert.equal(view.vm.result, null)
  } finally {
    view.stop()
  }
})

const validMetadata = () => ({
  name: ' general template name ',
  source: ' Example policy ',
  basis: ' Example basis ',
  label_i18n: { 'zh-CN': ' 模板 ', 'en-US': '   ' },
  resources: [],
})
const formTransform = (source) =>
  source.replace('defineExpose<FormInst>({ validate, restoreValidation })', '')

test('all template modes reject required and overlength metadata without writes or draft loss', async (t) => {
  const writes = []
  const view = await setup(
    Object.fromEntries(
      ['create', 'update', 'copy', 'fromOntology'].map((action) => [
        action,
        async (...args) => writes.push(args),
      ]),
    ),
  )
  t.after(view.stop)
  for (const mode of ['create', 'edit', 'copy', 'fromOntology']) {
    await view.vm.open(mode, mode === 'edit' || mode === 'copy' ? template() : undefined)
    for (const invalid of [
      { name: ' ' },
      { name: 'a'.repeat(129) },
      { source: ' ' },
      { source: 's'.repeat(129) },
      { basis: ' ' },
      { basis: 'b'.repeat(4001) },
      { label_i18n: { 'zh-CN': ' ' } },
      { label_i18n: { 'zh-CN': '中'.repeat(257) } },
      { label_i18n: { 'zh-CN': '模板', 'en-US': 'x'.repeat(257) } },
      { label_i18n: { 'zh-CN': '模板', fr: 'Unsupported' } },
    ]) {
      view.vm.form = { ...validMetadata(), ...invalid }
      view.vm.ontologyId = 5
      await settle()
      view.vm.ontologyRevision = 2
      const before = JSON.stringify(view.vm.form)
      await view.vm.save()
      assert.deepEqual(writes, [], mode)
      assert.equal(JSON.stringify(view.vm.form), before)
      assert.equal(view.vm.editor, true)
      assert.equal(view.vm.editorValidation, false)
    }
  }
})

test('metadata limits use Unicode code points; copy and frozen ontology requests keep their exact contracts', async (t) => {
  const writes = []
  const view = await setup(
    Object.fromEntries(
      ['create', 'update', 'copy', 'fromOntology'].map((action) => [
        action,
        async (...args) => {
          writes.push({ action, args })
          return template(3)
        },
      ]),
    ),
  )
  t.after(view.stop)
  for (const mode of ['create', 'edit', 'copy', 'fromOntology']) {
    await view.vm.open(mode, ['edit', 'copy'].includes(mode) ? template() : undefined)
    view.vm.form = {
      ...validMetadata(),
      name: '😀'.repeat(128),
      source: 's'.repeat(128),
      basis: 'b'.repeat(4000),
      label_i18n: { 'zh-CN': '😀'.repeat(256), 'en-US': '  ' },
      resources: [{ resource_id: 11, pinned_revision: 2 }],
    }
    view.vm.ontologyId = 5
    await settle()
    view.vm.ontologyRevision = 2
    await view.vm.save()
    const { action, args } = writes.at(-1)
    assert.equal(action, mode === 'edit' ? 'update' : mode)
    const payload = args.at(-1)
    assert.deepEqual(Object.keys(payload.label_i18n), ['zh-CN'])
    assert.equal(Array.from(payload.name).length, 128)
    if (mode === 'copy') {
      assert.equal(args[0].revision, 7)
      assert.equal(Object.hasOwn(payload, 'resources'), false)
      assert.equal(args[0].resources[0].pinned_revision, 2)
    } else if (mode === 'fromOntology') {
      assert.equal(payload.ontology_id, 5)
      assert.equal(payload.ontology_revision, 2)
      assert.equal(Object.hasOwn(payload, 'resources'), false)
    } else {
      assert.deepEqual(payload.resources, [{ resource_id: 11, pinned_revision: 2 }])
      if (mode === 'edit') assert.equal(args[0].revision, 7)
    }
  }
})

test('empty member lists are legal; invalid, duplicate and excessive members and half-selected pins never write', async (t) => {
  const writes = []
  const view = await setup({
    create: async (input) => {
      writes.push(input)
      return template(2, input)
    },
  })
  t.after(view.stop)
  await view.vm.open('create')
  view.vm.form = validMetadata()
  await view.vm.save()
  assert.deepEqual(writes[0].resources, [])
  await view.vm.open('create')
  for (const resources of [
    [{ resource_id: 0, pinned_revision: 1 }],
    [{ resource_id: 11, pinned_revision: 0 }],
    [{ resource_id: 11, pinned_revision: 1.5 }],
    [{ resource_id: Number.MAX_SAFE_INTEGER + 1, pinned_revision: 1 }],
    [
      { resource_id: 11, pinned_revision: 1 },
      { resource_id: 11, pinned_revision: 2 },
    ],
    Array.from({ length: 1001 }, (_, i) => ({ resource_id: i + 1, pinned_revision: 1 })),
  ]) {
    view.vm.form = { ...validMetadata(), resources }
    await view.vm.save()
    assert.equal(writes.length, 1)
  }
  view.vm.form = validMetadata()
  view.vm.resourceId = 11
  await settle()
  view.vm.resourceRevision = null
  await view.vm.save()
  assert.equal(writes.length, 1)
  view.vm.resourceRevision = 99
  await view.vm.addResource()
  assert.deepEqual(view.vm.form.resources, [])
  view.vm.resourceRevision = 2
  await view.vm.addResource()
  assert.deepEqual(view.vm.form.resources, [{ resource_id: 11, pinned_revision: 2 }])
  view.vm.resourceId = 11
  await settle()
  await view.vm.addResource()
  assert.equal(view.vm.form.resources.length, 1)
})

test('from-ontology validates selected numeric identity without clamping zero or applying hidden rules in other modes', async (t) => {
  const writes = []
  const view = await setup({
    fromOntology: async (input) => {
      writes.push(input)
      return template(2)
    },
  })
  t.after(view.stop)
  await view.vm.open('fromOntology')
  view.vm.form = validMetadata()
  for (const [id, revision] of [
    [null, null],
    [5, null],
    [5, 0],
    [5, -1],
    [5, 1.5],
    [0, 2],
  ]) {
    view.vm.ontologyId = id
    await settle()
    view.vm.ontologyRevision = revision
    await view.vm.save()
    assert.equal(writes.length, 0)
    assert.equal(view.vm.ontologyRevision, revision)
  }
  view.vm.ontologyId = 5
  await settle()
  view.vm.ontologyRevision = 2
  await view.vm.save()
  assert.equal(writes[0].ontology_revision, 2)
  await view.vm.open('create')
  assert.equal(Object.hasOwn(view.vm.editorFormRules, 'ontologyRevision'), false)
})

test('editor validation deduplicates submits, invalidates changed models and rejects late responses from prior sessions', async (t) => {
  for (const action of ['editInput', 'mode', 'ontology', 'reopen', 'rejectOld']) {
    const old = deferred()
    const current = deferred()
    const writes = []
    const view = await setup({ create: async (...args) => writes.push(args) })
    t.after(view.stop)
    await view.vm.open('create')
    view.vm.form = validMetadata()
    let validations = 0
    view.vm.editorFormRef = {
      validate: () => {
        validations++
        return old.promise
      },
      restoreValidation() {},
    }
    const first = view.vm.save()
    await view.vm.save()
    assert.equal(validations, 1)
    assert.equal(view.vm.busy, false)
    assert.equal(view.vm.editorValidation, true)
    let next
    if (action === 'editInput') view.vm.form.basis = 'New basis'
    else if (action === 'mode') view.vm.mode = 'fromOntology'
    else if (action === 'ontology') view.vm.ontologyId = 5
    else {
      view.vm.editor = false
      await view.vm.open('create')
      view.vm.form = { ...validMetadata(), name: 'Next session' }
      view.vm.editorFormRef = { validate: () => current.promise, restoreValidation() {} }
      next = view.vm.save()
    }
    if (action === 'rejectOld') old.reject(new Error('FORM_INVALID'))
    else old.resolve()
    await first
    assert.deepEqual(writes, [])
    if (next) {
      assert.equal(view.vm.editorValidation, true)
      assert.equal(view.vm.form.name, 'Next session')
      assert.equal(view.vm.error, '')
      current.reject(new Error('FORM_INVALID'))
      await next
    }
    assert.equal(view.vm.editorValidation, false)
  }
})

test('instance metadata schema rejects invalid input; relative IRI and omitted blank English remain legal', async (t) => {
  const writes = []
  const view = await setup({
    instantiate: async (item, input) => {
      writes.push({ item, input })
      return { name: input.name, template: item }
    },
  })
  t.after(view.stop)
  await view.vm.prepareInstance(template())
  view.vm.configureInstance()
  for (const invalid of [
    { name: ' ' },
    { name: 'x'.repeat(129) },
    { iri: ' ' },
    { iri: 'i'.repeat(641) },
    { labelZh: ' ' },
    { labelZh: '中'.repeat(257) },
    { labelEn: 'e'.repeat(257) },
  ]) {
    view.vm.instance = {
      name: 'general instance name',
      iri: '../relative',
      labelZh: '企业',
      labelEn: ' ',
      ...invalid,
    }
    const before = JSON.stringify(view.vm.instance)
    await view.vm.instantiate()
    assert.deepEqual(writes, [])
    assert.equal(JSON.stringify(view.vm.instance), before)
    assert.equal(view.vm.instantiateVisible, true)
  }
  view.vm.instance = {
    name: ' general instance name ',
    iri: ' ../relative ',
    labelZh: ' 企业 ',
    labelEn: ' ',
  }
  await view.vm.instantiate()
  assert.equal(writes[0].item.revision, 7)
  assert.equal(writes[0].item.resources[0].pinned_revision, 2)
  assert.deepEqual(writes[0].input, {
    name: 'general instance name',
    iri: '../relative',
    label_i18n: { 'zh-CN': '企业' },
  })
})

test('instance validation has its own lock and late validation cannot replace or unlock another preview', async (t) => {
  const old = deferred()
  const current = deferred()
  const writes = []
  const view = await setup({ instantiate: async (...args) => writes.push(args) })
  t.after(view.stop)
  await view.vm.prepareInstance(template())
  view.vm.configureInstance()
  view.vm.instance = { name: 'Instance', iri: 'urn:example:instance', labelZh: '企业', labelEn: '' }
  let validations = 0
  view.vm.instanceFormRef = {
    validate: () => {
      validations++
      return old.promise
    },
    restoreValidation() {},
  }
  const first = view.vm.instantiate()
  await view.vm.instantiate()
  assert.equal(validations, 1)
  assert.equal(view.vm.instanceValidation, true)
  assert.equal(view.vm.busy, false)
  view.vm.instantiateVisible = false
  await view.vm.prepareInstance(template(2))
  view.vm.configureInstance()
  view.vm.instance = {
    name: 'New instance',
    iri: 'urn:example:new',
    labelZh: '下一会话',
    labelEn: '',
  }
  view.vm.instanceFormRef = { validate: () => current.promise, restoreValidation() {} }
  const next = view.vm.instantiate()
  old.resolve()
  await first
  assert.deepEqual(writes, [])
  assert.equal(view.vm.instanceValidation, true)
  assert.equal(view.vm.instanceTemplate.id, 2)
  current.reject(new Error('FORM_INVALID'))
  await next
  assert.equal(view.vm.instanceValidation, false)
  assert.equal(view.vm.instance.labelZh, '下一会话')
})

test('real FormContainer validates both models, focuses first invalid fields with request busy still false and refreshes sibling errors', async (t) => {
  const writes = []
  const view = await setup({
    create: async (...args) => writes.push(args),
    instantiate: async (...args) => writes.push(args),
  })
  t.after(view.stop)
  await view.vm.open('create')
  const rules = reactive({ ...view.vm.editorFormRules })
  t.after(
    watch(
      () => view.vm.editorFormRules,
      (next) => {
        for (const key of Object.keys(rules)) delete rules[key]
        Object.assign(rules, next)
      },
      { flush: 'sync' },
    ),
  )
  const form = await mountForm(
    'components/business/FormContainer.vue',
    {},
    'validate,errors,registered,blocked',
    '/',
    formTransform,
    'EDITOR',
    { model: view.vm.editorModel, rules, disabled: false, submitting: false },
  )
  t.after(form.stop)
  const focused = []
  for (const field of Object.keys(rules))
    form.vm.registered.set(field, () => ({
      querySelector: () => ({
        focus() {
          assert.equal(view.vm.busy, false)
          assert.equal(view.vm.editorValidation, true)
          assert.equal(form.vm.blocked, false)
          focused.push(field)
        },
      }),
    }))
  view.vm.editorFormRef = { validate: form.vm.validate, restoreValidation() {} }
  await view.vm.save()
  assert.equal(focused[0], 'metadata.name')
  assert.equal(form.vm.errors['metadata.name'], 'This field is required')
  assert.deepEqual(writes, [])
  view.vm.form = validMetadata()
  await settle()
  assert.deepEqual(form.vm.errors, {})
  view.vm.resourceId = 11
  await settle()
  view.vm.resourceRevision = null
  await settle()
  await view.vm.save()
  assert.ok(form.vm.errors.resourceRevision)
  view.vm.resourceId = null
  await settle()
  assert.equal(form.vm.errors.resourceRevision, undefined)

  await view.vm.prepareInstance(template())
  view.vm.configureInstance()
  const instanceForm = await mountForm(
    'components/business/FormContainer.vue',
    {},
    'validate,errors,registered,blocked',
    '/',
    formTransform,
    'EDITOR',
    {
      model: view.vm.instance,
      rules: view.vm.instanceFormRules,
      disabled: false,
      submitting: false,
    },
  )
  t.after(instanceForm.stop)
  instanceForm.vm.registered.set('name', () => ({
    querySelector: () => ({
      focus() {
        assert.equal(view.vm.instanceValidation, true)
        assert.equal(instanceForm.vm.blocked, false)
        focused.push('instance.name')
      },
    }),
  }))
  view.vm.instanceFormRef = { validate: instanceForm.vm.validate, restoreValidation() {} }
  await view.vm.instantiate()
  assert.equal(focused.at(-1), 'instance.name')
  assert.ok(instanceForm.vm.errors.name)
  assert.deepEqual(writes, [])
})

test('draft guard rejects dirty closes, accepts confirmed closes and rebuilds clean save and reopen baselines', async (t) => {
  const prior = globalThis.window
  let accept = false
  let confirmations = 0
  globalThis.window = {
    confirm: () => {
      confirmations++
      return accept
    },
    addEventListener() {},
    removeEventListener() {},
  }
  t.after(() => {
    if (prior === undefined) delete globalThis.window
    else globalThis.window = prior
  })
  const view = await setup()
  t.after(view.stop)
  await view.vm.open('edit', template())
  await settle()
  view.vm.form.basis = 'Unsaved'
  view.vm.editorVisible = false
  assert.equal(view.vm.editor, true)
  assert.equal(confirmations, 1)
  accept = true
  view.vm.editorVisible = false
  assert.equal(view.vm.editor, false)
  await view.vm.open('edit', template())
  assert.equal(view.vm.form.basis, 'Example clause')
  await settle()
  view.vm.form.basis = 'Saved'
  await view.vm.save()
  await settle()
  accept = false
  const before = confirmations
  view.vm.editorVisible = false
  assert.equal(view.vm.editor, false)
  assert.equal(confirmations, before)
})

test('search submit and reset load once, preserve true total and clear the applied route filters', async (t) => {
  const calls = []
  const view = await setup({
    list: async (params) => {
      calls.push({ ...params })
      return { items: [template(params.page)], total: 61 }
    },
  })
  t.after(view.stop)
  view.vm.query = ' Draft '
  await settle()
  assert.equal(calls.length, 1)
  view.vm.page = 2
  await settle()
  view.vm.doSearch()
  await settle()
  assert.equal(calls.length, 3)
  assert.equal(calls.at(-1).page, 1)
  assert.equal(calls.at(-1).q, 'Draft')
  view.vm.changeFilter('builtin')
  await settle()
  view.vm.page = 2
  await settle()
  const before = calls.length
  view.vm.resetSearch()
  await settle()
  assert.equal(calls.length, before + 1)
  assert.equal(view.vm.total, 61)
  assert.deepEqual(view.router.currentRoute.value.query, {})
  assert.equal(view.vm.query, '')
  assert.equal(view.vm.filter, null)
  view.vm.doSearch()
  await settle()
  assert.equal(calls.length, before + 2)
})

test('list read error, no match and out-of-range correction stay independent from editor write errors', async (t) => {
  let fails = true
  const calls = []
  const view = await setup({
    list: async (params) => {
      calls.push(params.page)
      if (fails) throw { code: 'KG.REVISION_CONFLICT' }
      return { items: [], total: 0 }
    },
  })
  t.after(view.stop)
  assert.ok(view.vm.listError)
  assert.equal(view.vm.initialized, true)
  view.vm.error = 'Independent action failure'
  fails = false
  view.vm.page = 8
  await settle()
  await settle()
  assert.deepEqual(calls.slice(-2), [8, 1])
  assert.equal(view.vm.page, 1)
  assert.equal(view.vm.total, 0)
  assert.equal(view.vm.listError, '')
  assert.equal(view.vm.error, 'Independent action failure')
})

test('actual SearchTable remote page two renders all twenty rows with server total and exactly one pagination', async () => {
  const { default: Table } = await loadReal('components/business/SearchTable.vue')
  const messages = JSON.parse(await readFile(path.join(root, 'web/src/locales/en-US.json'), 'utf8'))
  const rows = Array.from({ length: 20 }, (_, i) => ({ id: i + 21, name: `Template${i + 21}` }))
  const html = await renderToString(
    createSSRApp({
      render: () =>
        h(Table, {
          rows,
          columns: [{ key: 'name', title: 'Name' }],
          rowKey: (row) => row.id,
          mode: 'remote',
          total: 61,
          page: 2,
          pageSize: 20,
          searchable: false,
        }),
    }).use(createI18n({ legacy: false, locale: 'en-US', messages: { 'en-US': messages } })),
  )
  assert.equal((html.match(/data-row-key=/g) ?? []).length, 20)
  assert.match(html, /data-row-key="21"/)
  assert.match(html, /data-row-key="40"/)
  assert.equal((html.match(/class="ui-pagination\b/g) ?? []).length, 1)
  assert.match(html, /aria-current="page"/)
  assert.match(html, /data-testid="pagination-total"[^>]*>\s*61/)
  assert.doesNotMatch(html, /search-panel/)
})
