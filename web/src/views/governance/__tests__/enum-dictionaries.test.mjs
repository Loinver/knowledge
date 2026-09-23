import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { mkdir, readFile, unlink } from 'node:fs/promises'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { setup } from '@css-render/vue3-ssr'
import { compileScript, parse } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import { build } from 'esbuild'
import { createRenderer, createSSRApp, nextTick, reactive } from 'vue'
import { createI18n } from 'vue-i18n'

const web = fileURLToPath(new URL('../../../..', import.meta.url))
const outputDir = path.join(web, 'node_modules/.tmp')
const dictionaryNames =
  'items,total,page,query,search,sort,loading,error,form,saved,showEditor,editorError,editorLoading,revisions,references,historyItem,selectedRevision,openCreate,openEdit,submit,remove,doSearch'
const entityNames =
  'data,error,loading,busy,form,showEditor,editorError,versions,versionsLoading,newerVersion,dictionaryOptions,isDraft,openProperty,submitProperty,removeProperty,changeDictionary,loadDetail'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

const settle = async () => {
  await new Promise((resolve) => setImmediate(resolve))
  await nextTick()
}

const dictionary = (id = 1, revision = 1) => ({
  id,
  revision,
  name: `Status${id}`,
  label_i18n: { 'zh-CN': '状态', 'en-US': 'Status' },
  definition_i18n: { 'zh-CN': '状态定义', 'en-US': 'Status definition' },
  entries: [{ value: 'OPEN', label_i18n: { 'zh-CN': '开放', 'en-US': 'Open' } }],
})
const property = () => ({
  name: 'status',
  datatype: 'enum',
  enum_dict_id: 1,
  enum_dict_revision: 1,
  label_i18n: { 'zh-CN': '状态', 'en-US': 'Status' },
  definition_i18n: {},
  nullable: true,
  default_value: 'OPEN',
})
const entity = (id = 1) => ({
  id,
  name: `Entity${id}`,
  kind: 'ENTITY',
  namespace_id: 1,
  iri: `https://example.org/Entity${id}`,
  status: 'DRAFT',
  current_revision: 3,
  edit_revision: 7,
  label_i18n: {},
  definition_i18n: {},
  data_props: [property()],
  parent_ids: [],
})

async function compileView(name, state, ssr = false) {
  const entryPoint = path.join(web, `src/views/${name}.vue`)
  await mkdir(outputDir, { recursive: true })
  const key = `enum_test_${randomUUID()}`
  globalThis[key] = state
  const outfile = path.join(outputDir, `${key}.mjs`)
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
          name: 'vue-enum-test',
          setup(bundler) {
            bundler.onResolve(
              { filter: /^(vue-router|@\/api\/(entity-types|enum-dictionaries))$/ },
              ({ path }) => ({ path, namespace: 'stub' }),
            )
            bundler.onLoad({ filter: /.*/, namespace: 'stub' }, ({ path: module }) => ({
              contents:
                module === 'vue-router'
                  ? `export const useRoute = () => globalThis[${JSON.stringify(key)}].route; export const useRouter = () => ({push: () => {}})`
                  : module.endsWith('entity-types')
                    ? `export const entityTypesApi = globalThis[${JSON.stringify(key)}].api.entityTypes`
                    : `export const enumDictionariesApi = globalThis[${JSON.stringify(key)}].dictionaries`,
            }))
            bundler.onResolve({ filter: /^@\// }, ({ path: module, kind, resolveDir }) =>
              bundler.resolve(path.join(web, 'src', module.slice(2)), { kind, resolveDir }),
            )
            bundler.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
              const source = await readFile(filename, 'utf8')
              const instrumented =
                ssr || filename !== entryPoint
                  ? source
                  : source.replace(
                      '</script>',
                      `\ndefineExpose({${name.startsWith('governance/') ? dictionaryNames : entityNames}})\n</script>`,
                    )
              const { descriptor } = parse(instrumented, { filename })
              const script = compileScript(descriptor, {
                id: key,
                inlineTemplate: ssr,
                templateOptions: { ssr },
              })
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
  } finally {
    await unlink(outfile).catch(() => {})
  }
}

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

async function mountView(name, overrides = {}) {
  const state = {
    route: reactive({ params: { id: '1' } }),
    api: {
      entityTypes: {
        get: async (id) => entity(id),
        update: async (_id, input) => ({
          ...entity(),
          data_props: input.data_props,
          edit_revision: 8,
        }),
      },
    },
    dictionaries: {
      list: async () => ({ items: [dictionary()], total: 1, page: 1, page_size: 20 }),
      get: async (id) => dictionary(id),
      revisions: async (id) => [dictionary(id, 2), dictionary(id, 1)],
      references: async () => [],
      create: async (input) => ({ ...input, id: 2, revision: 1 }),
      update: async (item, input) => ({ ...input, id: item.id, revision: item.revision + 1 }),
      remove: async () => {},
    },
  }
  Object.assign(state.api.entityTypes, overrides.entityTypes)
  Object.assign(state.dictionaries, overrides.dictionaries)
  const built = await compileView(name, state)
  built.component.render = () => null
  const messages = JSON.parse(await readFile(path.join(web, 'src/locales/en-US.json'), 'utf8'))
  const app = renderer
    .createApp(built.component)
    .use(createI18n({ legacy: false, locale: 'en-US', messages: { 'en-US': messages } }))
  const vm = app.mount({})
  return {
    vm,
    state,
    stop: () => {
      app.unmount()
      built.cleanup()
    },
  }
}

test('obsolete dictionary list successes and errors cannot overwrite the current search or loading state', async () => {
  const calls = []
  const view = await mountView('governance/EnumDictionaries', {
    dictionaries: {
      list: (params, signal) => {
        const request = deferred()
        calls.push({ ...request, params, signal })
        return request.promise
      },
    },
  })
  try {
    view.vm.page = 3
    await nextTick()
    view.vm.search = 'New'
    view.vm.doSearch()
    await nextTick()
    assert.equal(calls.at(-1).params.page, 1)
    assert.equal(calls.at(-1).params.q, 'New')
    assert.equal(calls[0].signal.aborted, true)
    calls[0].reject({ code: 'KG.RESOURCE_NOT_FOUND' })
    calls[1].resolve({ items: [dictionary(99)], total: 100 })
    await settle()
    assert.equal(view.vm.loading, true)
    assert.equal(view.vm.error, '')
    calls[2].resolve({ items: [dictionary(2)], total: 1 })
    await settle()
    assert.equal(view.vm.items[0].id, 2)
    assert.equal(view.vm.loading, false)
  } finally {
    view.stop()
  }
})

test('dictionary editor keeps only the newest opened item, preserves history, and validates duplicate values', async () => {
  const old = deferred()
  const view = await mountView('governance/EnumDictionaries', {
    references: [],
    dictionaries: { get: (id) => (id === 1 ? old.promise : Promise.resolve(dictionary(id, 2))) },
  })
  try {
    const first = view.vm.openEdit(dictionary(1))
    await view.vm.openEdit(dictionary(2))
    old.resolve(dictionary(1))
    await first
    assert.equal(view.vm.saved.id, 2)
    assert.equal(view.vm.form.name, 'Status2')
    view.vm.selectedRevision = 1
    assert.equal(view.vm.historyItem.revision, 1)
    view.vm.form.entries[0].value = 'CHANGED'
    assert.equal(view.vm.historyItem.entries[0].value, 'OPEN')
    view.vm.form.entries.push({ ...view.vm.form.entries[0] })
    await view.vm.submit()
    assert.match(view.vm.editorError, /unique machine value/)
  } finally {
    view.stop()
  }
})

test('dictionary create/update/delete use current saved revision and expose in-use conflicts', async () => {
  const writes = []
  const view = await mountView('governance/EnumDictionaries', {
    dictionaries: {
      create: async (input) => {
        writes.push(['create', input])
        return { ...input, id: 4, revision: 1 }
      },
      update: async (item, input) => {
        writes.push(['update', item.revision, input])
        return { ...input, id: item.id, revision: item.revision + 1 }
      },
      remove: async (item) => {
        writes.push(['remove', item.revision])
        throw { code: 'KG.REVISION_CONFLICT', params: { reason: 'enum_dictionary_in_use' } }
      },
    },
  })
  try {
    view.vm.openCreate()
    const { id: _id, revision: _revision, ...input } = dictionary(4)
    view.vm.form = input
    await view.vm.submit()
    assert.equal(writes[0][0], 'create')
    assert.equal(view.vm.showEditor, false)
    await view.vm.openEdit(dictionary(4, 2))
    await view.vm.submit()
    assert.equal(writes[1][1], 1)
    await view.vm.remove(dictionary(4, 3))
    assert.deepEqual(writes[2], ['remove', 3])
    assert.match(view.vm.error, /cannot be deleted/)
  } finally {
    view.stop()
  }
})

test('property resave pins the original version and sends edit CAS; upgrading validates the default', async () => {
  const writes = []
  const view = await mountView('ontology/EntityDetail', {
    entityTypes: {
      update: async (id, input) => {
        writes.push({ id, input })
        return { ...entity(), data_props: input.data_props, edit_revision: 8 }
      },
    },
    dictionaries: {
      revisions: async () => [
        { ...dictionary(1, 2), entries: [{ value: 'CLOSED', label_i18n: { 'zh-CN': '关闭' } }] },
        dictionary(1, 1),
      ],
    },
  })
  try {
    await settle()
    view.vm.openProperty(view.vm.data.data_props[0])
    await settle()
    assert.equal(view.vm.newerVersion, 2)
    assert.equal(view.vm.form.enum_dict_revision, 1)
    view.vm.submitProperty()
    await settle()
    assert.equal(writes[0].input.data_props[0].enum_dict_revision, 1)
    assert.equal(writes[0].input.if_match, 3)
    assert.equal(writes[0].input.edit_revision, 7)
    view.vm.openProperty(view.vm.data.data_props[0])
    await settle()
    view.vm.form.enum_dict_revision = 2
    view.vm.submitProperty()
    assert.match(view.vm.editorError, /default value is not/)
    assert.equal(writes.length, 1)
    view.vm.form.default_value = 'CLOSED'
    view.vm.submitProperty()
    await settle()
    assert.equal(writes[1].input.data_props[0].enum_dict_revision, 2)
    assert.equal(writes[1].input.edit_revision, 8)
  } finally {
    view.stop()
  }
})

test('new enum properties require explicit version choice and obsolete revision responses are ignored', async () => {
  const old = deferred()
  const view = await mountView('ontology/EntityDetail', {
    dictionaries: {
      revisions: (id) => (id === 1 ? old.promise : Promise.resolve([dictionary(id, 3)])),
    },
  })
  try {
    await settle()
    view.vm.openProperty()
    view.vm.form.name = 'Stage'
    view.vm.form.label_i18n['zh-CN'] = '阶段'
    view.vm.form.datatype = 'enum'
    view.vm.changeDictionary(1)
    view.vm.changeDictionary(2)
    await settle()
    old.resolve([dictionary(1, 7)])
    await settle()
    assert.equal(view.vm.versions[0].id, 2)
    assert.equal(view.vm.form.enum_dict_revision, null)
    view.vm.submitProperty()
    assert.match(view.vm.editorError, /Select a dictionary and pinned revision/)
  } finally {
    view.stop()
  }
})

test('route changes ignore stale entity loads and published properties are read-only', async () => {
  const old = deferred()
  let writes = 0
  const view = await mountView('ontology/EntityDetail', {
    entityTypes: {
      get: (id) =>
        id === 1 ? old.promise : Promise.resolve({ ...entity(id), status: 'PUBLISHED' }),
      update: async () => {
        writes++
      },
    },
  })
  try {
    view.state.route.params.id = '2'
    await settle()
    old.resolve(entity(1))
    await settle()
    assert.equal(view.vm.data.id, 2)
    assert.equal(view.vm.isDraft, false)
    view.vm.openProperty()
    assert.equal(view.vm.showEditor, false)
    view.vm.removeProperty(property())
    assert.equal(writes, 0)
  } finally {
    view.stop()
  }
})

test('property add/remove retain sibling pins and rejected writes leave local data unchanged', async () => {
  const writes = []
  let conflict = false
  const view = await mountView('ontology/EntityDetail', {
    entityTypes: {
      update: async (_id, input) => {
        writes.push(input)
        if (conflict) throw { code: 'KG.REVISION_CONFLICT' }
        return { ...entity(), data_props: input.data_props, edit_revision: 8 }
      },
    },
  })
  try {
    await settle()
    view.vm.openProperty()
    view.vm.form.name = 'Code'
    view.vm.form.label_i18n['zh-CN'] = '编号'
    view.vm.submitProperty()
    await settle()
    assert.equal(writes[0].data_props.length, 2)
    assert.equal(writes[0].data_props[0].enum_dict_revision, 1)
    assert.equal(view.vm.data.data_props.length, 2)
    conflict = true
    view.vm.removeProperty(view.vm.data.data_props[1])
    await settle()
    assert.equal(writes[1].data_props.length, 1)
    assert.equal(writes[1].data_props[0].enum_dict_revision, 1)
    assert.equal(writes[1].edit_revision, 8)
    assert.equal(view.vm.data.data_props.length, 2)
    assert.match(view.vm.error, /Reload before editing/)
    assert.equal(view.vm.busy, false)
  } finally {
    view.stop()
  }
})

test('dictionary API sends If-Match on writes and passes read cancellation to HTTP', async () => {
  const key = `enum_http_${randomUUID()}`
  const calls = []
  globalThis[key] = Object.fromEntries(
    ['get', 'post', 'put', 'delete'].map((method) => [
      method,
      async (...args) => {
        calls.push({ method, args })
        return { data: dictionary(2, 4) }
      },
    ]),
  )
  await mkdir(outputDir, { recursive: true })
  const outfile = path.join(outputDir, `${key}.mjs`)
  try {
    await build({
      entryPoints: [path.join(web, 'src/api/enum-dictionaries.ts')],
      outfile,
      bundle: true,
      platform: 'node',
      format: 'esm',
      logLevel: 'silent',
      plugins: [
        {
          name: 'http-stub',
          setup(bundler) {
            bundler.onResolve({ filter: /^@\/api\/client$/ }, () => ({
              path: 'http',
              namespace: 'stub',
            }))
            bundler.onLoad({ filter: /.*/, namespace: 'stub' }, () => ({
              contents: `export const http = globalThis[${JSON.stringify(key)}]`,
            }))
          },
        },
      ],
    })
    const { enumDictionariesApi } = await import(pathToFileURL(outfile).href)
    const controller = new AbortController()
    const input = dictionary(2, 4)
    await enumDictionariesApi.update(input, input)
    await enumDictionariesApi.remove(input)
    await enumDictionariesApi.list(
      { page: 2, page_size: 20, q: 'x', sort: '-id' },
      controller.signal,
    )
    await enumDictionariesApi.revisions(2, controller.signal)
    await enumDictionariesApi.references(2, controller.signal)
    assert.equal(calls[0].args[0], '/governance/enum-dictionaries/2')
    assert.equal(calls[0].args[2].headers['If-Match'], '4')
    assert.equal(calls[1].args[1].headers['If-Match'], '4')
    assert.equal(calls[2].args[1].params.sort, '-id')
    for (const call of calls.slice(2)) assert.equal(call.args[1].signal, controller.signal)
    assert.equal(calls[3].args[0], '/governance/enum-dictionaries/2/revisions')
    assert.equal(calls[4].args[0], '/governance/enum-dictionaries/2/references')
  } finally {
    delete globalThis[key]
    await unlink(outfile).catch(() => {})
  }
})

test('enum management renders real templates in both locales without untranslated keys', async () => {
  const state = {
    dictionaries: { list: async () => ({ items: [], total: 0 }) },
    route: { params: {} },
  }
  const built = await compileView('governance/EnumDictionaries', state, true)
  try {
    for (const locale of ['zh-CN', 'en-US']) {
      const messages = JSON.parse(
        await readFile(path.join(web, `src/locales/${locale}.json`), 'utf8'),
      )
      const i18n = createI18n({ legacy: false, locale, messages: { [locale]: messages } })
      const app = createSSRApp(built.component).use(i18n)
      setup(app)
      const html = await renderToString(app)
      assert.ok(html.includes(i18n.global.t('enumDictionaries.title')))
      assert.ok(html.includes(i18n.global.t('enumDictionaries.create')))
      assert.doesNotMatch(html, />(enumDictionaries|entityProps)\.[A-Za-z]+</)
      if (locale === 'en-US') assert.doesNotMatch(html, /[\u4e00-\u9fff]/)
    }
  } finally {
    built.cleanup()
  }
})
