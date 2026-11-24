import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { mkdir, readFile, unlink } from 'node:fs/promises'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { compileScript, parse } from '@vue/compiler-sfc'
import { build } from 'esbuild'
import { createPinia } from 'pinia'
import { createRenderer, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'

const web = fileURLToPath(new URL('../../../../..', import.meta.url))
const exposed =
  'mappings,selectedMappingId,selectedMapping,selectedOntologyId,selectedDatasourceId,mappingName,entityMaps,draftRevision,publishedRevision,catalog,preview,previewSignature,draftSignature,working,notice,actionError,canSaveDraft,canPublish,selectMapping,newMapping,handleSaveDraft,publishMapping,removeMapping,runCompile,copyPublishedMapping,serializeDraft,entityTypes,relationMaps,sampleLimit,metadataRevision,canWrite,auth,previewInvalidated,readOnly,chooseDatasource,selectionFailed,validating,mappingForm,formModel,formRules,step,samplePreview,sampleRows,sampleColumns,sampleQuery,appliedSampleQuery,samplePage,searchSample,resetSampleSearch'
const renderer = createRenderer({
  createElement: () => ({}),
  createText: () => ({}),
  createComment: () => ({}),
  setText() {},
  setElementText() {},
  parentNode: () => null,
  nextSibling: () => null,
  insert() {},
  remove() {},
  patchProp() {},
})
const settle = async () => {
  await new Promise((resolve) => setImmediate(resolve))
  await nextTick()
}
const mapping = (id, editRevision = id - 1) => ({
  id,
  name: `Mapping${id}`,
  ontology_id: 1,
  status: 'DRAFT',
  current_revision: 0,
  edit_revision: editRevision,
})
const draft = (id, editRevision = id - 1) => ({
  id: id * 10,
  mapping_id: id,
  revision: 0,
  onto_version: 0,
  edit_revision: editRevision,
  entity_maps: [
    {
      entity_type: 'Employee',
      schema: 'main',
      table: 'employees',
      field_maps: [{ target_attr: 'name', source_field: `name${id}` }],
      key_fields: [],
    },
  ],
  rel_maps: [],
})
const published = (id, editRevision = 2) => ({
  ...draft(id, editRevision),
  revision: 1,
  onto_version: 1,
})
const conflict = {
  code: 'KG.REVISION_CONFLICT',
  params: { resource: 'Mapping1', expected: 0, actual: 1 },
}
function deferred() {
  let resolve
  let reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
function state() {
  const writes = []
  return {
    writes,
    mappings: {
      list: async () => [mapping(1), mapping(2)],
      get: async (id) => mapping(id),
      draft: async (id) => draft(id),
      saveDraft: async (id, payload) => {
        writes.push(['save', id, payload.if_edit_match])
        return draft(id, payload.if_edit_match + 1)
      },
      publish: async (id, payload) => {
        writes.push(['publish', id, payload.if_edit_match])
        return published(id, payload.if_edit_match + 1)
      },
      compile: async (id) => {
        writes.push(['compile', id])
        return { entities: [], relations: [] }
      },
      remove: async (mapping) => {
        writes.push(['delete', mapping.id, mapping.edit_revision])
      },
    },
    ontology: {
      list: async () => [{ id: 1, name: 'People', status: 'PUBLISHED', current_revision: 1 }],
      refs: async () => [],
    },
    datasources: { list: async () => [] },
    metadata: {},
    entityTypes: { list: async () => [] },
    relations: { list: async () => [] },
    extraction: {},
  }
}

async function compileView(api) {
  const entryPoint = path.join(web, 'src/views/data-integration/mapping/MappingWorkbenchPage.vue')
  const key = `mapping_${randomUUID()}`
  const outfile = path.join(web, `node_modules/.tmp/${key}.mjs`)
  globalThis[key] = api
  await mkdir(path.dirname(outfile), { recursive: true })
  try {
    await build({
      entryPoints: [entryPoint],
      outfile,
      bundle: true,
      platform: 'node',
      format: 'esm',
      packages: 'external',
      logLevel: 'silent',
      plugins: [
        {
          name: 'mapping-test',
          setup(bundler) {
            bundler.onResolve(
              {
                filter:
                  /^@\/api\/(mappings|datasources|ontology|entity-types|relations|extraction)$/,
              },
              ({ path }) => ({ path, namespace: 'api-stub' }),
            )
            bundler.onLoad({ filter: /.*/, namespace: 'api-stub' }, ({ path: module }) => {
              const area = module.split('/').at(-1)
              const prop = area === 'entity-types' ? 'entityTypes' : area
              const api = `globalThis[${JSON.stringify(key)}]`
              return {
                contents: `export const ${prop}Api = ${api}.${prop};${
                  prop === 'datasources' ? `export const metadataApi = ${api}.metadata;` : ''
                }`,
              }
            })
            bundler.onResolve({ filter: /^@\// }, ({ path: module, kind, resolveDir }) =>
              bundler.resolve(path.join(web, 'src', module.slice(2)), { kind, resolveDir }),
            )
            bundler.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
              // This suite observes the page's business actions; real controls have a separate render suite.
              if (filename !== entryPoint) return { contents: 'export default {render:()=>null}' }
              const source = await readFile(filename, 'utf8')
              const { descriptor } = parse(
                filename === entryPoint
                  ? source.replace('</script>', `defineExpose({${exposed}})\n</script>`)
                  : source,
                { filename },
              )
              const script = compileScript(descriptor, { id: key })
              return { contents: script.content, loader: 'ts', resolveDir: path.dirname(filename) }
            })
          },
        },
      ],
    })
    return {
      component: (await import(pathToFileURL(outfile).href)).default,
      cleanup: () => delete globalThis[key],
    }
  } catch (error) {
    delete globalThis[key]
    throw error
  } finally {
    await unlink(outfile).catch(() => {})
  }
}

async function mount(t, api = state()) {
  const view = await compileView(api)
  const messages = JSON.parse(await readFile(path.join(web, 'src/locales/en-US.json'), 'utf8'))
  const translations = createI18n({
    legacy: false,
    locale: 'en-US',
    messages: { 'en-US': messages },
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { render: () => null } }],
  })
  const pinia = createPinia()
  pinia.state.value.auth = { user: { id: 1, role: 'EDITOR' } }
  const app = renderer
    .createApp({ ...view.component, render: () => null })
    .use(pinia)
    .use(translations)
    .use(router)
  const vm = app.mount({})
  let stopped = false
  const stop = () => {
    if (!stopped) app.unmount()
    stopped = true
    view.cleanup()
  }
  t.after(stop)
  await settle()
  await vm.selectMapping(1)
  vm.selectedDatasourceId = 1
  vm.catalog = {
    schemas: [{ schema: 'main', tables: [{ name: 'employees', columns: [] }] }],
  }
  await settle()
  vm.preview = { entities: [], relations: [] }
  vm.previewSignature = vm.draftSignature()
  assert.equal(vm.canSaveDraft, true)
  assert.equal(vm.canPublish, true)
  return { vm, api, stop, text: translations.global.t }
}

test('saving and publishing use the saved mapping and advance only its edit token', async (t) => {
  const { vm, api } = await mount(t)
  await vm.handleSaveDraft()
  assert.equal(vm.selectedMapping.current_revision, 0)
  assert.equal(vm.selectedMapping.edit_revision, 1)
  await vm.publishMapping()
  assert.deepEqual(api.writes, [
    ['save', 1, 0],
    ['save', 1, 1],
    ['publish', 1, 2],
  ])
  assert.equal(vm.publishedRevision.mapping_id, 1)
  assert.equal(vm.selectedMapping.current_revision, 1)
  assert.equal(vm.selectedMapping.edit_revision, 3)
})

test('dirty mapping cancellation retains fields and explicit discard switches context', async (t) => {
  const { vm } = await mount(t)
  const previousWindow = globalThis.window
  let decisions = 0
  globalThis.window = {
    confirm: () => {
      decisions++
      return false
    },
    addEventListener() {},
    removeEventListener() {},
  }
  try {
    vm.entityMaps[0].field_maps[0].source_field = 'unsaved_column'
    await vm.selectMapping(2)
    assert.equal(vm.selectedMappingId, 1)
    assert.equal(vm.entityMaps[0].field_maps[0].source_field, 'unsaved_column')
    vm.newMapping()
    assert.equal(vm.selectedMappingId, 1)
    assert.equal(decisions, 2)
    globalThis.window.confirm = () => true
    await vm.selectMapping(2)
    assert.equal(vm.selectedMappingId, 2)
    assert.equal(vm.entityMaps[0].field_maps[0].source_field, 'name2')
  } finally {
    globalThis.window = previousWindow
  }
})

test('published copy waits for its frozen details and preserves the incremental configuration', async (t) => {
  const { vm, api } = await mount(t)
  const read = deferred()
  const saved = { ...mapping(2), status: 'PUBLISHED', current_revision: 1 }
  api.mappings.get = async () => saved
  api.mappings.published = () => read.promise
  const selection = vm.selectMapping(2)
  await settle()
  vm.copyPublishedMapping()
  assert.equal(vm.selectedMappingId, 2)
  assert.equal(vm.publishedRevision, null)
  const frozen = published(2)
  frozen.entity_maps[0].incremental_field = 'id'
  frozen.entity_maps[0].key_fields = ['id']
  read.resolve(frozen)
  await selection
  vm.copyPublishedMapping()
  assert.equal(vm.selectedMappingId, null)
  assert.equal(vm.mappingName, 'Mapping2Copy')
  assert.equal(vm.selectedOntologyId, 1)
  assert.equal(vm.publishedRevision, null)
  assert.equal(vm.preview, null)
  const copy = vm.serializeDraft()
  assert.equal(copy.entity_maps[0].incremental_field, 'id')
  assert.deepEqual(copy.entity_maps[0].key_fields, ['id'])
  vm.entityMaps[0].field_maps[0].source_field = 'corrected'
  assert.equal(frozen.entity_maps[0].field_maps[0].source_field, 'name2')
  assert.equal(vm.mappings.find((item) => item.id === 2).status, 'PUBLISHED')
  assert.deepEqual(api.writes, [])
})

test('compile followed by publish uses the edit token returned by the first save', async (t) => {
  const { vm, api } = await mount(t)
  await vm.runCompile()
  await vm.publishMapping()
  assert.deepEqual(api.writes, [
    ['save', 1, 0],
    ['compile', 1],
    ['save', 1, 1],
    ['publish', 1, 2],
  ])
  assert.equal(vm.selectedMapping.current_revision, 1)
  assert.equal(vm.selectedMapping.edit_revision, 3)
})

test('deleting a draft mapping sends its edit token and resets the wizard', async (t) => {
  const { vm, api, text } = await mount(t)
  await vm.removeMapping()
  assert.deepEqual(api.writes, [['delete', 1, 0]])
  assert.equal(vm.selectedMappingId, null)
  assert.equal(
    vm.mappings.some((item) => item.id === 1),
    false,
  )
  assert.equal(vm.notice, text('dataAccess.mapping.deleted', { name: 'Mapping1' }))
  assert.equal(vm.working, false)
})

for (const action of ['publishMapping', 'runCompile']) {
  for (const returnToSameId of [false, true]) {
    test(`${action} stops after delayed save when selection changes${returnToSameId ? ' and returns to the same ID' : ''}`, async (t) => {
      const { vm, api } = await mount(t)
      const save = deferred()
      api.mappings.saveDraft = (id, payload) => {
        api.writes.push(['save', id, payload.if_edit_match])
        return save.promise
      }
      const pending = vm[action]()
      await settle()
      await vm.selectMapping(2)
      if (returnToSameId) await vm.selectMapping(1)
      const currentId = returnToSameId ? 1 : 2
      const token = vm.selectedMapping.edit_revision
      save.resolve(draft(1, 1))
      await pending
      assert.deepEqual(api.writes, [['save', 1, 0]])
      assert.equal(vm.selectedMappingId, currentId)
      assert.equal(vm.draftRevision.mapping_id, currentId)
      assert.equal(vm.selectedMapping.edit_revision, token)
      assert.equal(vm.publishedRevision, null)
      assert.equal(vm.actionError, '')
      assert.equal(vm.notice, '')
      assert.equal(vm.working, false)
    })
  }
}

for (const error of [null, conflict, new Error('network error')]) {
  test(`obsolete save ${error ? `failure ${error.code ?? 'network'}` : 'success'} cannot finish the new selection's save`, async (t) => {
    const { vm, api } = await mount(t)
    const saves = [deferred(), deferred()]
    api.mappings.saveDraft = (id) => saves[id - 1].promise
    const oldSave = vm.publishMapping()
    await settle()
    await vm.selectMapping(2)
    const currentSave = vm.handleSaveDraft()
    await settle()
    assert.equal(vm.working, true)
    if (error) saves[0].reject(error)
    else saves[0].resolve(draft(1, 1))
    await oldSave
    assert.equal(vm.working, true)
    assert.equal(vm.actionError, '')
    assert.equal(vm.draftRevision.mapping_id, 2)
    assert.deepEqual(api.writes, [])
    saves[1].resolve(draft(2, 2))
    await currentSave
    assert.equal(vm.working, false)
    assert.equal(vm.selectedMapping.edit_revision, 2)
  })
}

for (const fails of [false, true]) {
  test(`delayed publish ${fails ? 'conflict' : 'success'} cannot change a later selection`, async (t) => {
    const { vm, api } = await mount(t)
    const publishing = deferred()
    api.mappings.publish = (id, payload) => {
      api.writes.push(['publish', id, payload.if_edit_match])
      return publishing.promise
    }
    const pending = vm.publishMapping()
    await settle()
    await vm.selectMapping(2)
    if (fails) publishing.reject(conflict)
    else publishing.resolve(published(1))
    await pending
    assert.deepEqual(api.writes, [
      ['save', 1, 0],
      ['publish', 1, 1],
    ])
    assert.equal(vm.selectedMappingId, 2)
    assert.equal(vm.selectedMapping.status, 'DRAFT')
    assert.equal(vm.draftRevision.mapping_id, 2)
    assert.equal(vm.publishedRevision, null)
    assert.equal(vm.actionError, '')
    assert.equal(vm.notice, '')
  })
}

test('a current save conflict keeps local edits and prevents publishing', async (t) => {
  const { vm, api, text } = await mount(t)
  vm.entityMaps[0].field_maps[0].source_field = 'local_change'
  await settle()
  vm.preview = { entities: [], relations: [] }
  vm.previewSignature = vm.draftSignature()
  api.mappings.saveDraft = async () => {
    throw conflict
  }
  await vm.publishMapping()
  assert.equal(vm.entityMaps[0].field_maps[0].source_field, 'local_change')
  assert.equal(vm.selectedMapping.edit_revision, 0)
  assert.equal(vm.actionError, text('errors.KG.REVISION_CONFLICT', conflict.params))
  assert.equal(vm.working, false)
  assert.equal(vm.publishedRevision, null)
  assert.deepEqual(api.writes, [])
})

for (const phase of ['saveDraft', 'publish']) {
  for (const fails of [false, true]) {
    test(`unmount during ${phase} ignores ${fails ? 'conflicts' : 'success'} and performs no later write`, async (t) => {
      const { vm, api, stop } = await mount(t)
      const request = deferred()
      api.mappings[phase] = (id) => {
        api.writes.push([phase, id])
        return request.promise
      }
      const pending = vm.publishMapping()
      await settle()
      const before = {
        draft: vm.draftRevision,
        token: vm.selectedMapping.edit_revision,
        notice: vm.notice,
        error: vm.actionError,
        writes: [...api.writes],
      }
      stop()
      if (fails) request.reject(conflict)
      else request.resolve(phase === 'saveDraft' ? draft(1, 1) : published(1))
      await pending
      assert.deepEqual(api.writes, before.writes)
      assert.deepEqual(vm.draftRevision, before.draft)
      assert.equal(vm.selectedMapping.edit_revision, before.token)
      assert.equal(vm.publishedRevision, null)
      assert.equal(vm.notice, before.notice)
      assert.equal(vm.actionError, before.error)
    })
  }
}

test('a delayed creation cannot select its mapping after navigating elsewhere', async (t) => {
  const { vm, api } = await mount(t)
  const fields = JSON.parse(JSON.stringify(vm.entityMaps))
  vm.newMapping()
  vm.selectedOntologyId = 1
  vm.mappingName = 'Created'
  vm.entityMaps = fields
  const creating = deferred()
  const draftReads = []
  api.mappings.create = () => creating.promise
  api.mappings.draft = async (id) => {
    draftReads.push(id)
    return draft(id)
  }
  const pending = vm.handleSaveDraft()
  await settle()
  await vm.selectMapping(2)
  creating.resolve(mapping(3, 0))
  await pending
  assert.equal(vm.selectedMappingId, 2)
  assert.equal(vm.draftRevision.mapping_id, 2)
  assert.deepEqual(draftReads, [2])
  assert.equal(
    vm.mappings.some((item) => item.id === 3),
    false,
  )
})

test('published detail never loads live ontology assets or adds new upstream fields', async (t) => {
  const { vm, api } = await mount(t)
  let liveReads = 0
  api.ontology.refs = async () => {
    liveReads++
    throw new Error('live upstream must not be read')
  }
  vm.entityTypes = [{ name: 'Employee', data_props: [{ name: 'newUpstreamField' }] }]
  const frozen = published(2)
  frozen.entity_maps[0].field_maps[0].transform_params = { format: ['frozen'] }
  api.mappings.get = async () => ({ ...mapping(2), status: 'PUBLISHED', current_revision: 1 })
  api.mappings.published = async () => frozen
  await vm.selectMapping(2)
  assert.equal(liveReads, 0)
  assert.equal(vm.actionError, '')
  assert.equal(vm.publishedRevision.onto_version, 1)
  assert.deepEqual(
    vm.entityMaps[0].field_maps.map((field) => field.target_attr),
    ['name'],
  )
  vm.entityMaps[0].field_maps[0].transform_params.format.push('local')
  assert.deepEqual(frozen.entity_maps[0].field_maps[0].transform_params, { format: ['frozen'] })
  assert.equal(vm.canSaveDraft, false)
  assert.equal(vm.canPublish, false)
})

for (const setting of ['sampleLimit', 'metadataRevision']) {
  test(`${setting} changes invalidate preview and publication readiness`, async (t) => {
    const { vm } = await mount(t)
    assert.equal(vm.canPublish, true)
    const before = vm.draftSignature()
    vm[setting] = 42
    assert.notEqual(vm.draftSignature(), before)
    assert.equal(vm.preview, null)
    assert.equal(vm.previewInvalidated, true)
    assert.equal(vm.canPublish, false)
  })
}

test('viewer cannot save, publish, compile or delete even through action handlers', async (t) => {
  const { vm, api } = await mount(t)
  vm.auth.user.role = 'VIEWER'
  assert.equal(vm.canWrite, false)
  assert.equal(vm.readOnly, true)
  await vm.handleSaveDraft()
  await vm.publishMapping()
  await vm.runCompile()
  await vm.removeMapping()
  assert.deepEqual(api.writes, [])
})

test('late preview cannot restore publication readiness after sample scope changes', async (t) => {
  const { vm, api } = await mount(t)
  const result = deferred()
  api.mappings.compile = () => result.promise
  const pending = vm.runCompile()
  await settle()
  vm.sampleLimit = 100
  result.resolve({ entities: [], relations: [], summary: {} })
  await pending
  assert.equal(vm.preview, null)
  assert.equal(vm.canPublish, false)
})

test('returning to the same datasource cannot accept an earlier metadata response', async (t) => {
  const { vm, api } = await mount(t)
  const requests = []
  api.metadata.latest = (id) => {
    const request = { id, ...deferred() }
    requests.push(request)
    return request.promise
  }
  const first = vm.chooseDatasource(1)
  const second = vm.chooseDatasource(2)
  const current = vm.chooseDatasource(1)
  requests[2].resolve({ revision: 3, catalog: { schemas: [] } })
  await current
  requests[1].resolve({ revision: 2, catalog: { schemas: [] } })
  requests[0].resolve({ revision: 1, catalog: { schemas: [] } })
  await Promise.all([first, second])
  assert.equal(vm.metadataRevision, 3)
})

test('missing published revision is an explicit retryable failure without live fallback', async (t) => {
  const { vm, api } = await mount(t)
  api.mappings.get = async () => ({ ...mapping(2), status: 'PUBLISHED', current_revision: 1 })
  api.mappings.published = async () => null
  api.ontology.refs = () => {
    throw new Error('live fallback forbidden')
  }
  await vm.selectMapping(2)
  assert.equal(vm.selectionFailed, true)
  assert.equal(vm.publishedRevision, null)
  assert.equal(vm.entityMaps.length, 0)
  assert.equal(vm.canPublish, false)
})

test('role downgrade during save prevents the subsequent publish request', async (t) => {
  const { vm, api } = await mount(t)
  const response = deferred()
  api.mappings.saveDraft = () => response.promise
  const pending = vm.publishMapping()
  vm.auth.user.role = 'VIEWER'
  response.resolve(draft(1, 1))
  await pending
  assert.deepEqual(api.writes, [])
  assert.equal(vm.publishedRevision, null)
})

for (const [name, invalidate, errorStep] of [
  [
    'mapping name',
    (vm) => {
      vm.mappingName = '  '
    },
    1,
  ],
  [
    'source field',
    (vm) => {
      vm.entityMaps[0].field_maps[0].source_field = null
    },
    3,
  ],
  [
    'default value',
    (vm) => {
      Object.assign(vm.entityMaps[0].field_maps[0], { null_policy: 'DEFAULT', default_value: '  ' })
    },
    3,
  ],
  [
    'sample zero',
    (vm) => {
      vm.sampleLimit = 0
    },
    4,
  ],
  [
    'fusion priority zero',
    (vm) => {
      Object.assign(vm.entityMaps[0], {
        match_keys: ['id'],
        key_fields: ['id'],
        fusion: { priority: 0, null_policy: 'KEEP', conflict_policy: 'PRIORITY' },
      })
    },
    3,
  ],
  [
    'missing fusion',
    (vm) => {
      Object.assign(vm.entityMaps[0], { match_keys: ['id'], key_fields: ['id'], fusion: null })
    },
    3,
  ],
]) {
  test(`invalid ${name} performs zero writes and reveals the failed step`, async (t) => {
    const { vm, api } = await mount(t)
    invalidate(vm)
    const before = vm.serializeDraft()
    await vm.handleSaveDraft()
    await vm.runCompile()
    assert.deepEqual(api.writes, [])
    assert.deepEqual(vm.serializeDraft(), before)
    assert.equal(vm.step, errorStep)
    assert.equal(vm.working, false)
  })
}

test('pending form validation prevents duplicate writes and keeps controls enabled', async (t) => {
  const { vm, api } = await mount(t)
  const validation = deferred()
  vm.mappingForm = { validate: () => validation.promise, restoreValidation() {} }
  const first = vm.handleSaveDraft()
  await settle()
  assert.equal(vm.validating, true)
  assert.equal(vm.working, false)
  await vm.handleSaveDraft()
  await vm.runCompile()
  assert.deepEqual(api.writes, [])
  validation.resolve()
  await first
  assert.deepEqual(api.writes, [['save', 1, 0]])
  assert.equal(vm.validating, false)
})

for (const invalidate of ['selection', 'draft', 'role', 'unmount']) {
  test(`late validation after ${invalidate} cannot start a write`, async (t) => {
    const { vm, api, stop } = await mount(t)
    const validation = deferred()
    vm.mappingForm = { validate: () => validation.promise, restoreValidation() {} }
    const pending = vm.handleSaveDraft()
    await settle()
    if (invalidate === 'selection') {
      await vm.selectMapping(2)
      await vm.selectMapping(1)
    }
    if (invalidate === 'draft') vm.entityMaps[0].field_maps[0].source_field = 'changed'
    if (invalidate === 'role') vm.auth.user.role = 'VIEWER'
    if (invalidate === 'unmount') stop()
    validation.resolve()
    await pending
    assert.deepEqual(api.writes, [])
  })
}

test('sample search applies only on submit, preserves zero false null and resets the page', async (t) => {
  const { vm } = await mount(t)
  vm.samplePreview = {
    columns: [{ name: 'value' }],
    rows: [{ value: 0 }, { value: false }, { value: null }, { value: 'other' }],
    truncated: true,
  }
  await settle()
  vm.sampleQuery = 'false'
  assert.equal(vm.sampleRows.length, 4)
  vm.samplePage = 2
  vm.searchSample('false')
  assert.deepEqual(
    vm.sampleRows.map((row) => row.values.value),
    [false],
  )
  assert.equal(vm.samplePage, 1)
  vm.searchSample('0')
  assert.deepEqual(
    vm.sampleRows.map((row) => row.values.value),
    [0],
  )
  vm.resetSampleSearch()
  assert.deepEqual(
    vm.sampleRows.map((row) => row.values.value),
    [0, false, null, 'other'],
  )
})

test('serialized associative attributes are a detached request snapshot', async (t) => {
  const { vm } = await mount(t)
  vm.relationMaps = [
    {
      mode: 'ASSOCIATIVE',
      attributes: [{ attr: 'amount', field: 'original' }],
      source_candidates: [],
      target_candidates: [],
    },
  ]
  const sent = vm.serializeDraft()
  vm.relationMaps[0].attributes[0].field = 'changed'
  assert.equal(sent.rel_maps[0].attributes[0].field, 'original')
})

test('obsolete validation cannot clear the pending validation of a later mapping', async (t) => {
  const { vm, api } = await mount(t)
  const validations = [deferred(), deferred()]
  vm.mappingForm = { validate: () => validations[0].promise, restoreValidation() {} }
  const old = vm.handleSaveDraft()
  await settle()
  await vm.selectMapping(2)
  vm.mappingForm = { validate: () => validations[1].promise, restoreValidation() {} }
  const current = vm.handleSaveDraft()
  await settle()
  validations[0].resolve()
  await old
  assert.equal(vm.validating, true)
  assert.equal(vm.working, false)
  assert.deepEqual(api.writes, [])
  validations[1].resolve()
  await current
  assert.deepEqual(api.writes, [['save', 2, 1]])
})

test('polymorphic and via endpoint requirements prevent writes until the actual fields are complete', async (t) => {
  const { vm, api } = await mount(t)
  const side = {
    field: '',
    ref_table: '',
    ref_field: 'id',
    type_field: 'kind',
    candidates: [{ field: 'owner', ref_table: 'employees', when: '', ref_entity_type: 'Employee' }],
    via_table: 'employees',
    via_field: '',
    via_ref_field: 'id',
  }
  vm.relationMaps = [
    {
      localId: 2,
      relation_type: 'Owner',
      mode: 'JUNCTION',
      schema: 'main',
      table: 'employees',
      fk_field: '',
      ...Object.fromEntries(Object.entries(side).map(([key, value]) => [`source_${key}`, value])),
      target_field: 'target',
      target_ref_table: 'employees',
      target_ref_field: 'id',
      target_type_field: '',
      target_candidates: [],
      target_via_table: '',
      target_via_field: '',
      target_via_ref_field: 'id',
      attributes: [],
    },
  ]
  await vm.handleSaveDraft()
  assert.deepEqual(api.writes, [])
  vm.relationMaps[0].source_candidates[0].when = 'Employee'
  await vm.handleSaveDraft()
  assert.deepEqual(api.writes, [])
  vm.relationMaps[0].source_via_field = 'owner_id'
  await vm.handleSaveDraft()
  assert.deepEqual(api.writes, [['save', 1, 0]])
})
