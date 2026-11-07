import assert from 'node:assert/strict'
import { test } from 'node:test'

import { compile } from '../../views/__tests__/view-harness.mjs'

for (const [file, name, path] of [
  ['entity-types', 'entityTypesApi', '/entity-types'],
  ['relations', 'relationsApi', '/relations'],
  ['domains', 'domainsApi', '/domains'],
  ['ontology', 'ontologyApi', '/ontologies'],
  ['datasources', 'datasourcesApi', '/datasources'],
  ['mappings', 'mappingsApi', '/mappings'],
]) {
  test(`${name} includes tail records and does not present a failed tail as complete`, async (t) => {
    const calls = []
    const rows = Array.from({ length: 401 }, (_, id) => ({ id }))
    let fail = false
    const controller = new AbortController()
    const result = await compile(`api/${file}.ts`, {
      '@/api/client': {
        http: {
          get: async (url, options) => {
            assert.equal(url, path)
            assert.equal(options.signal, controller.signal)
            calls.push(options.params.page)
            if (fail && options.params.page === 2) throw new Error('tail failed')
            const start = (options.params.page - 1) * options.params.page_size
            return { data: rows.slice(start, start + options.params.page_size) }
          },
        },
      },
    })
    t.after(result.cleanup)
    const api = result.mod[name]
    const load = () =>
      name === 'graphApi'
        ? api.revisions(controller.signal)
        : name === 'mappingsApi'
          ? api.list(controller.signal)
          : api.list({}, controller.signal)
    assert.deepEqual(await load(), rows)
    assert.deepEqual(calls, [1, 2, 3])
    fail = true
    await assert.rejects(load(), /tail failed/)
    controller.abort()
    await assert.rejects(load(), { name: 'AbortError' })
  })
}
