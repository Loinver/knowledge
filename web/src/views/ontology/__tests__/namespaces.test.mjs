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
import { createRenderer, createSSRApp, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'

const web = fileURLToPath(new URL('../../../..', import.meta.url))
const exposed = {
  Namespaces: 'items,loading,loadError,actionError,notice,load,remove,deleteBlocker',
  'components/NamespaceCreateModal': 'form,saving,error,submit',
  EntityTypes: 'namespaces,formData,onNamespaceCreated',
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
const namespace = (id, extra = {}) => ({
  id,
  prefix: `ns${id}`,
  iri: `https://example.org/ns${id}#`,
  protected: false,
  label_i18n: null,
  resource_count: 0,
  ...extra,
})
const settle = async () => {
  await new Promise((resolve) => setImmediate(resolve))
  await nextTick()
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
  return {
    namespaces: {
      list: async () => [],
      create: async (payload) => namespace(9, payload),
      remove: async () => {},
    },
    domains: { list: async () => [] },
    entityTypes: {
      list: async () => [],
      stats: async () => ({ total: 0, published: 0, draft: 0, violation: 0 }),
    },
  }
}

// Compile the real SFC; API modules resolve to per-test stubs instead of HTTP.
async function compileView(name, api, ssr = false) {
  const entryPoint = path.join(web, `src/views/ontology/${name}.vue`)
  const key = `namespaces_${randomUUID()}`
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
          name: 'namespace-test',
          setup(bundler) {
            bundler.onResolve(
              { filter: /^@\/api\/(namespaces|domains|entity-types)$/ },
              ({ path }) => ({ path, namespace: 'api-stub' }),
            )
            bundler.onLoad({ filter: /.*/, namespace: 'api-stub' }, ({ path: module }) => {
              const area = module.split('/').at(-1)
              const prop = area === 'entity-types' ? 'entityTypes' : area
              return {
                contents: `export const ${prop}Api = globalThis[${JSON.stringify(key)}].${prop}`,
              }
            })
            bundler.onResolve({ filter: /^@\// }, ({ path: module, kind, resolveDir }) =>
              bundler.resolve(path.join(web, 'src', module.slice(2)), { kind, resolveDir }),
            )
            bundler.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
              let source = await readFile(filename, 'utf8')
              if (filename === entryPoint && !ssr) {
                source = source.replace('</script>', `defineExpose({${exposed[name]}})\n</script>`)
              }
              const { descriptor } = parse(source, { filename })
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
  } catch (err) {
    delete globalThis[key]
    throw err
  } finally {
    await unlink(outfile).catch(() => {})
  }
}
async function i18n(locale = 'en-US') {
  const messages = JSON.parse(await readFile(path.join(web, `src/locales/${locale}.json`), 'utf8'))
  return createI18n({ legacy: false, locale, messages: { [locale]: messages } })
}
function createTestRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { render: () => null } }],
  })
}
async function mount(t, name, api = state(), props = {}) {
  const view = await compileView(name, api)
  const translations = await i18n()
  const app = renderer
    .createApp({ ...view.component, render: () => null }, props)
    .use(translations)
    .use(createTestRouter())
  const vm = app.mount({})
  let stopped = false
  const stop = () => {
    if (!stopped) app.unmount()
    stopped = true
    view.cleanup()
  }
  t.after(stop)
  await settle()
  return { vm, api, stop, text: translations.global.t }
}

test('namespace list explains blocked deletes and keeps in-use conflicts readable', async (t) => {
  const api = state()
  api.namespaces.list = async () => [
    namespace(1, { protected: true }),
    namespace(2, { resource_count: 3 }),
    namespace(3),
  ]
  const { vm, text } = await mount(t, 'Namespaces', api)
  assert.equal(vm.items.length, 3)
  assert.equal(vm.deleteBlocker(vm.items[0]), text('namespace.protectedHint'))
  assert.equal(vm.deleteBlocker(vm.items[1]), text('namespace.inUseHint', { count: 3 }))
  assert.equal(vm.deleteBlocker(vm.items[2]), '')

  // A stale list can still hit the backend guard; show its count instead of a generic error.
  const inUse = { code: 'KG.RESOURCE_IN_USE', params: { prefix: 'ns3', count: 2 } }
  api.namespaces.remove = async () => {
    throw inUse
  }
  await vm.remove(vm.items[2])
  assert.equal(vm.actionError, text('namespace.inUseHint', { count: 2 }))
  assert.equal(vm.notice, '')

  const removed = []
  api.namespaces.remove = async (id) => removed.push(id)
  api.namespaces.list = async () => [
    namespace(1, { protected: true }),
    namespace(2, { resource_count: 3 }),
  ]
  await vm.remove(vm.items[2])
  assert.deepEqual(removed, [3])
  assert.equal(vm.actionError, '')
  assert.equal(vm.notice, text('namespace.deleted', { prefix: 'ns3' }))
  assert.deepEqual(
    vm.items.map((item) => item.id),
    [1, 2],
  )
})

test('namespace list keeps only the newest result and ignores reads finishing after unmount', async (t) => {
  const { vm, api, stop } = await mount(t, 'Namespaces')
  const requests = []
  api.namespaces.list = (signal) => {
    const request = { signal, ...deferred() }
    requests.push(request)
    return request.promise
  }
  const first = vm.load()
  const second = vm.load()
  assert.equal(requests[0].signal.aborted, true)
  requests[0].reject(new Error('obsolete failure'))
  await first
  assert.equal(vm.loading, true)
  assert.equal(vm.loadError, '')
  requests[1].resolve([namespace(4)])
  await second
  assert.deepEqual(vm.items, [namespace(4)])
  assert.equal(vm.loading, false)

  const pending = vm.load()
  stop()
  assert.equal(requests[2].signal.aborted, true)
  requests[2].resolve([])
  await pending
  assert.deepEqual(vm.items, [namespace(4)])
})

test('namespace modal trims input, omits empty labels and names the duplicated field', async (t) => {
  const shows = []
  const created = []
  const calls = []
  let failure = { code: 'KG.ALREADY_EXISTS', params: { namespace: 'kg', field: 'prefix' } }
  const api = state()
  api.namespaces.create = async (payload) => {
    calls.push(payload)
    if (failure) throw failure
    return namespace(5, payload)
  }
  const { vm, text } = await mount(t, 'components/NamespaceCreateModal', api, {
    show: true,
    'onUpdate:show': (value) => shows.push(value),
    onCreated: (value) => created.push(value),
  })
  vm.form = { prefix: ' kg ', iri: ' https://example.org/kg# ', labelZh: '', labelEn: '  ' }
  await vm.submit()
  assert.equal(vm.error, text('namespace.duplicatePrefix'))
  failure = {
    code: 'KG.ALREADY_EXISTS',
    params: { namespace: 'https://example.org/kg#', field: 'iri' },
  }
  await vm.submit()
  assert.equal(vm.error, text('namespace.duplicateIri'))
  failure = new Error('offline')
  await vm.submit()
  assert.equal(vm.error, text('errors.network'))
  assert.deepEqual(shows, [])
  assert.deepEqual(created, [])
  assert.deepEqual(calls[0], {
    prefix: 'kg',
    iri: 'https://example.org/kg#',
    protected: false,
    label_i18n: null,
  })

  failure = null
  vm.form = { ...vm.form, labelZh: ' 知识 ' }
  await vm.submit()
  assert.deepEqual(calls.at(-1).label_i18n, { 'zh-CN': '知识' })
  assert.equal(vm.error, '')
  assert.equal(vm.saving, false)
  assert.deepEqual(shows, [false])
  assert.deepEqual(
    created.map((item) => item.prefix),
    ['kg'],
  )
})

test('entity type drawer selects a namespace registered in place on an empty system', async (t) => {
  const { vm } = await mount(t, 'EntityTypes')
  assert.deepEqual(vm.namespaces, [])
  vm.onNamespaceCreated(namespace(7))
  assert.deepEqual(
    vm.namespaces.map((item) => item.id),
    [7],
  )
  assert.equal(vm.formData.namespace_id, 7)
})

test('namespace page renders both locales with a registration entry', async () => {
  const view = await compileView('Namespaces', state(), true)
  try {
    for (const locale of ['zh-CN', 'en-US']) {
      const translations = await i18n(locale)
      const app = createSSRApp(view.component).use(translations).use(createTestRouter())
      setup(app)
      const html = await renderToString(app)
      for (const key of ['page.namespaces', 'namespace.description', 'namespace.create']) {
        assert.ok(html.includes(translations.global.t(key)), key)
      }
      assert.doesNotMatch(html, />namespace\.[A-Za-z]+</)
      if (locale === 'en-US') assert.doesNotMatch(html, /[一-鿿]/)
    }
  } finally {
    view.cleanup()
  }
})
