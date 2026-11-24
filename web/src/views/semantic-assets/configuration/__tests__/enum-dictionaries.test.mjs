import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { mkdir, readFile, unlink } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { compileScript, compileTemplate, parse, registerTS } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import { build } from 'esbuild'
import { createPinia } from 'pinia'
import { createRenderer, createSSRApp, nextTick, reactive } from 'vue'
import { createI18n } from 'vue-i18n'

import {
  mount as mountConfiguration,
  settle as settleConfiguration,
} from './configuration-harness.mjs'

const web = fileURLToPath(new URL('../../../../..', import.meta.url))
const resolvePackage = createRequire(path.join(web, 'package.json'))
registerTS(() => resolvePackage('typescript'))
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

async function compileView(name, state, ssr = false, transform = (source) => source) {
  const views = {
    'governance/EnumDictionaries':
      'semantic-assets/configuration/enum-dictionaries/EnumDictionariesPage',
    'ontology/EntityDetail': 'semantic-assets/entity-types/EntityTypeDetailPage',
    'governance/AssemblyTemplates':
      'semantic-assets/configuration/assembly-templates/AssemblyTemplatesPage',
    'governance/TemplateCoreCheck':
      'semantic-assets/configuration/assembly-templates/components/TemplateCoreCheck',
  }
  const entryPoint = path.join(web, `src/views/${views[name]}.vue`)
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
              {
                filter: /^(vue-router|@\/api\/(entity-types|enum-dictionaries|templates|clauses))$/,
              },
              ({ path }) => ({ path, namespace: 'stub' }),
            )
            bundler.onLoad({ filter: /.*/, namespace: 'stub' }, ({ path: module }) => ({
              contents:
                module === 'vue-router'
                  ? `export const RouterLink = {render: () => null}; export const useRoute = () => { const route = globalThis[${JSON.stringify(key)}].route; if (!route) return {query: {}, params: {}, fullPath: '/'}; route.query ??= {}; return route }; export const useRouter = () => ({push: () => {}, replace: () => {}}); export const onBeforeRouteLeave = () => {}`
                  : module.endsWith('entity-types')
                    ? `export const entityTypesApi = globalThis[${JSON.stringify(key)}].api.entityTypes`
                    : module.endsWith('templates')
                      ? `export const templatesApi = globalThis[${JSON.stringify(key)}].templates`
                      : module.endsWith('clauses')
                        ? `export const clausesApi = globalThis[${JSON.stringify(key)}].clauses`
                        : `export const enumDictionariesApi = globalThis[${JSON.stringify(key)}].dictionaries`,
            }))
            bundler.onResolve({ filter: /^@\// }, ({ path: module, kind, resolveDir }) =>
              bundler.resolve(path.join(web, 'src', module.slice(2)), { kind, resolveDir }),
            )
            bundler.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
              const original = await readFile(filename, 'utf8')
              const source = filename === entryPoint ? transform(original) : original
              const instrumented =
                ssr || filename !== entryPoint
                  ? source
                  : source.replace(
                      '</script>',
                      `\ndefineExpose({${name.startsWith('governance/') ? dictionaryNames : entityNames}})\n</script>`,
                    )
              const { descriptor } = parse(instrumented, { filename })
              if (!descriptor.script && !descriptor.scriptSetup) {
                const compiled = compileTemplate({
                  source: descriptor.template.content,
                  filename,
                  id: key,
                  ssr,
                  ssrCssVars: descriptor.cssVars,
                })
                assert.deepEqual(compiled.errors, [])
                return {
                  contents: `${compiled.code}\nexport default { ${ssr ? 'ssrRender' : 'render'} }`,
                  loader: 'ts',
                  resolveDir: path.dirname(filename),
                }
              }
              const script = compileScript(descriptor, {
                id: key,
                inlineTemplate: ssr,
                templateOptions: { ssr },
                fs: { fileExists: existsSync, readFile: (file) => readFileSync(file, 'utf8') },
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
  const pinia = createPinia()
  pinia.state.value.auth = {
    user: { id: 1, role: 'EDITOR', status: 'ACTIVE', username: 'test_actor' },
  }
  const app = renderer
    .createApp(built.component)
    .use(createI18n({ legacy: false, locale: 'en-US', messages: { 'en-US': messages } }))
    .use(pinia)
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

async function mountDictionarySearch(start) {
  const calls = []
  const view = await mountConfiguration(
    'views/semantic-assets/configuration/enum-dictionaries/EnumDictionariesPage.vue',
    {
      '@/api/enum-dictionaries': {
        enumDictionariesApi: {
          list: async (params) => {
            calls.push({ ...params })
            return { items: [dictionary()], total: 61 }
          },
        },
      },
    },
    'search,query,sort,page,doSearch,clearSearch,resetSearch',
    start,
  )
  return { ...view, calls }
}

test('dictionary reset handler clears query, sort and page in one request and preserves unrelated route state', async (t) => {
  const view = await mountDictionarySearch('/dictionaries?q=Status&sort=-id&page=3&keep=1')
  t.after(view.stop)
  assert.deepEqual(view.calls, [{ page: 3, page_size: 20, q: 'Status', sort: '-id' }])
  view.vm.search = 'Unsubmitted'
  await settleConfiguration()
  assert.equal(view.calls.length, 1)

  view.vm.resetSearch()
  await settleConfiguration()
  assert.equal(view.vm.search, '')
  assert.equal(view.vm.query, '')
  assert.equal(view.vm.sort, 'name')
  assert.equal(view.vm.page, 1)
  assert.equal(view.calls.length, 2)
  assert.deepEqual(view.calls.at(-1), { page: 1, page_size: 20, q: '', sort: 'name' })
  assert.deepEqual(view.router.currentRoute.value.query, { sort: 'name', keep: '1' })
  await settleConfiguration()
  assert.equal(view.calls.length, 2)
})

test('dictionary reset handler requests once for sort alone and never reloads unchanged default conditions', async (t) => {
  const view = await mountDictionarySearch('/dictionaries?sort=-name&keep=1')
  t.after(view.stop)
  assert.equal(view.calls.length, 1)
  view.vm.resetSearch()
  await settleConfiguration()
  assert.equal(view.calls.length, 2)
  assert.deepEqual(view.calls.at(-1), { page: 1, page_size: 20, q: '', sort: 'name' })
  assert.deepEqual(view.router.currentRoute.value.query, { sort: 'name', keep: '1' })

  view.vm.resetSearch()
  await settleConfiguration()
  assert.equal(view.calls.length, 2)
  view.vm.search = 'Unsubmitted'
  view.vm.resetSearch()
  await settleConfiguration()
  assert.equal(view.vm.search, '')
  assert.equal(view.calls.length, 2)
  assert.deepEqual(view.router.currentRoute.value.query, { sort: 'name', keep: '1' })
})

test('dictionary clear and submit handlers retain the original sort and load once per action', async (t) => {
  const view = await mountDictionarySearch('/dictionaries?q=Status&sort=-id&page=3&keep=1')
  t.after(view.stop)
  view.vm.clearSearch()
  await settleConfiguration()
  assert.equal(view.vm.search, '')
  assert.equal(view.vm.query, '')
  assert.equal(view.vm.sort, '-id')
  assert.equal(view.vm.page, 1)
  assert.equal(view.calls.length, 2)
  assert.deepEqual(view.calls.at(-1), { page: 1, page_size: 20, q: '', sort: '-id' })
  assert.deepEqual(view.router.currentRoute.value.query, { sort: '-id', keep: '1' })

  view.vm.search = '  Next  '
  await settleConfiguration()
  assert.equal(view.calls.length, 2)
  view.vm.doSearch()
  await settleConfiguration()
  assert.equal(view.calls.length, 3)
  assert.deepEqual(view.calls.at(-1), { page: 1, page_size: 20, q: 'Next', sort: '-id' })
  assert.deepEqual(view.router.currentRoute.value.query, { q: 'Next', sort: '-id', keep: '1' })
  view.vm.doSearch()
  await settleConfiguration()
  assert.equal(view.calls.length, 4)
  assert.deepEqual(view.calls.at(-1), { page: 1, page_size: 20, q: 'Next', sort: '-id' })
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

test('dictionary repeated saves issue one request and a conflict preserves the editable draft', async () => {
  const response = deferred()
  const writes = []
  const view = await mountView('governance/EnumDictionaries', {
    dictionaries: {
      update: (item, input) => {
        writes.push({ item, input })
        return response.promise
      },
    },
  })
  try {
    await view.vm.openEdit(dictionary())
    view.vm.form.entries[0].value = 'CHANGED'
    const first = view.vm.submit()
    await view.vm.submit()
    assert.equal(writes.length, 1)
    assert.equal(writes[0].item.revision, 1)
    assert.equal(writes[0].input.entries[0].value, 'CHANGED')
    response.reject({ code: 'KG.REVISION_CONFLICT' })
    await first
    assert.equal(view.vm.form.entries[0].value, 'CHANGED')
    assert.equal(view.vm.showEditor, true)
    assert.match(view.vm.editorError, /Close and reopen/)
  } finally {
    view.stop()
  }
})

test('closed dictionary sessions ignore old save completion and release their busy state', async () => {
  const response = deferred()
  const view = await mountView('governance/EnumDictionaries', {
    dictionaries: { update: () => response.promise },
  })
  try {
    await view.vm.openEdit(dictionary())
    const pending = view.vm.submit()
    view.vm.showEditor = false
    await nextTick()
    response.resolve(dictionary(1, 2))
    await pending
    assert.equal(view.vm.showEditor, false)
    assert.equal(view.vm.saved.revision, 1)
    assert.equal(view.vm.editorError, '')
    view.vm.openCreate()
    assert.equal(view.vm.showEditor, true)
    assert.equal(view.vm.saved, null)
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
    await settle()
    await view.vm.submitProperty()
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
    await view.vm.submitProperty()
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
      const pinia = createPinia()
      pinia.state.value.auth = {
        user: { id: 1, role: 'EDITOR', status: 'ACTIVE', username: 'test_actor' },
      }
      const app = createSSRApp(built.component).use(i18n).use(pinia)
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

test('real dictionary and template tables render remote page three without slicing the server page again', async () => {
  for (const name of ['governance/EnumDictionaries', 'governance/AssemblyTemplates']) {
    const record = name.endsWith('EnumDictionaries')
      ? dictionary(41)
      : {
          id: 41,
          name: 'Template41',
          label_i18n: { 'en-US': 'Remote template' },
          source: 'Example policy',
          basis: 'Example clause',
          builtin: false,
          revision: 7,
          reference_count: 0,
          resources: [],
        }
    const state = {
      route: { params: {}, query: { page: '3' } },
      dictionaries: { list: async () => ({ items: [record], total: 61, page: 3, page_size: 20 }) },
      templates: { list: async () => ({ items: [record], total: 61, page: 3, page_size: 20 }) },
    }
    const built = await compileView(name, state, true, (source) =>
      source.replace('</script>', '\nawait load()\n</script>'),
    )
    try {
      const messages = JSON.parse(await readFile(path.join(web, 'src/locales/en-US.json'), 'utf8'))
      const i18n = createI18n({ legacy: false, locale: 'en-US', messages: { 'en-US': messages } })
      const pinia = createPinia()
      pinia.state.value.auth = { user: { id: 1, role: 'EDITOR', status: 'ACTIVE' } }
      const html = await renderToString(createSSRApp(built.component).use(i18n).use(pinia))
      assert.ok(html.includes(record.name))
      assert.ok(html.includes('ui-data-table-td'))
      assert.ok(html.includes('position:sticky;right:0'))
      assert.ok(html.includes(i18n.global.t('assetLedger.resultCount', { count: 61 })))
      if (name.endsWith('EnumDictionaries')) {
        assert.ok(html.includes('search-panel'))
        assert.ok(html.includes('search-table'))
        assert.equal((html.match(/type="search"/g) ?? []).length, 1)
      }
      assert.doesNotMatch(html, /class="n-data-table/)
    } finally {
      built.cleanup()
    }
  }
})

test('core-check real template displays actual conformance states independently of member presence in both locales', async () => {
  for (const state of ['NOT_RUN', 'VIOLATION']) {
    const response = {
      template_id: 1,
      template_revision: 7,
      items: [],
      all_core_present: true,
      enterprise_extension_count: 0,
      coverage: 'REQUESTED_NAME_KIND_ONLY',
      standards_conformance: state,
    }
    const built = await compileView(
      'governance/TemplateCoreCheck',
      { clauses: { all: async () => [] } },
      true,
      (source) =>
        source.replace(
          'ref<CoreCheckResult | null>(null)',
          `ref<CoreCheckResult | null>(${JSON.stringify(response)})`,
        ),
    )
    try {
      for (const locale of ['zh-CN', 'en-US']) {
        const messages = JSON.parse(
          await readFile(path.join(web, `src/locales/${locale}.json`), 'utf8'),
        )
        const i18n = createI18n({ legacy: false, locale, messages: { [locale]: messages } })
        const pinia = createPinia()
        pinia.state.value.auth = { user: { id: 1, role: 'EDITOR', status: 'ACTIVE' } }
        const html = await renderToString(
          createSSRApp(built.component, { templateId: 1 }).use(i18n).use(pinia),
        )
        assert.ok(html.includes(i18n.global.t(`validation.${state}`)))
        assert.doesNotMatch(html, /--alert-color:var\(--status-pass\)/)
        if (state === 'VIOLATION') assert.match(html, /--alert-color:var\(--status-violation\)/)
      }
    } finally {
      built.cleanup()
    }
  }
})
