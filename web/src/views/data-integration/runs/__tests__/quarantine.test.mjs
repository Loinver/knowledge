import assert from 'node:assert/strict'
import { test } from 'node:test'

import { createRenderer, h, ref } from 'vue'
import { createI18n } from 'vue-i18n'

import { compile, deferred, settle } from '../../../../testing/view-harness.mjs'

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

async function mount(t, api) {
  const built = await compile(
    'views/data-integration/runs/components/RunQuarantine.vue',
    { '@/api/graph': { graphApi: api } },
    'data,error,loading,reload,download,exportError',
  )
  const run = ref(1)
  const child = ref()
  const component = { ...built.mod.default, render: () => null }
  const app = renderer
    .createApp({ render: () => h(component, { runId: run.value, ref: child }) })
    .use(createI18n({ legacy: false, locale: 'en-US', messages: {} }))
  app.mount({})
  t.after(() => {
    app.unmount()
    built.cleanup()
  })
  await settle()
  return { run, child, app }
}

test('quarantine changes cancel prior run reads and never accept stale records', async (t) => {
  const requests = []
  const { run, child } = await mount(t, {
    runQuarantine: (id, signal) => {
      const request = { id, signal, ...deferred() }
      requests.push(request)
      return request.promise
    },
  })
  run.value = 2
  await settle()
  assert.equal(requests[0].signal.aborted, true)
  assert.equal(requests[1].id, 2)
  requests[1].resolve([{ id: 22, run_id: 2, field: 'name' }])
  await settle()
  requests[0].resolve([{ id: 11, run_id: 1 }])
  await settle()
  assert.deepEqual(child.value.data, [{ id: 22, run_id: 2, field: 'name' }])
  assert.equal(child.value.loading, false)
})

test('mismatched quarantine fails visibly, blocks export and can recover without masking failure as empty', async (t) => {
  let fails = true
  const { child } = await mount(t, {
    runQuarantine: async () => (fails ? [{ id: 3, run_id: 99 }] : []),
  })
  assert.ok(child.value.error)
  assert.equal(child.value.data, null)
  child.value.download()
  fails = false
  child.value.reload()
  await settle()
  assert.equal(child.value.error, '')
  assert.deepEqual(child.value.data, [])
})

test('quarantine exports only the loaded run records and releases its object URL', async (t) => {
  const rows = [{ id: 7, run_id: 1, row_key: 'example-1', field: 'date' }]
  const links = []
  const revoked = []
  const timers = []
  let blob
  t.mock.method(URL, 'createObjectURL', (value) => {
    blob = value
    return 'blob:quarantine'
  })
  t.mock.method(URL, 'revokeObjectURL', (url) => revoked.push(url))
  t.mock.method(globalThis, 'setTimeout', (callback) => timers.push(callback))
  const original = globalThis.document
  globalThis.document = {
    createElement: () => {
      const link = { click: () => links.push({ href: link.href, download: link.download }) }
      return link
    },
  }
  t.after(() => {
    if (original === undefined) delete globalThis.document
    else globalThis.document = original
  })
  const { child } = await mount(t, { runQuarantine: async () => rows })
  child.value.download()
  assert.equal(blob.type, 'application/json')
  assert.deepEqual(JSON.parse(await blob.text()), { run_id: 1, quarantine: rows })
  assert.deepEqual(links, [{ href: 'blob:quarantine', download: 'run-1-quarantine.json' }])
  for (const callback of timers) callback()
  assert.deepEqual(revoked, ['blob:quarantine'])
})
