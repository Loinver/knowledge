import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { mkdir, readFile, unlink } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'

import { compileScript, compileTemplate, parse, registerTS } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import { build } from 'esbuild'
import { createSSRApp } from 'vue'
import { createI18n } from 'vue-i18n'

import { compile, deferred, mount, root, settle } from '../testing/view-harness.mjs'
const resolvePackage = createRequire(path.join(root, 'web/package.json'))
registerTS(() => resolvePackage('typescript'))

const entity = (id = 1) => ({
  id,
  name: `Entity${id}`,
  iri: `https://example.org/Entity${id}`,
  namespace_id: 1,
  status: 'DRAFT',
  current_revision: 2,
  edit_revision: 8,
  label_i18n: { 'zh-CN': '实体' },
  definition_i18n: { 'zh-CN': '定义' },
  data_props: [{ name: 'Code', datatype: 'string', nullable: true }],
  parent_ids: [2, 99],
})
const relation = (id = 1) => ({
  id,
  name: `relation${id}`,
  iri: `https://example.org/relation${id}`,
  namespace_id: 1,
  status: 'DRAFT',
  current_revision: 3,
  edit_revision: 11,
  label_i18n: { 'zh-CN': '关系' },
  definition_i18n: { 'zh-CN': '关系定义' },
  domain_spec: {
    type_id: 1,
    role_i18n: { 'en-US': 'Source' },
    cardinality: { min: 1, max: 4, role_label_i18n: { 'en-US': 'Targets per source' } },
  },
  range_spec: { type_id: 2, role_i18n: { 'en-US': 'Target' }, cardinality: { min: 0, max: -1 } },
  inverse_of: 5,
  enable_attributes: false,
  attribute_defs: [],
  union_of: [],
  intersection_of: [],
  owl: { functional: false, inverse_functional: true, symmetric: false, transitive: false },
})
const namespaceStub = { '@/api/namespaces': { namespacesApi: { list: async () => [] } } }

async function mountEntity(t, overrides = {}, role = 'EDITOR') {
  const ctx = await mount(
    'views/semantic-assets/entity-types/EntityTypeDetailPage.vue',
    {
      '@/api/entity-types': {
        entityTypesApi: {
          get: async (id) => entity(id),
          list: async () => [entity(1), entity(2), entity(3)],
          usages: async () => ({}),
          ...overrides,
        },
      },
    },
    'data,basicForm,basicFormRef,basicError,showBasicEditor,openBasicEditor,saveBasic,parentOptions',
    '/entities/1',
    undefined,
    role,
  )
  t.after(ctx.stop)
  return ctx
}
async function mountRelations(t, overrides = {}, role = 'EDITOR') {
  const ctx = await mount(
    'views/semantic-assets/relation-types/RelationTypesPage.vue',
    {
      ...namespaceStub,
      '@/api/entity-types': { entityTypesApi: { list: async () => [entity(1), entity(2)] } },
      '@/api/relations': {
        relationsApi: {
          list: async () => [relation(5)],
          get: async (id) => relation(id),
          ...overrides,
        },
      },
    },
    'openEdit,openCreate,handleEdit,handleCreate,formData,editFormRef,editingDetail,editError,createError,showEdit,showCreate,createRules,editRules,pickLabel,inverseOptions',
    '/',
    undefined,
    role,
  )
  t.after(ctx.stop)
  return ctx
}

test('parent editor snapshots selected parents, permits clearing and preserves data properties', async (t) => {
  const validation = deferred()
  const writes = []
  const ctx = await mountEntity(t, {
    update: async (id, payload) => {
      writes.push({ id, payload })
      return { ...entity(id), ...payload }
    },
  })
  ctx.vm.openBasicEditor()
  assert.deepEqual(ctx.vm.basicForm.parentIds, [2, 99])
  assert.equal(
    ctx.vm.parentOptions.some((item) => item.value === 1),
    false,
  )
  assert.equal(ctx.vm.parentOptions.find((item) => item.value === 99).label, '#99')
  ctx.vm.basicForm.parentIds = [2, 3]
  ctx.vm.basicForm.labelEn = '  '
  ctx.vm.basicFormRef = { validate: () => validation.promise }
  const saving = ctx.vm.saveBasic()
  ctx.vm.basicForm.parentIds.push(99)
  validation.resolve()
  await saving
  assert.deepEqual(writes[0].payload.parent_ids, [2, 3])
  assert.deepEqual(writes[0].payload.label_i18n, { 'zh-CN': '实体' })
  assert.equal(writes[0].payload.if_match, 2)
  assert.equal(writes[0].payload.edit_revision, 8)
  assert.equal('data_props' in writes[0].payload, false)
  assert.deepEqual(ctx.vm.data.data_props, entity().data_props)
  ctx.vm.openBasicEditor()
  ctx.vm.basicForm.parentIds = []
  await ctx.vm.saveBasic()
  assert.deepEqual(writes[1].payload.parent_ids, [])
})

test('parent editor rejects self references and retains the draft after backend conflict errors', async (t) => {
  const writes = []
  const ctx = await mountEntity(t, {
    update: async (...args) => {
      writes.push(args)
      throw { code: 'KG.REVISION_CONFLICT' }
    },
  })
  ctx.vm.openBasicEditor()
  ctx.vm.basicForm.parentIds = [1]
  await ctx.vm.saveBasic()
  assert.deepEqual(writes, [])
  assert.ok(ctx.vm.basicError)
  ctx.vm.basicForm.parentIds = [3]
  await ctx.vm.saveBasic()
  assert.equal(ctx.vm.showBasicEditor, true)
  assert.deepEqual(ctx.vm.basicForm.parentIds, [3])
  assert.ok(ctx.vm.basicError)
})

test('closing and reopening a parent editor invalidates pending form validation', async (t) => {
  const validation = deferred()
  const writes = []
  const ctx = await mountEntity(t, { update: async (...args) => writes.push(args) })
  ctx.vm.openBasicEditor()
  ctx.vm.basicFormRef = { validate: () => validation.promise }
  const saving = ctx.vm.saveBasic()
  ctx.vm.showBasicEditor = false
  ctx.vm.openBasicEditor()
  ctx.vm.basicForm.parentIds = [3]
  validation.resolve()
  await saving
  assert.deepEqual(writes, [])
  assert.deepEqual(ctx.vm.basicForm.parentIds, [3])
})

test('relation edit snapshots semantic fields and preserves endpoint roles without sending unsupported fields', async (t) => {
  const validation = deferred()
  const writes = []
  const ctx = await mountRelations(t, {
    update: async (id, payload) => {
      writes.push({ id, payload })
      return { ...relation(id), ...payload }
    },
  })
  await ctx.vm.openEdit(1)
  assert.equal(ctx.vm.formData.labelEn, '')
  assert.equal(ctx.vm.formData.definitionZh, '关系定义')
  ctx.vm.formData.definitionEn = 'Edited relation definition'
  ctx.vm.formData.domainCardinality.min = 2
  ctx.vm.formData.domainCardinality.max = 5
  ctx.vm.formData.rangeCardinality.max = 7
  ctx.vm.formData.inverseOf = null
  ctx.vm.formData.owl.inverse_functional = false
  ctx.vm.formData.owl.transitive = true
  // Validate asynchronously while nested form objects continue changing.
  ctx.vm.editFormRef = { validate: () => validation.promise }
  const saving = ctx.vm.handleEdit()
  ctx.vm.formData.domainCardinality.min = 9
  ctx.vm.formData.owl.transitive = false
  validation.resolve()
  await saving
  const payload = writes[0].payload
  assert.deepEqual(payload.label_i18n, { 'zh-CN': '关系' })
  assert.equal(payload.definition_i18n['en-US'], 'Edited relation definition')
  assert.deepEqual(payload.domain_spec.cardinality, {
    min: 2,
    max: 5,
    role_label_i18n: { 'en-US': 'Targets per source' },
  })
  assert.deepEqual(payload.domain_spec.role_i18n, { 'en-US': 'Source' })
  assert.equal(payload.range_spec.cardinality.max, 7)
  assert.equal(payload.inverse_of, null)
  assert.equal(payload.owl.transitive, true)
  assert.equal(payload.owl.inverse_functional, false)
  assert.equal(payload.if_match, 3)
  assert.equal(payload.edit_revision, 11)
  assert.equal('enable_attributes' in payload, false)
  assert.equal('union_of' in payload, false)
  assert.equal('intersection_of' in payload, false)
})

test('relation create submits editable cardinality and all OWL flags while keeping blank English absent', async (t) => {
  const writes = []
  const ctx = await mountRelations(t, { create: async (payload) => writes.push(payload) })
  ctx.vm.openCreate()
  Object.assign(ctx.vm.formData, {
    name: 'worksIn',
    namespace_id: 1,
    labelZh: ' 任职 ',
    labelEn: ' ',
    domainType: 1,
    rangeType: 2,
    definitionZh: ' 关系定义 ',
    inverseOf: 5,
  })
  ctx.vm.formData.domainCardinality = { min: 1, max: 2 }
  ctx.vm.formData.owl.functional = true
  assert.equal(ctx.vm.createRules.name[1].pattern.test('worksIn'), true)
  await ctx.vm.handleCreate()
  assert.equal(writes[0].name, 'worksIn')
  assert.deepEqual(writes[0].label_i18n, { 'zh-CN': '任职' })
  assert.deepEqual(writes[0].definition_i18n, { 'zh-CN': '关系定义' })
  assert.deepEqual(writes[0].domain_spec.cardinality, { min: 1, max: 2 })
  assert.deepEqual(writes[0].range_spec.cardinality, { min: 0, max: -1 })
  assert.equal(writes[0].inverse_of, 5)
  assert.deepEqual(writes[0].owl, {
    functional: true,
    inverse_functional: false,
    symmetric: false,
    transitive: false,
  })
})

test('relation editor rejects invalid cardinality and attribute mode conversion before sending writes', async (t) => {
  const writes = []
  const ctx = await mountRelations(t, {
    create: async (...args) => writes.push(args),
    update: async (...args) => writes.push(args),
  })
  await ctx.vm.openEdit(1)
  ctx.vm.formData.enableAttrs = true
  await ctx.vm.handleEdit()
  assert.ok(ctx.vm.editError)
  ctx.vm.formData.enableAttrs = false
  for (const spec of [
    { min: 3, max: 2 },
    { min: -1, max: -1 },
    { min: 0, max: -2 },
    { min: 0.5, max: 1 },
    { min: 0, max: null },
  ]) {
    ctx.vm.formData.domainCardinality = spec
    await ctx.vm.handleEdit()
    assert.ok(ctx.vm.editError)
  }
  ctx.vm.showEdit = false
  ctx.vm.openCreate()
  ctx.vm.formData.rangeCardinality = { min: 2, max: 1 }
  await ctx.vm.handleCreate()
  assert.ok(ctx.vm.createError)
  assert.deepEqual(writes, [])
})

test('relation save rejection retains modified definitions, cardinality and OWL state', async (t) => {
  const ctx = await mountRelations(t, {
    update: async () => {
      throw { code: 'KG.REVISION_CONFLICT' }
    },
  })
  await ctx.vm.openEdit(1)
  ctx.vm.formData.definitionEn = 'Unsaved definition'
  ctx.vm.formData.rangeCardinality.max = 3
  ctx.vm.formData.owl.symmetric = true
  await ctx.vm.handleEdit()
  assert.equal(ctx.vm.showEdit, true)
  assert.equal(ctx.vm.formData.definitionEn, 'Unsaved definition')
  assert.equal(ctx.vm.formData.rangeCardinality.max, 3)
  assert.equal(ctx.vm.formData.owl.symmetric, true)
  assert.ok(ctx.vm.editError)
})

test('viewer and published entity/relationship drafts cannot be edited', async (t) => {
  const viewer = await mountEntity(t, {}, 'VIEWER')
  viewer.vm.openBasicEditor()
  assert.equal(viewer.vm.showBasicEditor, false)
  const published = await mountEntity(t, {
    get: async () => ({ ...entity(), status: 'PUBLISHED' }),
  })
  published.vm.openBasicEditor()
  assert.equal(published.vm.showBasicEditor, false)
  const relationViewer = await mountRelations(t, {}, 'VIEWER')
  await relationViewer.vm.openEdit(1)
  assert.equal(relationViewer.vm.showEdit, false)
  const writes = []
  const relationPublished = await mountRelations(t, {
    get: async () => ({ ...relation(), status: 'PUBLISHED' }),
    update: async (...args) => writes.push(args),
  })
  await relationPublished.vm.openEdit(1)
  await relationPublished.vm.handleEdit()
  assert.deepEqual(writes, [])
})

test('entity creation and ontology creation/editing do not fabricate English labels', async (t) => {
  const entityWrites = []
  const typeCtx = await mount(
    'views/semantic-assets/entity-types/EntityTypesPage.vue',
    {
      ...namespaceStub,
      '@/api/domains': { domainsApi: { list: async () => [] } },
      '@/api/entity-types': {
        entityTypesApi: {
          list: async () => [],
          stats: async () => ({}),
          create: async (payload) => entityWrites.push(payload),
        },
      },
    },
    'showCreate,handleCreate,formData,displayLabel',
  )
  t.after(typeCtx.stop)
  typeCtx.vm.showCreate = true
  Object.assign(typeCtx.vm.formData, {
    name: 'Entity',
    namespace_id: 1,
    labelZh: ' 中文 ',
    labelEn: '',
  })
  await typeCtx.vm.handleCreate()
  assert.deepEqual(entityWrites[0].label_i18n, { 'zh-CN': '中文' })
  assert.equal(typeCtx.vm.displayLabel(entity()), 'Not translated')
  const ontologyWrites = []
  const onto = { ...entity(), name: 'Ontology' }
  const ontoCtx = await mount(
    'views/ontology/ontologies/OntologiesPage.vue',
    {
      '@/api/ontology': {
        ontologyApi: {
          list: async () => [],
          get: async () => onto,
          create: async (payload) => {
            ontologyWrites.push(payload)
            return onto
          },
          update: async (_id, payload) => {
            ontologyWrites.push(payload)
            return onto
          },
        },
      },
    },
    'openCreate,openEdit,handleSubmit,formData,displayLabel',
  )
  t.after(ontoCtx.stop)
  ontoCtx.vm.openCreate()
  Object.assign(ontoCtx.vm.formData, {
    name: 'Ontology',
    iri: onto.iri,
    labelZh: '本体',
    labelEn: ' ',
  })
  await ontoCtx.vm.handleSubmit()
  assert.deepEqual(ontologyWrites[0].label_i18n, { 'zh-CN': '本体' })
  ontoCtx.vm.openEdit(onto)
  await settle()
  await ontoCtx.vm.handleSubmit()
  assert.deepEqual(ontologyWrites[1].label_i18n, { 'zh-CN': '实体' })
  assert.equal(ontoCtx.vm.displayLabel(onto), 'Not translated')
})

test('relation detail renders missing English as untranslated', async (t) => {
  const ctx = await mount(
    'views/semantic-assets/relation-types/RelationTypeDetailPage.vue',
    {
      '@/api/entity-types': { entityTypesApi: { list: async () => [entity()] } },
      '@/api/relations': {
        relationsApi: { get: async () => relation(), usages: async () => ({}) },
      },
    },
    'data,localized,endpointName',
    '/entities/1',
  )
  t.after(ctx.stop)
  assert.equal(ctx.vm.localized(ctx.vm.data.definition_i18n), 'Not translated')
  assert.equal(ctx.vm.endpointName(1), 'Not translated')
})

test('generated API aliases retain validation counts, binding and four states at runtime', async () => {
  const response = {
    report_id: 1,
    target_id: 2,
    target_revision: 3,
    scope: 'ontology',
    summary: { pass: 1, violation: 2, na: 3, not_run: 4 },
    binding: {
      working_draft_id: 'example',
      edit_revision: 8,
      content_digest: 'digest',
      target: 'WORKING',
    },
  }
  const states = ['PASS', 'VIOLATION', 'NA', 'NOT_RUN'].map((state) => ({
    check_code: 'A01',
    state,
  }))
  const calls = []
  const built = await compile('api/validation.ts', {
    '@/api/client': {
      http: {
        post: async (url) => {
          calls.push(url)
          return { data: response }
        },
        get: async (url) => {
          calls.push(url)
          return { data: url.endsWith('/results') ? states : response }
        },
      },
    },
  })
  try {
    assert.equal(await built.mod.validationApi.validateOntology(2), response)
    assert.equal(await built.mod.validationApi.getReport(1), response)
    assert.equal(await built.mod.validationApi.getResults(1), states)
    assert.deepEqual(calls, [
      '/validation/ontologies/2',
      '/validation/reports/1',
      '/validation/reports/1/results',
    ])
  } finally {
    built.cleanup()
  }
})

test('production semantic fields template renders both cardinality directions, definitions, inverse and OWL controls in both locales', async () => {
  const id = `semantic_fields_${randomUUID().replaceAll('-', '')}`
  const filename = path.join(
    root,
    'web/src/views/semantic-assets/relation-types/components/RelationSemanticFields.vue',
  )
  const outfile = path.join(root, 'web/node_modules/.tmp', `${id}.mjs`)
  const { descriptor } = parse(await readFile(filename, 'utf8'), { filename })
  const script = compileScript(descriptor, {
    id,
    inlineTemplate: true,
    templateOptions: { ssr: true },
    fs: { fileExists: existsSync, readFile: (value) => readFileSync(value, 'utf8') },
  })
  try {
    await mkdir(path.dirname(outfile), { recursive: true })
    await build({
      stdin: { contents: script.content, loader: 'ts', resolveDir: path.dirname(filename) },
      outfile,
      bundle: true,
      format: 'esm',
      platform: 'node',
      packages: 'external',
      logLevel: 'silent',
      loader: { '.css': 'empty' },
      plugins: [
        {
          name: 'semantic-fields-sfc',
          setup(bundler) {
            bundler.onResolve({ filter: /^@\// }, ({ path: value, kind, resolveDir }) =>
              bundler.resolve(path.join(root, 'web/src', value.slice(2)), { kind, resolveDir }),
            )
            bundler.onLoad({ filter: /\.vue$/ }, async ({ path: file }) => {
              const { descriptor: child } = parse(await readFile(file, 'utf8'), { filename: file })
              let contents
              if (child.script || child.scriptSetup) {
                contents = compileScript(child, {
                  id,
                  inlineTemplate: true,
                  templateOptions: { ssr: true },
                  fs: { fileExists: existsSync, readFile: (value) => readFileSync(value, 'utf8') },
                }).content
              } else {
                const template = compileTemplate({
                  source: child.template?.content ?? '',
                  filename: file,
                  id,
                  ssr: true,
                })
                if (template.errors.length) throw new Error(template.errors.join('\n'))
                contents = `${template.code}\nexport default {ssrRender}`
              }
              return { contents, loader: 'ts', resolveDir: path.dirname(file) }
            })
          },
        },
      ],
    })
    const component = (await import(pathToFileURL(outfile).href)).default
    for (const locale of ['en-US', 'zh-CN']) {
      const messages = JSON.parse(
        await readFile(path.join(root, `web/src/locales/${locale}.json`), 'utf8'),
      )
      const i18n = createI18n({ legacy: false, locale, messages: { [locale]: messages } })
      const app = createSSRApp(component, {
        definitionZh: '示例定义',
        definitionEn: 'Example definition',
        domainCardinality: { min: 1, max: 3 },
        rangeCardinality: { min: 0, max: -1 },
        inverseOf: 5,
        owl: relation().owl,
        inverseOptions: [{ label: 'Inverse relation', value: 5 }],
        referencesLoading: false,
      })
      app.use(i18n)
      const html = await renderToString(app)
      for (const key of [
        'domainCardinality',
        'rangeCardinality',
        'inverseOf',
        'functional',
        'inverseFunctional',
        'symmetric',
        'transitive',
      ])
        assert.ok(html.includes(messages.relation[key]), key)
      assert.ok(html.includes('Example definition'))
      assert.ok(html.includes('示例定义'))
      assert.ok(html.includes('Inverse relation'))
      assert.equal((html.match(/role="checkbox"/g) ?? []).length, 4)
    }
  } finally {
    await unlink(outfile).catch(() => {})
  }
})
