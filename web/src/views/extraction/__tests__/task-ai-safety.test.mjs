import 'naive-ui'

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

const web = fileURLToPath(new URL('../../../..', import.meta.url))
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
function deferred() {
  let resolve
  let reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

async function mount(t, file, exposed, api, props = {}, role = 'EDITOR') {
  const entry = path.join(web, 'src/views/extraction', file)
  const key = `extraction_${randomUUID()}`
  const outfile = path.join(web, `node_modules/.tmp/${key}.mjs`)
  globalThis[key] = api
  await mkdir(path.dirname(outfile), { recursive: true })
  await build({
    entryPoints: [entry],
    outfile,
    bundle: true,
    platform: 'node',
    format: 'esm',
    packages: 'external',
    logLevel: 'silent',
    plugins: [
      {
        name: 'api-fixture',
        setup(bundler) {
          bundler.onResolve(
            { filter: /^@\/api\/(extraction|mappings|datasources|ai)$/ },
            ({ path }) => ({ path, namespace: 'api-fixture' }),
          )
          bundler.onLoad({ filter: /.*/, namespace: 'api-fixture' }, ({ path: module }) => {
            const name = module.split('/').at(-1)
            return {
              contents: `export const ${name}Api = globalThis[${JSON.stringify(key)}].${name}; export const suggestionPayloadLines = () => [];`,
            }
          })
          bundler.onResolve({ filter: /^@\// }, ({ path: module, kind, resolveDir }) =>
            bundler.resolve(path.join(web, 'src', module.slice(2)), { kind, resolveDir }),
          )
          bundler.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
            let source = await readFile(filename, 'utf8')
            if (filename === entry)
              source = source
                .replace('defineExpose({ generate })', '')
                .replace('</script>', `defineExpose({ ${exposed} })\n</script>`)
            const { descriptor } = parse(source, { filename })
            return {
              contents: compileScript(descriptor, { id: key }).content,
              loader: 'ts',
              resolveDir: path.dirname(filename),
            }
          })
        },
      },
    ],
  })
  const component = (await import(pathToFileURL(outfile).href)).default
  await unlink(outfile)
  const pinia = createPinia()
  pinia.state.value.auth = { user: { id: 1, role } }
  const en = JSON.parse(await readFile(path.join(web, 'src/locales/en-US.json'), 'utf8'))
  const app = renderer
    .createApp({ ...component, render: () => null }, props)
    .use(pinia)
    .use(createI18n({ legacy: false, locale: 'en-US', messages: { 'en-US': en } }))
    .use(createRouter({ history: createMemoryHistory(), routes: [] }))
  const vm = app.mount({})
  let stopped = false
  const stop = () => {
    if (!stopped) app.unmount()
    stopped = true
  }
  t.after(() => {
    stop()
    delete globalThis[key]
  })
  await settle()
  return { vm, stop }
}

async function taskView(t, extraction, role = 'EDITOR') {
  const original = globalThis.window
  globalThis.window = {
    setInterval: () => 1,
    clearInterval() {},
    addEventListener() {},
    removeEventListener() {},
  }
  const view = await mount(
    t,
    'ExtractionTasks.vue',
    'tasks,page,loadTasks,cancelTask,cancellationRequested,notice,canCreate,selectedMappingId,selectedDatasourceId,publishedRevisionId,createTask',
    {
      extraction,
      mappings: { list: async () => [] },
      datasources: { list: async () => [] },
    },
    {},
    role,
  )
  t.after(() => {
    if (original === undefined) delete globalThis.window
    else globalThis.window = original
  })
  return view
}

test('running task cancellation remains requested until the worker confirms cancellation', async (t) => {
  const task = { id: 1, status: 'RUNNING' }
  let state = task
  const { vm } = await taskView(t, { tasks: async () => [state], cancelTask: async () => task })
  await vm.cancelTask(task)
  assert.deepEqual(vm.cancellationRequested, [1])
  assert.equal(vm.tasks[0].status, 'RUNNING')
  state = { ...task, status: 'CANCELLED' }
  await vm.loadTasks()
  assert.deepEqual(vm.cancellationRequested, [])
  assert.equal(vm.tasks[0].status, 'CANCELLED')
})

test('task pagination immediately loads the new page and rejects a late prior page', async (t) => {
  const requests = []
  const { vm } = await taskView(t, {
    tasks: (page, signal) => {
      const request = { page, signal, ...deferred() }
      requests.push(request)
      return request.promise
    },
  })
  vm.page = 2
  await settle()
  assert.equal(requests[0].signal.aborted, true)
  assert.equal(requests[1].page, 2)
  requests[1].resolve([{ id: 2, status: 'RUNNING' }])
  await settle()
  requests[0].resolve([{ id: 1, status: 'SUCCESS' }])
  await settle()
  assert.equal(vm.tasks[0].id, 2)
})

test('viewer cannot create or cancel a task through handlers', async (t) => {
  const writes = []
  const { vm } = await taskView(
    t,
    {
      tasks: async () => [],
      createTask: async () => writes.push('create'),
      cancelTask: async () => writes.push('cancel'),
    },
    'VIEWER',
  )
  vm.selectedMappingId = 1
  vm.selectedDatasourceId = 1
  vm.publishedRevisionId = 10
  assert.equal(vm.canCreate, false)
  await vm.createTask()
  await vm.cancelTask({ id: 1, status: 'PENDING' })
  assert.deepEqual(writes, [])
})

const suggestionProps = {
  kind: 'DOCUMENT_FACTS',
  title: 'Review',
  targetId: 1,
  reviewOnly: true,
  text: 'Source document',
}
const suggestionExposed = 'generate,items,loading,error,selected,toggle,apply,reset'

test('AI late response cannot restore suggestions after source invalidation', async (t) => {
  const response = deferred()
  const { vm } = await mount(
    t,
    'components/ExtractionSuggestions.vue',
    suggestionExposed,
    { ai: { extractDocument: () => response.promise } },
    suggestionProps,
  )
  const pending = vm.generate()
  vm.reset()
  response.resolve([{ id: 1, title: 'Obsolete' }])
  await pending
  assert.deepEqual(vm.items, [])
  assert.equal(vm.loading, false)
})

test('AI source review selection is reversible and never applies document facts', async (t) => {
  const writes = []
  const { vm } = await mount(
    t,
    'components/ExtractionSuggestions.vue',
    suggestionExposed,
    { ai: { extractDocument: async () => [{ id: 1 }], apply: async () => writes.push('apply') } },
    suggestionProps,
  )
  await vm.generate()
  vm.toggle(1)
  assert.deepEqual(vm.selected, [1])
  await vm.apply(1)
  vm.toggle(1)
  assert.deepEqual(vm.selected, [])
  assert.deepEqual(writes, [])
})

test('viewer cannot generate AI suggestions', async (t) => {
  const writes = []
  const { vm } = await mount(
    t,
    'components/ExtractionSuggestions.vue',
    suggestionExposed,
    { ai: { extractDocument: async () => writes.push('generate') } },
    suggestionProps,
    'VIEWER',
  )
  await vm.generate()
  assert.deepEqual(writes, [])
})
