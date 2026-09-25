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
  Designer:
    'catalogLoading,catalogError,loading,detail,ontologyId,refs,positions,selectedKey,canEdit,saving,working,loadError,actionError,saveError,needsRefresh,loadCatalog,selectOntology,persist,addToCanvas,removeFromCanvas,publish',
  Domains:
    'items,selected,members,loading,membersLoading,checking,working,canEdit,checkResult,listError,membersError,actionError,needsRefresh,addTypeId,load,select,refreshSelection,addMember,removeMember,publishCheck,publish',
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
const resource = (id, editRevision = 1) => ({
  id,
  name: `Resource${id}`,
  iri: `https://example.org/Resource${id}`,
  label_i18n: { 'en-US': `Resource ${id}`, 'zh-CN': `资源 ${id}` },
  status: 'DRAFT',
  current_revision: 1,
  edit_revision: editRevision,
})
const reference = (id) => ({ id: id + 100, resource_id: id, pinned_revision: 1 })
const member = (id) => ({ id: id + 200, resource_id: id, as_ref: false })
const conflict = { code: 'KG.REVISION_CONFLICT', params: { expected: 1, actual: 2 } }
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
    ontology: {
      list: async () => [resource(1), resource(2)],
      get: async (id) => resource(id),
      refs: async (id) => [reference(id)],
      getCanvas: async (id) => ({ positions: { [id]: { x: id * 10, y: id * 20 } } }),
      saveCanvas: async () => {},
      addRef: async () => {},
      removeRef: async () => {},
      publish: async () => {},
    },
    domains: {
      list: async () => [resource(1), resource(2)],
      get: async (id) => resource(id),
      members: async (id) => [member(id)],
      addMember: async () => {},
      removeMember: async () => {},
      publishCheck: async () => ({ can_publish: true }),
      publish: async () => {},
    },
    entityTypes: { list: async () => [resource(1), resource(2), resource(3)] },
    relations: { list: async () => [] },
    message: { success() {} },
  }
}

async function compileView(name, api, ssr = false) {
  const entryPoint = path.join(web, `src/views/ontology/${name}.vue`)
  const key = `selection_${randomUUID()}`
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
          name: 'selection-test',
          setup(bundler) {
            bundler.onResolve(
              { filter: /^@\/api\/(ontology|domains|entity-types|relations)$/ },
              ({ path }) => ({ path, namespace: 'api-stub' }),
            )
            bundler.onLoad({ filter: /.*/, namespace: 'api-stub' }, ({ path: module }) => {
              const area = module.split('/').at(-1)
              const prop = area === 'entity-types' ? 'entityTypes' : area
              return {
                contents: `export const ${prop}Api = globalThis[${JSON.stringify(key)}].${prop}`,
              }
            })
            bundler.onResolve({ filter: /^naive-ui$/ }, ({ namespace, path }) =>
              namespace === 'message-stub'
                ? { path, external: true }
                : { path, namespace: 'message-stub' },
            )
            bundler.onLoad({ filter: /.*/, namespace: 'message-stub' }, () => ({
              contents: `export * from 'naive-ui'; export const useMessage = () => globalThis[${JSON.stringify(key)}].message`,
            }))
            bundler.onResolve({ filter: /^@\// }, ({ path: module, kind, resolveDir }) =>
              bundler.resolve(path.join(web, 'src', module.slice(2)), { kind, resolveDir }),
            )
            bundler.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
              let source = await readFile(filename, 'utf8')
              if (filename === entryPoint) {
                const instrumentation = ssr
                  ? Object.entries(api.seed ?? {})
                      .map(([field, value]) => `${field}.value = ${JSON.stringify(value)}`)
                      .join('\n')
                  : `defineExpose({${exposed[name]}})`
                source = source.replace('</script>', `${instrumentation}\n</script>`)
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
async function mount(t, name, api = state()) {
  const view = await compileView(name, api)
  const translations = await i18n()
  const app = renderer
    .createApp({ ...view.component, render: () => null })
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

test('designer ignores obsolete successes, errors and loading completion even when reads ignore abort', async (t) => {
  const { vm, api } = await mount(t, 'Designer')
  for (const failure of [false, true]) {
    const requests = []
    api.ontology.get = (id, signal) => {
      const request = { id, signal, ...deferred() }
      requests.push(request)
      return request.promise
    }
    const first = vm.selectOntology(1)
    await settle()
    const second = vm.selectOntology(2)
    await settle()
    assert.equal(requests[0].signal.aborted, true)
    assert.equal(vm.canEdit, false)
    if (failure) {
      requests[0].reject(new Error('obsolete failure'))
      await first
      assert.equal(vm.loading, true)
      assert.equal(vm.loadError, '')
    }
    requests[1].resolve(resource(2))
    await second
    if (!failure) {
      requests[0].resolve(resource(1))
      await first
    }
    assert.equal(vm.ontologyId, 2)
    assert.equal(vm.detail.id, 2)
    assert.deepEqual(vm.positions, { 2: { x: 20, y: 40 } })
    assert.equal(vm.loading, false)
    assert.equal(vm.canEdit, true)
  }
})

test('designer saves captured identity and positions, blocks writes while loading and isolates old save callbacks', async (t) => {
  const { vm, api } = await mount(t, 'Designer')
  const saves = []
  api.ontology.saveCanvas = (id, positions) => {
    const write = { id, positions, ...deferred() }
    saves.push(write)
    return write.promise
  }
  const first = vm.persist()
  vm.positions['1'].x = 999
  const read = deferred()
  api.ontology.get = () => read.promise
  const selecting = vm.selectOntology(2)
  await vm.persist()
  assert.equal(saves.length, 1)
  read.resolve(resource(2))
  await selecting
  const second = vm.persist()
  saves[0].reject(new Error('old save failure'))
  await first
  assert.equal(vm.saving, true)
  assert.equal(vm.saveError, '')
  assert.deepEqual(
    saves.map(({ id, positions }) => ({ id, positions })),
    [
      { id: 1, positions: { 1: { x: 10, y: 20 } } },
      { id: 2, positions: { 2: { x: 20, y: 40 } } },
    ],
  )
  saves[1].resolve()
  await second
  assert.equal(vm.saving, false)
})

test('designer waits for pending writes before returning to the same ontology and recovers from read errors', async (t) => {
  const { vm, api, text } = await mount(t, 'Designer')
  const write = deferred()
  const originalGet = api.ontology.get
  const reads = []
  api.ontology.get = (id) => {
    reads.push(id)
    return originalGet(id)
  }
  api.ontology.saveCanvas = () => write.promise
  const saving = vm.persist()
  await vm.selectOntology(2)
  const returning = vm.selectOntology(1)
  await settle()
  assert.deepEqual(reads, [2])
  assert.equal(vm.canEdit, false)
  write.resolve()
  await Promise.all([saving, returning])
  assert.deepEqual(reads, [2, 1])
  const originalCanvas = api.ontology.getCanvas
  api.ontology.getCanvas = async () => {
    throw new Error('offline')
  }
  await vm.selectOntology(1)
  assert.equal(vm.loadError, text('errors.network'))
  assert.equal(vm.detail, null)
  assert.equal(vm.canEdit, false)
  api.ontology.getCanvas = originalCanvas
  await vm.selectOntology(1)
  assert.equal(vm.loadError, '')
  assert.equal(vm.canEdit, true)
})

test('designer refreshes the complete snapshot before accepting the next edit token and retains data on conflict', async (t) => {
  const { vm, api, text } = await mount(t, 'Designer')
  const read = deferred()
  const calls = []
  api.ontology.addRef = async (...args) => calls.push(args)
  api.ontology.get = async (id) => resource(id, 2)
  api.ontology.refs = () => read.promise
  const adding = vm.addToCanvas(3)
  await settle()
  assert.equal(vm.detail, null)
  assert.equal(vm.canEdit, false)
  await vm.addToCanvas(2)
  assert.deepEqual(calls, [[1, 3, undefined, 1]])
  read.resolve([reference(1), reference(3)])
  await adding
  assert.equal(vm.detail.edit_revision, 2)
  assert.equal(vm.canEdit, true)
  api.ontology.removeRef = async (...args) => {
    calls.push(args)
    throw conflict
  }
  const before = vm.refs.map((item) => ({ ...item }))
  await vm.removeFromCanvas(3)
  assert.deepEqual(calls[1], [1, 103, 2])
  assert.deepEqual(vm.refs, before)
  assert.equal(vm.detail.edit_revision, 2)
  assert.equal(vm.actionError, text('errors.KG.REVISION_CONFLICT', conflict.params))
  assert.equal(vm.needsRefresh, true)
  assert.equal(vm.canEdit, false)
  api.ontology.get = async (id) => resource(id, 3)
  await vm.selectOntology(1)
  const published = []
  api.ontology.publish = async (...args) => published.push(args)
  await vm.publish()
  assert.deepEqual(published, [[1, 3]])
})

test('designer suppresses stale edit conflicts and pending read callbacks after unmount', async (t) => {
  const { vm, api, stop } = await mount(t, 'Designer')
  const write = deferred()
  const published = []
  api.ontology.publish = () => write.promise
  api.message.success = (message) => published.push(message)
  const publishing = vm.publish()
  await vm.selectOntology(2)
  write.reject(conflict)
  await publishing
  assert.equal(vm.actionError, '')
  assert.equal(vm.needsRefresh, false)
  const read = deferred()
  let signal
  api.ontology.get = (_id, value) => {
    signal = value
    return read.promise
  }
  const selecting = vm.selectOntology(1)
  await settle()
  stop()
  assert.equal(signal.aborted, true)
  read.resolve(resource(1))
  await selecting
  assert.equal(vm.detail, null)
  assert.equal(vm.loadError, '')
  assert.equal(vm.loading, true)
  assert.deepEqual(published, [])
})

test('designer catalog errors remain visible and an explicit retry reloads all required resources', async (t) => {
  const api = state()
  api.relations.list = async () => {
    throw new Error('offline')
  }
  const { vm, text } = await mount(t, 'Designer', api)
  assert.equal(vm.catalogError, text('errors.network'))
  assert.equal(vm.canEdit, false)
  api.relations.list = async () => []
  await vm.loadCatalog()
  assert.equal(vm.catalogError, '')
  assert.equal(vm.detail.id, 1)
  assert.equal(vm.canEdit, true)
})

test('domain member reads and publication checks keep only the latest selection', async (t) => {
  const { vm, api } = await mount(t, 'Domains')
  const first = deferred()
  let signal
  api.domains.members = (id, value) => {
    if (id === 1) {
      signal = value
      return first.promise
    }
    return Promise.resolve([member(id)])
  }
  const selecting = vm.select(resource(1))
  await vm.select(resource(2))
  assert.equal(signal.aborted, true)
  first.resolve([member(1)])
  await selecting
  assert.deepEqual(vm.members, [member(2)])
  const checks = []
  api.domains.publishCheck = (id, signal) => {
    const request = { id, signal, ...deferred() }
    checks.push(request)
    return request.promise
  }
  const checking = vm.publishCheck()
  await vm.select(resource(1))
  const newest = vm.publishCheck()
  checks[0].reject(new Error('obsolete check'))
  await checking
  assert.equal(vm.checking, true)
  assert.equal(vm.actionError, '')
  checks[1].resolve({ can_publish: false, member_exists: false })
  await newest
  assert.equal(vm.checkResult.can_publish, false)
  assert.equal(vm.checking, false)
})

test('domain writes capture identity and revision and never refresh a different selection', async (t) => {
  const { vm, api } = await mount(t, 'Domains')
  await vm.select(resource(1, 7))
  vm.addTypeId = 3
  const write = deferred()
  const calls = []
  api.domains.addMember = (...args) => {
    calls.push(args)
    return write.promise
  }
  const adding = vm.addMember()
  await vm.select(resource(2, 8))
  vm.addTypeId = 2
  write.resolve()
  await adding
  assert.deepEqual(calls, [[1, 3, false, 7]])
  assert.equal(vm.selected.id, 2)
  assert.equal(vm.selected.edit_revision, 8)
  assert.equal(vm.addTypeId, 2)
  assert.deepEqual(vm.members, [member(2)])
  assert.equal(vm.working, false)
  const removal = deferred()
  api.domains.removeMember = () => removal.promise
  const removing = vm.removeMember(202)
  await vm.select(resource(1))
  removal.reject(conflict)
  await removing
  assert.equal(vm.actionError, '')
  assert.equal(vm.needsRefresh, false)
})

test('domain edits reload token then members before enabling writes and conflicts require a full refresh', async (t) => {
  const { vm, api, text } = await mount(t, 'Domains')
  await vm.select(resource(1))
  const calls = []
  api.domains.removeMember = async (...args) => calls.push(args)
  api.domains.list = async () => [resource(1, 2), resource(2)]
  const members = deferred()
  api.domains.members = () => members.promise
  const removing = vm.removeMember(201)
  await settle()
  assert.equal(vm.selected.edit_revision, 2)
  assert.equal(vm.canEdit, false)
  await vm.publish()
  assert.deepEqual(calls, [[1, 201, 1]])
  members.resolve([member(3)])
  await removing
  assert.equal(vm.canEdit, true)
  api.domains.publish = async (...args) => {
    calls.push(args)
    throw conflict
  }
  await vm.publish()
  assert.deepEqual(calls[1], [1, 2])
  assert.deepEqual(vm.members, [member(3)])
  assert.equal(vm.selected.edit_revision, 2)
  assert.equal(vm.actionError, text('errors.KG.REVISION_CONFLICT', conflict.params))
  assert.equal(vm.canEdit, false)
  api.domains.list = async () => [resource(1, 3), resource(2)]
  await vm.refreshSelection()
  assert.equal(vm.selected.edit_revision, 3)
  assert.equal(vm.actionError, '')
  assert.equal(vm.canEdit, true)
})

test('returning to a domain waits for its pending write and obtains a fresh token before members', async (t) => {
  const api = state()
  const write = deferred()
  let revision = 1
  api.domains.list = async () => [resource(1, revision), resource(2)]
  api.domains.publish = async () => {
    await write.promise
    revision = 2
  }
  const reads = []
  api.domains.members = async (id) => {
    reads.push(id)
    return [member(id)]
  }
  const { vm } = await mount(t, 'Domains', api)
  await vm.select(resource(1))
  const publishing = vm.publish()
  await vm.select(resource(2))
  const returning = vm.select(resource(1))
  await settle()
  assert.deepEqual(reads, [1, 2])
  assert.equal(vm.canEdit, false)
  write.resolve()
  await Promise.all([publishing, returning])
  assert.deepEqual(reads, [1, 2, 1])
  assert.equal(vm.selected.edit_revision, 2)
  assert.equal(vm.canEdit, true)
})

test('domain list failures are visible and obsolete requests cannot finish a newer retry', async (t) => {
  const api = state()
  api.domains.list = async () => {
    throw new Error('offline')
  }
  const { vm, text } = await mount(t, 'Domains', api)
  assert.equal(vm.listError, text('errors.network'))
  const requests = []
  api.domains.list = (_params, signal) => {
    const request = { signal, ...deferred() }
    requests.push(request)
    return request.promise
  }
  const first = vm.load()
  const second = vm.load()
  assert.equal(requests[0].signal.aborted, true)
  requests[0].reject(new Error('obsolete list failure'))
  await first
  assert.equal(vm.loading, true)
  assert.equal(vm.listError, '')
  requests[1].resolve([resource(2)])
  await second
  assert.deepEqual(vm.items, [resource(2)])
  assert.equal(vm.loading, false)
})

test('domain failures recover and obsolete member failures cannot finish a newer load or update an unmounted view', async (t) => {
  const { vm, api, text, stop } = await mount(t, 'Domains')
  api.domains.members = async () => {
    throw new Error('offline')
  }
  await vm.select(resource(1))
  assert.equal(vm.membersError, text('errors.network'))
  assert.equal(vm.canEdit, false)
  api.domains.members = async (id) => [member(id)]
  await vm.refreshSelection()
  assert.equal(vm.membersError, '')
  assert.equal(vm.canEdit, true)
  const requests = []
  api.domains.members = (id, signal) => {
    const request = { id, signal, ...deferred() }
    requests.push(request)
    return request.promise
  }
  const first = vm.select(resource(1))
  const second = vm.select(resource(2))
  requests[0].reject(new Error('obsolete failure'))
  await first
  assert.equal(vm.membersLoading, true)
  assert.equal(vm.membersError, '')
  stop()
  assert.equal(requests[1].signal.aborted, true)
  requests[1].resolve([member(2)])
  await second
  assert.deepEqual(vm.members, [])
  assert.equal(vm.membersLoading, true)
  assert.equal(vm.membersError, '')
})

test('both pages suppress pending mutation callbacks and follow-up reads after unmount', async (t) => {
  for (const name of ['Designer', 'Domains']) {
    await t.test(name, async (t) => {
      const { vm, api, stop } = await mount(t, name)
      if (name === 'Domains') await vm.select(resource(1))
      const write = deferred()
      const target = name === 'Designer' ? api.ontology : api.domains
      target.publish = () => write.promise
      const followUps = []
      target.get = target.list = async () => followUps.push('unexpected reload')
      const publishing = vm.publish()
      stop()
      write.reject(conflict)
      await publishing
      assert.equal(vm.actionError, '')
      assert.equal(vm.needsRefresh, false)
      assert.equal(vm.working, true)
      assert.deepEqual(followUps, [])
    })
  }
})

test('selection pages render visible errors and translated refresh controls using their real templates', async () => {
  for (const name of ['Designer', 'Domains']) {
    const api = state()
    api.seed =
      name === 'Designer'
        ? { catalogLoading: false, catalogError: 'visible failure' }
        : { loading: false, listError: 'visible failure' }
    const view = await compileView(name, api, true)
    try {
      for (const locale of ['en-US', 'zh-CN']) {
        const translations = await i18n(locale)
        const app = createSSRApp(view.component).use(translations).use(createTestRouter())
        setup(app)
        const html = await renderToString(app)
        assert.match(html, /role="alert"/)
        assert.match(html, /visible failure/)
        assert.ok(html.includes(translations.global.t('graph.refresh')))
        assert.ok(!html.includes(translations.global.t('designer.noOntologyHint')))
      }
    } finally {
      view.cleanup()
    }
  }
})
