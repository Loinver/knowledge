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

const web = fileURLToPath(new URL('../../../..', import.meta.url))
const exposed = 'page,data,error,loading,reload,downloading,downloadError,download,formatTime'
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

async function compileView(api, ssr = false) {
  const entryPoint = path.join(web, 'src/views/extraction/ExtractionRuns.vue')
  const key = `runs_${randomUUID()}`
  globalThis[key] = api
  const outfile = path.join(web, `node_modules/.tmp/${key}.mjs`)
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
          name: 'run-test',
          setup(bundler) {
            bundler.onResolve({ filter: /^@\/api\/extraction$/ }, ({ path }) => ({
              path,
              namespace: 'api-stub',
            }))
            bundler.onLoad({ filter: /.*/, namespace: 'api-stub' }, () => ({
              contents: `export const extractionApi = globalThis[${JSON.stringify(key)}]`,
            }))
            bundler.onResolve({ filter: /^@\// }, ({ path: module, kind, resolveDir }) =>
              bundler.resolve(path.join(web, 'src', module.slice(2)), { kind, resolveDir }),
            )
            bundler.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
              const source = await readFile(filename, 'utf8')
              const { descriptor } = parse(
                ssr || filename !== entryPoint
                  ? source
                  : source.replace('</script>', `defineExpose({${exposed}})\n</script>`),
                { filename },
              )
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

async function i18n(locale = 'en-US') {
  const messages = JSON.parse(await readFile(path.join(web, `src/locales/${locale}.json`)))
  return createI18n({ legacy: false, locale, messages: { [locale]: messages } })
}

async function mount(t, api) {
  const view = await compileView(api)
  const app = renderer.createApp({ ...view.component, render: () => null }).use(await i18n())
  const vm = app.mount({})
  t.after(() => {
    app.unmount()
    view.cleanup()
  })
  return { app, vm }
}

test('paging aborts obsolete reads and cannot display stale rows', async (t) => {
  const requests = []
  const { vm } = await mount(t, {
    list: (page, signal) => {
      const request = { page, signal, ...deferred() }
      requests.push(request)
      return request.promise
    },
  })
  assert.equal(requests[0].page, 1)
  vm.page = 2
  await settle()
  assert.equal(requests[0].signal.aborted, true)
  assert.equal(requests[1].page, 2)
  requests[1].resolve([{ id: 22 }])
  await settle()
  requests[0].resolve([{ id: 1 }])
  await settle()
  assert.deepEqual(vm.data, [{ id: 22 }])
  assert.equal(vm.loading, false)
})

test('list errors are visible and refresh can recover', async (t) => {
  let fails = true
  const { vm } = await mount(t, {
    list: async () => {
      if (fails) throw { code: 'KG.SOURCE_UNREACHABLE' }
      return []
    },
  })
  await settle()
  assert.match(vm.error, /KG.SOURCE_UNREACHABLE/)
  assert.equal(vm.loading, false)
  fails = false
  vm.reload()
  await settle()
  assert.equal(vm.error, '')
  assert.deepEqual(vm.data, [])
})

test('SQLite UTC times render in local timezone while explicit offsets are preserved', async (t) => {
  const previous = process.env.TZ
  process.env.TZ = 'Asia/Shanghai'
  t.after(() => {
    if (previous === undefined) delete process.env.TZ
    else process.env.TZ = previous
  })
  const { vm } = await mount(t, { list: async () => [] })
  const expected = new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Shanghai',
  }).format(new Date('2026-09-23T01:00:00Z'))
  assert.equal(vm.formatTime('2026-09-23T01:00:00'), expected)
  assert.equal(vm.formatTime('2026-09-23T01:00:00Z'), expected)
  assert.equal(vm.formatTime('2026-09-23T09:00:00+08:00'), expected)
})

test('download uses captured run id, suppresses duplicate clicks and releases object URL', async (t) => {
  const request = deferred()
  const calls = []
  const links = []
  const revoked = []
  const timers = []
  const blob = new Blob(['{"run_id":7}'], { type: 'application/json' })
  t.mock.method(URL, 'createObjectURL', (value) => {
    assert.equal(value, blob)
    return 'blob:run-report'
  })
  t.mock.method(URL, 'revokeObjectURL', (url) => revoked.push(url))
  t.mock.method(globalThis, 'setTimeout', (callback) => timers.push(callback))
  const originalDocument = globalThis.document
  globalThis.document = {
    createElement: () => {
      const link = { click: () => links.push({ href: link.href, download: link.download }) }
      return link
    },
  }
  t.after(() => {
    if (originalDocument === undefined) delete globalThis.document
    else globalThis.document = originalDocument
  })
  const { vm } = await mount(t, {
    list: async () => [],
    exportRun: (id) => {
      calls.push(id)
      return request.promise
    },
  })
  const downloading = vm.download(7)
  assert.equal(vm.downloading, 7)
  await vm.download(8)
  vm.page = 2
  request.resolve(blob)
  await downloading
  assert.deepEqual(calls, [7])
  assert.deepEqual(links, [{ href: 'blob:run-report', download: 'run-7.json' }])
  for (const callback of timers) callback()
  assert.deepEqual(revoked, ['blob:run-report'])
  assert.equal(vm.downloading, null)
})

test('download errors recover and navigation cancels a pending download', async (t) => {
  let fails = true
  let signal
  const request = deferred()
  const { app, vm } = await mount(t, {
    list: async () => [],
    exportRun: (_id, currentSignal) => {
      signal = currentSignal
      if (fails) return Promise.reject({ code: 'KG.RESOURCE_NOT_FOUND' })
      return request.promise
    },
  })
  await vm.download(7)
  assert.equal(vm.downloadError, 'KG.RESOURCE_NOT_FOUND')
  assert.equal(vm.downloading, null)
  fails = false
  const downloading = vm.download(7)
  assert.equal(vm.downloadError, '')
  app.unmount()
  assert.equal(signal.aborted, true)
  // Even an API that ignores cancellation must not trigger a download after navigation.
  request.resolve(new Blob(['{}']))
  await downloading
  assert.equal(vm.downloadError, '')
})

test('real template renders bilingual report explanation and page controls', async () => {
  const view = await compileView({ list: async () => [] }, true)
  try {
    for (const locale of ['zh-CN', 'en-US']) {
      const translator = await i18n(locale)
      const app = createSSRApp(view.component).use(translator)
      setup(app)
      const html = await renderToString(app)
      for (const key of ['page.extractionRuns', 'runs.exportNote', 'runs.previous', 'runs.next']) {
        assert.ok(html.includes(translator.global.t(key)))
      }
      assert.doesNotMatch(html, />runs\.[A-Za-z]+</)
      if (locale === 'en-US') assert.doesNotMatch(html, /[\u4e00-\u9fff]/)
      assert.match(html, /disabled/)
    }
  } finally {
    view.cleanup()
  }
})

test('export API produces a JSON file without turning error envelopes into blobs', async (t) => {
  const key = `run_api_${randomUUID()}`
  const payload = { schema_version: 1, run_id: 7, publication: null }
  const calls = []
  const signal = new AbortController().signal
  globalThis[key] = {
    get: async (...args) => {
      calls.push(args)
      return { data: payload }
    },
  }
  t.after(() => delete globalThis[key])
  const result = await build({
    entryPoints: [path.join(web, 'src/api/extraction.ts')],
    bundle: true,
    write: false,
    format: 'esm',
    plugins: [
      {
        name: 'http-stub',
        setup(bundler) {
          bundler.onResolve({ filter: /^@\/api\/client$/ }, ({ path }) => ({
            path,
            namespace: 'stub',
          }))
          bundler.onLoad({ filter: /.*/, namespace: 'stub' }, () => ({
            contents: `export const http = globalThis[${JSON.stringify(key)}]`,
          }))
        },
      },
    ],
  })
  const source = Buffer.from(result.outputFiles[0].text).toString('base64')
  const { extractionApi } = await import(`data:text/javascript;base64,${source}`)
  const blob = await extractionApi.exportRun(7, signal)
  assert.equal(blob.type, 'application/json')
  assert.deepEqual(JSON.parse(await blob.text()), payload)
  assert.deepEqual(calls, [['/extraction/runs/7/export', { signal }]])
  globalThis[key].get = async () => {
    throw { code: 'KG.RESOURCE_NOT_FOUND' }
  }
  await assert.rejects(extractionApi.exportRun(999, signal), { code: 'KG.RESOURCE_NOT_FOUND' })
})
