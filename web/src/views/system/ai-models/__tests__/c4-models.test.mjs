import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, settle } from '../../../../testing/view-harness.mjs'
import { mountC4 } from '../../../account/__tests__/c4-render-harness.mjs'

const entry = 'views/system/ai-models/AiModelsPage.vue'
const expose =
  'form,openCreate,openEdit,submit,showEditor,busy,saving,editorError,enabledSelection,enabledFilter,page,query,search,doSearch,resetSearch,editing,auth'
const api = (overrides = {}) => ({
  page: async () => ({ items: [], total: 0 }),
  defaults: async () => [],
  ...overrides,
})
const valid = {
  name: ' Example ',
  baseUrl: 'https://example.org/v1',
  model: 'example',
  modelVersion: '1',
  timeoutSeconds: 30,
  apiKey: '',
  enabled: false,
}

test('UI select strings retain false, true and null in remote API queries; reset reads once', async (t) => {
  const queries = []
  const view = await mountC4(
    t,
    entry,
    api({
      page: async (query) => {
        queries.push(query)
        return { items: [], total: 0 }
      },
    }),
    expose,
  )
  view.vm.enabledSelection = 'false'
  await settle()
  assert.equal(queries.at(-1).enabled, false)
  assert.equal(view.vm.enabledFilter, false)
  view.vm.enabledSelection = 'true'
  await settle()
  assert.equal(queries.at(-1).enabled, true)
  const before = queries.length
  view.vm.resetSearch()
  await settle()
  assert.equal(queries.length, before + 1)
  assert.equal(queries.at(-1).enabled, undefined)
  assert.equal(view.vm.enabledSelection, null)
})

test('model real form rejects invalid URL and timeout, then preserves failed draft and boolean payload', async (t) => {
  const writes = []
  let fail = true
  const view = await mountC4(
    t,
    entry,
    api({
      add: async (payload) => {
        writes.push(payload)
        if (fail) throw { code: 'KG.INTERNAL_ERROR' }
        return { id: 1, ...payload }
      },
    }),
    expose,
  )
  view.vm.openCreate()
  await settle()
  await view.vm.submit()
  assert.equal(writes.length, 0)
  assert.ok(view.invalid().length >= 3)
  Object.assign(view.vm.form, valid, {
    baseUrl: 'https://user:password@example.org',
    timeoutSeconds: null,
  })
  await settle()
  await view.vm.submit()
  assert.equal(writes.length, 0)
  Object.assign(view.vm.form, valid)
  await settle()
  await view.vm.submit()
  assert.ok(view.vm.editorError)
  assert.equal(view.vm.form.name, ' Example ')
  assert.equal(view.vm.showEditor, true)
  assert.equal(writes[0].enabled, false)
  assert.equal('api_key' in writes[0], false)
  fail = false
  await view.vm.submit()
  assert.equal(view.vm.showEditor, false)
  assert.equal(writes.length, 2)
})

test('late model save cannot close a new editor or clear its busy state', async (t) => {
  const pending = [deferred(), deferred()]
  let calls = 0
  const view = await mountC4(t, entry, api({ add: () => pending[calls++].promise }), expose)
  view.vm.openCreate()
  Object.assign(view.vm.form, valid)
  await settle()
  const first = view.vm.submit()
  await settle()
  await view.vm.submit()
  assert.equal(calls, 1)
  view.vm.auth.user = { id: 'second-actor', role: 'ADMIN' }
  await settle()
  view.vm.openCreate()
  Object.assign(view.vm.form, valid, { name: 'Second' })
  await settle()
  const second = view.vm.submit()
  await settle()
  assert.equal(calls, 2)
  pending[0].resolve({ id: 1 })
  await first
  assert.equal(view.vm.showEditor, true)
  assert.equal(view.vm.form.name, 'Second')
  assert.equal(view.vm.busy, true)
  pending[1].resolve({ id: 2 })
  await second
  assert.equal(view.vm.showEditor, false)
})

test('model edits keep revision identity and omit unchanged key; explicit clear sends null and false', async (t) => {
  const original = {
    id: 7,
    revision: 12,
    name: 'Example',
    capability: 'CHAT',
    base_url: 'https://example.org/v1',
    model: 'example',
    model_version: '1',
    timeout_seconds: 30,
    enabled: true,
    has_key: true,
  }
  const writes = []
  const view = await mountC4(
    t,
    entry,
    api({
      getDetailById: async () => original,
      edit: async (config, payload) => {
        writes.push([config, payload])
        return { ...config, ...payload }
      },
    }),
    expose,
  )
  await view.vm.openEdit(original)
  await settle()
  await view.vm.submit()
  assert.equal(writes[0][0].revision, 12)
  assert.equal('api_key' in writes[0][1], false)
  await view.vm.openEdit(original)
  view.vm.form.clearKey = true
  await settle()
  await view.vm.submit()
  assert.equal(writes[1][1].api_key, null)
  assert.equal(writes[1][1].enabled, false)
})
