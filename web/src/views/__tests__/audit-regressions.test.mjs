import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from './view-harness.mjs'

test('clause table uses its summary contract and editing reads the full detail', async (t) => {
  const brief = {
    id: 7,
    revision: 3,
    standard: 'SYNTHETIC',
    clause_number: '1',
    title_i18n: { 'zh-CN': '合成条款', 'en-US': 'Synthetic clause' },
    appendix_nature: 'NORMATIVE',
    product_fallback: null,
  }
  const detail = deferred()
  const reads = []
  const ctx = await mount(
    'views/governance/StandardClauses.vue',
    {
      '@/api/clauses': {
        clausesApi: {
          list: async () => ({ items: [brief], total: 1 }),
          get: (id) => {
            reads.push(id)
            return detail.promise
          },
        },
      },
    },
    'items,columns,openEdit,form,saved,showEditor,busy',
  )
  t.after(ctx.stop)
  assert.equal(
    ctx.vm.columns.find((column) => column.key === 'title').render(ctx.vm.items[0]),
    'Synthetic clause',
  )
  const editing = ctx.vm.openEdit(ctx.vm.items[0])
  assert.equal(ctx.vm.showEditor, false)
  assert.equal(ctx.vm.busy, true)
  detail.resolve({
    ...brief,
    self_authored_description: { 'zh-CN': '完整说明', 'en-US': 'Complete note' },
  })
  await editing
  assert.deepEqual(reads, [7])
  assert.equal(ctx.vm.saved.revision, 3)
  assert.equal(ctx.vm.form.self_authored_description['en-US'], 'Complete note')
  assert.equal(ctx.vm.showEditor, true)
  assert.equal(ctx.vm.busy, false)
})
test('task creation uses the latest selected mapping revision', async () => {
  const first = deferred(),
    second = deferred(),
    writes = []
  globalThis.window = { setInterval: () => 1, clearInterval: () => {} }
  const ctx = await mount(
    'views/extraction/ExtractionTasks.vue',
    {
      '@/api/extraction': {
        extractionApi: {
          tasks: async () => [],
          createTask: async (p) => {
            writes.push(p)
            return { id: 1 }
          },
        },
      },
      '@/api/mappings': {
        mappingsApi: {
          list: async () => [],
          published: (id) => (id === 1 ? first.promise : second.promise),
        },
      },
      '@/api/datasources': { datasourcesApi: { list: async () => [] } },
    },
    'chooseMapping,selectedMappingId,publishedRevisionId,selectedDatasourceId,canCreate,createTask',
  )
  const a = ctx.vm.chooseMapping(1),
    b = ctx.vm.chooseMapping(2)
  second.resolve({ id: 202 })
  await b
  first.resolve({ id: 101 })
  await a
  ctx.vm.selectedDatasourceId = 9
  assert.equal(ctx.vm.selectedMappingId, 2)
  assert.equal(ctx.vm.publishedRevisionId, 202)
  assert.equal(ctx.vm.canCreate, true)
  await ctx.vm.createTask()
  assert.equal(writes[0].mapping_revision_id, 202)
  ctx.stop()
  delete globalThis.window
})

test('task polling never starts after unmount during initial reads', async () => {
  const initial = deferred(),
    timers = [],
    clears = []
  globalThis.window = {
    setInterval: (fn) => {
      timers.push(fn)
      return timers.length
    },
    clearInterval: (id) => clears.push(id),
  }
  const ctx = await mount(
    'views/extraction/ExtractionTasks.vue',
    {
      '@/api/extraction': { extractionApi: { tasks: () => initial.promise } },
      '@/api/mappings': { mappingsApi: { list: async () => [] } },
      '@/api/datasources': { datasourcesApi: { list: async () => [] } },
    },
    'tasks',
  )
  ctx.stop()
  initial.resolve([])
  await settle()
  assert.equal(timers.length, 0)
  assert.deepEqual(clears, [])
  delete globalThis.window
})

test('ontology editing waits for detail and preserves its definition', async () => {
  const detail = deferred(),
    writes = []
  const row = {
    id: 1,
    name: 'Ontology',
    iri: 'https://example.org/Ontology',
    status: 'DRAFT',
    current_revision: 0,
    edit_revision: 2,
    label_i18n: { 'zh-CN': '本体' },
  }
  const ctx = await mount(
    'views/ontology/Ontologies.vue',
    {
      '@/api/ontology': {
        ontologyApi: {
          list: async () => [row],
          get: () => detail.promise,
          update: async (...args) => {
            writes.push(args)
            return row
          },
        },
      },
    },
    'openEdit,handleSubmit,formData',
  )
  ctx.vm.openEdit(row)
  ctx.vm.formData.labelZh = '改名'
  await ctx.vm.handleSubmit()
  assert.equal(writes.length, 0)
  detail.resolve({ ...row, definition_i18n: { 'zh-CN': '不能丢失的定义' } })
  await settle()
  await ctx.vm.handleSubmit()
  assert.equal(writes[0][1].definition_i18n['zh-CN'], '不能丢失的定义')
  ctx.stop()
})

test('entity fusion reloads for the current entity', async () => {
  const reads = []
  const ctx = await mount(
    'views/graph/GraphEntityDetail.vue',
    {
      '@/api/graph': {
        graphApi: {
          detail: async (iri) => ({ entity: { iri, graph_revision_id: 1, attrs: {} } }),
          entityEvidence: async () => ({ evidences: [] }),
          entityFusion: async (iri) => {
            reads.push(iri)
            return { iri, source_rows: [{ row_key: iri }], conflicts: [] }
          },
        },
      },
    },
    'data,fusion,activeTab,loadFusion',
    '/entities/A',
  )
  ctx.vm.activeTab = 'fusion'
  await settle()
  await ctx.router.push('/entities/B')
  await settle()
  assert.equal(ctx.vm.data.detail.entity.iri, 'B')
  assert.equal(ctx.vm.fusion.iri, 'B')
  ctx.vm.activeTab = 'attrs'
  await settle()
  ctx.vm.activeTab = 'fusion'
  await settle()
  assert.deepEqual(reads, ['A', 'B'])
  ctx.stop()
})

test('failed validation cannot retain another graph report', async () => {
  const ctx = await mount(
    'views/graph/GraphReports.vue',
    {
      '@/api/validation': {
        validationApi: {
          revisions: async () => [],
          validateGraph: async (id) => {
            if (id === 2) throw { code: 'KG.FORBIDDEN' }
            return { report_id: 11 }
          },
          getReport: async () => ({ id: 11, summary: { pass: 1 } }),
          getResults: async () => [{ check_code: 'A01', state: 'PASS' }],
        },
      },
    },
    'selectedGraphId,runValidation,reportId,results,resultsError',
  )
  ctx.vm.selectedGraphId = 1
  await ctx.vm.runValidation()
  await settle()
  ctx.vm.selectedGraphId = 2
  await ctx.vm.runValidation()
  await settle()
  assert.equal(ctx.vm.reportId, null)
  assert.deepEqual(ctx.vm.results, [])
  assert.ok(ctx.vm.resultsError)
  ctx.stop()
})

function designerState() {
  const resource = (id) => ({
    id,
    name: `Resource${id}`,
    iri: `https://example.org/${id}`,
    label_i18n: { 'zh-CN': `资源${id}` },
    status: 'DRAFT',
    current_revision: 0,
    edit_revision: 1,
  })
  const refs = []
  return {
    refs,
    resource,
    stubs: {
      '@/api/ontology': {
        ontologyApi: {
          list: async () => [resource(1), resource(2)],
          get: async (id) => resource(id),
          refs: async () => [...refs],
          getCanvas: async () => ({ positions: {} }),
          saveCanvas: async () => {},
          addRef: async (id, rid) => {
            refs.push({ id: 100 + rid, resource_id: rid })
            return refs.at(-1)
          },
        },
      },
      '@/api/domains': { domainsApi: { list: async () => [], members: async () => [] } },
      '@/api/entity-types': {
        entityTypesApi: { list: async () => [], create: async () => resource(101) },
      },
      '@/api/relations': { relationsApi: { list: async () => [] } },
      '@/api/namespaces': { namespacesApi: { list: async () => [{ id: 1 }] } },
      '@/api/validation': { validationApi: {} },
    },
  }
}

test('designer created resources appear in the canvas catalog', async () => {
  const state = designerState()
  const ctx = await mount(
    'views/ontology/Designer.vue',
    state.stubs,
    'submitCreate,createName,createNamespace,createLabelZh,canEdit,refs,nodes,entityTypes',
  )
  assert.equal(ctx.vm.canEdit, true)
  ctx.vm.createName = 'NewType'
  ctx.vm.createNamespace = 1
  ctx.vm.createLabelZh = '新类型'
  await ctx.vm.submitCreate()
  assert.equal(ctx.vm.refs[0].resource_id, 101)
  assert.equal(ctx.vm.nodes.length, 1)
  assert.equal(ctx.vm.entityTypes.length, 1)
  ctx.stop()
})

test('designer rejects old validation after selecting another ontology', async () => {
  const state = designerState(),
    pending = deferred()
  state.stubs['@/api/validation'].validationApi = {
    validateOntology: () => pending.promise,
    getResults: async () => [{ check_code: 'A01', state: 'PASS' }],
  }
  const ctx = await mount(
    'views/ontology/Designer.vue',
    state.stubs,
    'runValidation,selectOntology,ontologyId,validationReport,validationResults,showValidation',
  )
  assert.equal(ctx.vm.ontologyId, 1)
  const validating = ctx.vm.runValidation()
  await ctx.vm.selectOntology(2)
  pending.resolve({ report_id: 11, ontology_id: 1, summary: { pass: 1 } })
  await validating
  assert.equal(ctx.vm.ontologyId, 2)
  assert.equal(ctx.vm.validationReport, null)
  assert.deepEqual(ctx.vm.validationResults, [])
  assert.equal(ctx.vm.showValidation, false)
  ctx.stop()
})

test('late designer creation cannot attach to a different ontology', async () => {
  const state = designerState(),
    pending = deferred(),
    writes = []
  state.stubs['@/api/entity-types'].entityTypesApi.create = () => pending.promise
  state.stubs['@/api/ontology'].ontologyApi.addRef = async (...args) => writes.push(args)
  const ctx = await mount(
    'views/ontology/Designer.vue',
    state.stubs,
    'submitCreate,selectOntology,showCreate,createName,createNamespace,ontologyId',
  )
  ctx.vm.createName = 'NewType'
  ctx.vm.createNamespace = 1
  ctx.vm.showCreate = true
  const creating = ctx.vm.submitCreate()
  ctx.vm.showCreate = false
  await ctx.vm.selectOntology(2)
  pending.resolve(state.resource(101))
  await creating
  assert.deepEqual(writes, [])
  ctx.stop()
})

test('entity route reuse closes old basic editors and rejects validation that finishes after navigation', async (t) => {
  const validate = deferred()
  const writes = []
  const entity = (id) => ({
    id,
    name: `Entity${id}`,
    label_i18n: { 'zh-CN': `Entity${id}` },
    status: 'DRAFT',
    current_revision: 0,
    edit_revision: 1,
    data_props: [],
  })
  const ctx = await mount(
    'views/ontology/EntityDetail.vue',
    {
      '@/api/entity-types': {
        entityTypesApi: {
          get: async (id) => entity(id),
          list: async () => [],
          usages: async () => ({}),
          update: async (...args) => {
            writes.push(args)
            return entity(args[0])
          },
        },
      },
    },
    'data,openBasicEditor,saveBasic,showBasicEditor,basicFormRef,basicForm',
    '/entities/1',
  )
  t.after(ctx.stop)
  ctx.vm.openBasicEditor()
  ctx.vm.basicForm.labelZh = 'Old edit'
  ctx.vm.basicFormRef = { validate: () => validate.promise }
  const saving = ctx.vm.saveBasic()
  await ctx.router.push('/entities/2')
  await settle()
  validate.resolve()
  await saving
  assert.equal(ctx.vm.data.id, 2)
  assert.equal(ctx.vm.showBasicEditor, false)
  assert.deepEqual(writes, [])
})

test('core resource checks discard results after the requirements change', async (t) => {
  const response = deferred()
  const ctx = await mount(
    'views/governance/components/TemplateCoreCheck.vue',
    {
      '@/api/clauses': {
        clausesApi: { all: async () => [{ id: 1, standard: 'Example', clause_number: '1' }] },
      },
      '@/api/templates': { templatesApi: { coreCheck: () => response.promise } },
    },
    'requirements,check,result',
    '/',
    (source) => source.replace('defineProps<{ templateId: number }>()', '({ templateId: 1 })'),
  )
  t.after(ctx.stop)
  ctx.vm.requirements[0] = { name: 'Person', kind: 'ENTITY', standard_clause_id: 1 }
  const pending = ctx.vm.check()
  ctx.vm.requirements[0].name = 'Missing'
  response.resolve({ template_id: 1, all_core_present: true, items: [] })
  await pending
  assert.equal(ctx.vm.result, null)
})

test('selecting datasource preserves saved draft bindings', async () => {
  const map = {
    id: 1,
    name: 'Existing',
    ontology_id: 1,
    status: 'DRAFT',
    current_revision: 0,
    edit_revision: 0,
  }
  const draft = {
    id: 10,
    mapping_id: 1,
    revision: 0,
    edit_revision: 0,
    entity_maps: [
      {
        entity_type: 'Employee',
        schema: 'main',
        table: 'employees',
        key_fields: ['id'],
        field_maps: [{ target_attr: 'name', source_field: 'name' }],
      },
    ],
    rel_maps: [],
  }
  const ctx = await mount(
    'views/extraction/MappingWizard.vue',
    {
      '@/api/mappings': {
        mappingsApi: { list: async () => [map], get: async () => map, draft: async () => draft },
      },
      '@/api/ontology': {
        ontologyApi: { list: async () => [{ id: 1, status: 'PUBLISHED' }], refs: async () => [] },
      },
      '@/api/datasources': {
        datasourcesApi: { list: async () => [{ id: 1 }] },
        metadataApi: { latest: async () => ({ revision: 1, catalog: { schemas: [] } }) },
      },
      '@/api/entity-types': { entityTypesApi: { list: async () => [] } },
      '@/api/relations': { relationsApi: { list: async () => [] } },
      '@/api/extraction': { extractionApi: {} },
    },
    'selectMapping,chooseDatasource,entityMaps,selectedDatasourceId',
  )
  await ctx.vm.selectMapping(1)
  assert.equal(ctx.vm.entityMaps[0].table, 'employees')
  assert.equal(ctx.vm.selectedDatasourceId, null)
  await ctx.vm.chooseDatasource(1)
  assert.equal(ctx.vm.entityMaps[0].table, 'employees')
  assert.equal(ctx.vm.entityMaps[0].field_maps[0].source_field, 'name')
  assert.deepEqual(ctx.vm.entityMaps[0].key_fields, ['id'])
  ctx.stop()
})

test('late compile cannot authorize publication of an edited draft', async () => {
  const pending = deferred(),
    writes = []
  const mapping = {
    id: 1,
    name: 'Mapping1',
    ontology_id: 1,
    status: 'DRAFT',
    current_revision: 0,
    edit_revision: 0,
  }
  const draft = {
    id: 10,
    mapping_id: 1,
    revision: 0,
    edit_revision: 0,
    entity_maps: [
      {
        entity_type: 'Employee',
        schema: 'main',
        table: 'employees',
        field_maps: [{ target_attr: 'name', source_field: 'name' }],
        key_fields: [],
      },
    ],
    rel_maps: [],
  }
  const ctx = await mount(
    'views/extraction/MappingWizard.vue',
    {
      '@/api/mappings': {
        mappingsApi: {
          list: async () => [mapping],
          get: async () => mapping,
          draft: async () => draft,
          saveDraft: async (id, p) => {
            writes.push(['save', p.draft.entity_maps[0].field_maps[0].source_field])
            return { ...draft, edit_revision: p.if_edit_match + 1 }
          },
          compile: () => pending.promise,
          publish: async () => {
            writes.push(['publish'])
            return { ...draft, revision: 1, edit_revision: 3 }
          },
        },
      },
      '@/api/ontology': {
        ontologyApi: {
          list: async () => [{ id: 1, status: 'PUBLISHED', current_revision: 1 }],
          refs: async () => [],
        },
      },
      '@/api/datasources': { datasourcesApi: { list: async () => [] }, metadataApi: {} },
      '@/api/entity-types': { entityTypesApi: { list: async () => [] } },
      '@/api/relations': { relationsApi: { list: async () => [] } },
      '@/api/extraction': { extractionApi: {} },
    },
    'selectMapping,runCompile,publishMapping,canPublish,entityMaps,catalog,selectedDatasourceId,preview',
  )
  await ctx.vm.selectMapping(1)
  ctx.vm.selectedDatasourceId = 1
  ctx.vm.catalog = { schemas: [{ schema: 'main', tables: [{ name: 'employees', columns: [] }] }] }
  const compiling = ctx.vm.runCompile()
  await settle()
  ctx.vm.entityMaps[0].field_maps[0].source_field = 'unsampled_column'
  await settle()
  assert.equal(ctx.vm.preview, null)
  pending.resolve({ entities: [], relations: [] })
  await compiling
  assert.equal(ctx.vm.canPublish, false)
  await ctx.vm.publishMapping()
  assert.deepEqual(writes, [['save', 'name']])
  ctx.stop()
})
