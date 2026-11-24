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
import { createRenderer, createSSRApp, h, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'

// Vue's native v-model checks these constructors when updating an input value.
globalThis.Document ??= class {}
globalThis.ShadowRoot ??= class {}

const web = fileURLToPath(new URL('../../../../..', import.meta.url))
const resolvePackage = createRequire(path.join(web, 'package.json'))
registerTS(() => resolvePackage('typescript'))
const exposed = {
  Namespaces: 'auth,items,loading,loadError,actionError,notice,load,remove,deleteBlocker',
  'components/NamespaceCreateModal': 'form,formRef,rules,canWrite,saving,error,submit',
  EntityTypes: 'namespaces,formData,onNamespaceCreated',
}
function node(type, text = '') {
  return {
    type,
    tagName: type.toUpperCase(),
    text,
    props: {},
    children: [],
    parent: null,
    getRootNode() {
      return this.parent?.getRootNode() ?? this
    },
    focus() {},
    listeners: new Map(),
    addEventListener(event, callback) {
      const listeners = this.listeners.get(event) ?? []
      listeners.push(callback)
      this.listeners.set(event, listeners)
    },
    removeEventListener(event, callback) {
      this.listeners.set(
        event,
        (this.listeners.get(event) ?? []).filter((listener) => listener !== callback),
      )
    },
    getAttribute(name) {
      return this.props[name] ?? null
    },
    querySelector(selector) {
      return find(this, (item) => selector.split(',').includes(item.type))[0] ?? null
    },
  }
}
function find(tree, predicate) {
  return [tree, ...tree.children.flatMap((child) => find(child, predicate))].filter(predicate)
}
function contents(tree) {
  return (tree.type === '#comment' ? '' : tree.text) + tree.children.map(contents).join('')
}
const renderer = createRenderer({
  createElement: (type) => node(type),
  createText: (text) => node('#text', text),
  createComment: (text) => node('#comment', text),
  setText: (item, text) => {
    item.text = text
  },
  setElementText: (item, text) => {
    item.text = text
    item.children = []
  },
  parentNode: (item) => item.parent,
  nextSibling: (item) => item.parent?.children[item.parent.children.indexOf(item) + 1] ?? null,
  insert(item, parent, anchor) {
    if (item.parent) item.parent.children.splice(item.parent.children.indexOf(item), 1)
    item.parent = parent
    const index = anchor ? parent.children.indexOf(anchor) : -1
    if (index < 0) parent.children.push(item)
    else parent.children.splice(index, 0, item)
  },
  remove(item) {
    if (item.parent) item.parent.children.splice(item.parent.children.indexOf(item), 1)
  },
  patchProp: (item, key, _old, value) => {
    item.props[key] = value
  },
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
  const views = {
    Namespaces: 'semantic-assets/namespaces/NamespacesPage',
    'components/NamespaceCreateModal': 'semantic-assets/components/NamespaceCreateModal',
    EntityTypes: 'semantic-assets/entity-types/EntityTypesPage',
  }
  const entryPoint = path.join(web, `src/views/${views[name]}.vue`)
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
              if (!descriptor.script && !descriptor.scriptSetup) {
                const template = compileTemplate({
                  source: descriptor.template.content,
                  filename,
                  id: key,
                  ssr,
                  ssrCssVars: descriptor.cssVars,
                })
                assert.deepEqual(template.errors, [])
                return {
                  contents: `${template.code}\nexport default { ${ssr ? 'ssrRender' : 'render'} }`,
                  loader: 'ts',
                  resolveDir: path.dirname(filename),
                }
              }
              const script = compileScript(descriptor, {
                id: key,
                inlineTemplate: ssr || filename !== entryPoint,
                templateOptions: { ssr },
                fs: { fileExists: existsSync, readFile: (file) => readFileSync(file, 'utf8') },
              })
              return {
                contents:
                  script.content +
                  (filename === entryPoint && !ssr
                    ? "\nexport { FormContainer, FormField, UiInput, UiButton } from '@/components/ui'"
                    : ''),
                loader: 'ts',
                resolveDir: path.dirname(filename),
              }
            })
          },
        },
      ],
    })
    const module = await import(pathToFileURL(outfile).href)
    return {
      component: module.default,
      ui: module,
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
function createTestPinia() {
  const pinia = createPinia()
  pinia.state.value.auth = {
    user: { id: 1, role: 'EDITOR', status: 'ACTIVE', username: 'namespace_test_actor' },
  }
  return pinia
}
async function mount(t, name, api = state(), props = {}) {
  const view = await compileView(name, api)
  const translations = await i18n()
  const app = renderer
    .createApp({ ...view.component, render: () => null }, props)
    .use(translations)
    .use(createTestPinia())
    .use(createTestRouter())
  const vm = app.mount(node('root'))
  let stopped = false
  const stop = () => {
    if (!stopped) app.unmount()
    stopped = true
    view.cleanup()
  }
  t.after(stop)
  await settle()
  if (name === 'components/NamespaceCreateModal') {
    // Mount the actual Form/Field/Input/Button consumers with the modal's real rules.
    // The overlay is outside this Node renderer's scope; no validation or primitive is stubbed.
    const { FormContainer, FormField, UiInput, UiButton } = view.ui
    const tree = node('root')
    const fields = [
      ['prefix', 'namespace.prefix', 'namespace.prefixHint'],
      ['iri', 'namespace.iri', 'namespace.iriHint'],
      ['labelZh', 'common.labelZh'],
      ['labelEn', 'common.labelEn'],
    ]
    const formApp = renderer
      .createApp({
        render: () =>
          h('section', {}, [
            h(
              FormContainer,
              {
                id: 'namespace-create-form',
                ref: (instance) => {
                  vm.formRef = instance
                },
                model: vm.form,
                rules: vm.rules,
                disabled: vm.saving || !vm.canWrite,
                onSubmit: () => vm.submit(),
              },
              {
                default: () =>
                  fields.map(([field, label, hint]) =>
                    h(
                      FormField,
                      {
                        path: field,
                        label: translations.global.t(label),
                      },
                      {
                        default: () =>
                          h(UiInput, {
                            value: vm.form[field],
                            'onUpdate:value': (value) => {
                              vm.form[field] = value
                            },
                          }),
                        ...(hint ? { feedback: () => translations.global.t(hint) } : {}),
                      },
                    ),
                  ),
              },
            ),
            h(
              UiButton,
              {
                attrType: 'submit',
                form: 'namespace-create-form',
                loading: vm.saving,
                disabled: !vm.canWrite,
              },
              () => translations.global.t('common.save'),
            ),
          ]),
      })
      .use(translations)
    formApp.mount(tree)
    t.after(() => formApp.unmount())
    await settle()
    return { vm, api, stop, tree, text: translations.global.t }
  }
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

test('namespace deletion cannot publish feedback or restart reads after unmount', async (t) => {
  for (const outcome of ['success', 'failure']) {
    await t.test(outcome, async (t) => {
      const pending = deferred()
      let reads = 0
      const api = state()
      api.namespaces.list = async () => {
        reads++
        return [namespace(3)]
      }
      api.namespaces.remove = () => pending.promise
      const { vm, stop } = await mount(t, 'Namespaces', api)
      const deleting = vm.remove(vm.items[0])
      stop()
      if (outcome === 'success') pending.resolve()
      else pending.reject({ code: 'KG.RESOURCE_IN_USE', params: { count: 3 } })
      await deleting
      assert.equal(reads, 1)
      assert.equal(vm.notice, '')
      assert.equal(vm.actionError, '')
    })
  }
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
  const { vm, tree, text } = await mount(t, 'components/NamespaceCreateModal', api, {
    show: true,
    'onUpdate:show': (value) => shows.push(value),
    onCreated: (value) => created.push(value),
  })
  for (const key of [
    'namespace.prefix',
    'namespace.prefixHint',
    'namespace.iri',
    'namespace.iriHint',
  ]) {
    assert.ok(contents(tree).includes(text(key)), key)
  }
  for (const input of find(tree, (item) => item.type === 'input')) {
    const label = find(tree, (item) => item.type === 'label' && item.props.for === input.props.id)
    assert.equal(label.length, 1, 'each input is linked to its rendered field label')
  }
  await vm.submit()
  await settle()
  assert.deepEqual(calls, [], 'invalid required fields cannot write')
  assert.equal(find(tree, (item) => item.type === 'input' && item.props['aria-invalid']).length, 2)
  const pending = deferred()
  api.namespaces.create = (payload) => {
    calls.push(payload)
    return pending.promise
  }
  vm.form = { prefix: 'kg', iri: 'https://example.org/kg#', labelZh: '', labelEn: '' }
  await settle()
  const first = vm.submit()
  await settle()
  await vm.submit()
  assert.equal(calls.length, 1, 'repeated save cannot issue another request')
  const failedDraft = { ...vm.form }
  pending.reject(new Error('offline'))
  await first
  await settle()
  assert.deepEqual(vm.form, failedDraft, 'failed save retains every draft field')
  assert.equal(vm.error, text('errors.network'))
  assert.deepEqual(shows, [])
  assert.deepEqual(created, [])
  calls.length = 0
  api.namespaces.create = async (payload) => {
    calls.push(payload)
    if (failure) throw failure
    return namespace(5, payload)
  }
  vm.form = { prefix: ' kg ', iri: ' https://example.org/kg# ', labelZh: '', labelEn: '  ' }
  await settle()
  const nativeForm = find(tree, (item) => item.type === 'form')[0]
  await nativeForm.props.onSubmit({ preventDefault() {} })
  await settle()
  assert.equal(calls.length, 1, 'native form validation accepts canonical values exactly once')
  assert.equal(vm.error, text('namespace.duplicatePrefix'))
  assert.deepEqual(
    vm.form,
    {
      prefix: ' kg ',
      iri: ' https://example.org/kg# ',
      labelZh: '',
      labelEn: '  ',
    },
    'the rejected native form retains its complete draft',
  )
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
  await settle()
  await nativeForm.props.onSubmit({ preventDefault() {} })
  await settle()
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
      const app = createSSRApp(view.component)
        .use(translations)
        .use(createTestPinia())
        .use(createTestRouter())
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
