import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'

import { build } from 'esbuild'

async function loadApi(t, http) {
  const key = `ontology_api_${randomUUID()}`
  globalThis[key] = http
  t.after(() => delete globalThis[key])
  const result = await build({
    entryPoints: [fileURLToPath(new URL('../ontology.ts', import.meta.url))],
    bundle: true,
    write: false,
    platform: 'node',
    format: 'esm',
    logLevel: 'silent',
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
  return (await import(`data:text/javascript;base64,${source}`)).ontologyApi
}

test('ontology list and exports preserve pagination, file bytes, MIME types and cancellation signals', async (t) => {
  const signal = new AbortController().signal
  const calls = []
  let data = [{ id: 7 }]
  const api = await loadApi(t, {
    get: async (...args) => {
      calls.push(args)
      return { data }
    },
  })
  assert.equal(await api.list({ page: 2, page_size: 200 }, signal), data)
  assert.deepEqual(calls.shift(), ['/ontologies', { params: { page: 2, page_size: 200 }, signal }])

  for (const [format, type, content] of [
    ['turtle', 'text/turtle;charset=utf-8', '<https://example.org/Ontology> a <urn:Ontology> .'],
    ['json-ld', 'application/ld+json', '{"@context":{"code":"urn:code"},"code":"example"}'],
  ]) {
    data = new Blob([content], { type })
    const blob = await api.export(7, { format, revision: 3 }, signal)
    assert.equal(blob, data)
    assert.equal(blob.type, type)
    assert.equal(await blob.text(), content)
    assert.deepEqual(calls.shift(), [
      '/ontologies/7/export',
      { params: { format, revision: 3 }, responseType: 'blob', signal },
    ])
  }
})

test('ontology export rejects JSON error envelopes in successful and failed Blob responses', async (t) => {
  const detail = {
    code: 'KG.RESOURCE_NOT_FOUND',
    message: '',
    params: { reason: 'revision_not_found' },
    data: null,
  }
  const data = new Blob([JSON.stringify(detail)], { type: 'application/json;charset=utf-8' })
  let rejected = false
  const api = await loadApi(t, {
    get: async () => {
      if (rejected) throw { response: { data, status: 404 } }
      return { data }
    },
  })
  for (rejected of [false, true]) {
    await assert.rejects(api.export(7, { format: 'turtle', revision: 3 }), (error) => {
      assert.deepEqual(error, detail)
      return true
    })
  }
})

test('ontology export preserves original non-JSON, malformed, network and cancellation errors', async (t) => {
  const controller = new AbortController()
  controller.abort()
  let failure
  const api = await loadApi(t, {
    get: async () => {
      throw failure
    },
  })
  for (failure of [
    { response: { data: new Blob(['Bad Gateway'], { type: 'text/plain' }), status: 502 } },
    { response: { data: new Blob(['{'], { type: 'application/json' }), status: 500 } },
    { code: 'ERR_NETWORK' },
    controller.signal.reason,
  ]) {
    await assert.rejects(api.export(7, { format: 'json-ld' }, controller.signal), (error) => {
      assert.equal(error, failure)
      return true
    })
  }
})

test('ontology mutations send the captured edit revision without changing legacy calls or canvas writes', async (t) => {
  const calls = []
  const api = await loadApi(
    t,
    Object.fromEntries(
      ['put', 'post', 'delete'].map((method) => [
        method,
        async (...args) => {
          calls.push([method, ...args])
          return { data: {} }
        },
      ]),
    ),
  )
  const payload = { label_i18n: { 'en-US': 'Example' }, if_match: 3 }
  await api.update(7, payload, 0)
  await api.addRef(7, 11, 2, 1)
  await api.removeRef(7, 12, 2)
  await api.publish(7, 3)
  assert.deepEqual(calls.splice(0), [
    ['put', '/ontologies/7', { ...payload, if_edit_match: 0 }],
    ['post', '/ontologies/7/refs', { resource_id: 11, pinned_revision: 2, if_edit_match: 1 }],
    ['delete', '/ontologies/7/refs/12', { headers: { 'If-Edit-Match': 2 } }],
    ['post', '/ontologies/7/publish', undefined, { headers: { 'If-Edit-Match': 3 } }],
  ])

  await api.update(7, { ...payload, if_edit_match: 4 })
  assert.equal(calls.shift()[2].if_edit_match, 4)
  await api.addRef(7, 11)
  assert.equal(calls.shift()[2].if_edit_match, undefined)
  await api.removeRef(7, 12)
  assert.equal(calls.shift()[2].headers['If-Edit-Match'], undefined)
  await api.publish(7)
  assert.equal(calls.shift()[3].headers['If-Edit-Match'], undefined)

  const positions = { 11: { x: 20, y: 30 } }
  await api.saveCanvas(7, positions)
  assert.deepEqual(calls.shift(), ['put', '/ontologies/7/canvas', { positions }])
})
