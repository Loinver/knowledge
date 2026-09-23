import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { mkdir, readFile, unlink } from 'node:fs/promises'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { compileScript, parse } from '@vue/compiler-sfc'
import { build } from 'esbuild'
import { createRenderer, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'

const web = fileURLToPath(new URL('../../../..', import.meta.url))
const exposed =
  'mappings,selectedMappingId,selectedMapping,selectedOntologyId,selectedDatasourceId,mappingName,entityMaps,draftRevision,publishedRevision,catalog,preview,working,notice,actionError,canSaveDraft,canPublish,selectMapping,newMapping,handleSaveDraft,publishMapping,runCompile'
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
  const entryPoint = path.join(web, 'src/views/extraction/MappingWizard.vue')
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
  const app = renderer
    .createApp({ ...view.component, render: () => null })
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
    await vm.selectMapping(2)
    const currentSave = vm.handleSaveDraft()
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
