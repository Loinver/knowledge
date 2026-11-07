import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from '../../__tests__/view-harness.mjs'

const field = {
  iri: 'https://example.org/eventTime',
  name: 'moment',
  kind: 'PROPERTY',
  type_iri: 'Event',
  datatype: 'date',
}
const graph = (id) => ({
  graph_revision_id: id,
  ontology_id: id,
  ontology_revision: 1,
  type_counts: [],
  nodes: [{ iri: 'event', type_iri: 'Event', attrs: { moment: '2024-01-01T01:00:00Z' } }],
  edges: [],
})
const catalog = (id) => ({ ontology_id: id, ontology_revision: 1, stale: false, fields: [field] })
const template = (id, config = {}) => ({
  id,
  ontology_id: id,
  ontology_revision: 1,
  layout_id: 'timeline',
  config,
  name_i18n: { 'zh-CN': '模板', 'en-US': 'Template' },
  stale: false,
})
async function setup(api = {}, start = '/?graph=1') {
  const viewTemplateApi = {
    list: async (id) => ({ items: [template(id)], total: 1 }),
    fields: async (id) => catalog(id),
    applicable: async (id) => template(id),
    ...api,
  }
  return mount(
    'views/graph/GraphBrowse.vue',
    {
      '@/api/graph': {
        graphApi: {
          view: async (params) => graph(params.graph_revision_id ?? 1),
          entities: async () => ({ items: [] }),
          recommendations: async () => ({ recommendations: [] }),
        },
        viewTemplateApi,
      },
    },
    'templates,semanticFields,semanticConfig,semanticContext,configureSemantics,applyTemplate,saveTemplate,templateName,selectedTemplateId,legacyTemplate,templateError,savingTemplate,applyingTemplate,replayBounds,selectLayout',
    start,
  )
}

test('late catalog/list responses cannot replace the active graph and abort on unmount', async () => {
  const oldFields = deferred(),
    oldList = deferred(),
    lastFields = deferred()
  const signals = []
  const ctx = await setup({
    fields: (id, _revision, signal) => {
      signals.push(signal)
      return id === 1
        ? oldFields.promise
        : id === 3
          ? lastFields.promise
          : Promise.resolve(catalog(id))
    },
    list: (id) => (id === 1 ? oldList.promise : Promise.resolve({ items: [template(id)] })),
  })
  await ctx.router.push('/?graph=2')
  await settle()
  oldFields.resolve(catalog(1))
  oldList.resolve({ items: [template(1)] })
  await settle()
  assert.equal(ctx.vm.semanticFields.data.value.ontology_id, 2)
  assert.equal(ctx.vm.templates[0].id, 2)
  assert.equal(signals[0].aborted, true)
  await ctx.router.push('/?graph=3')
  await settle()
  ctx.stop()
  assert.equal(signals.at(-1).aborted, true)
  lastFields.resolve(catalog(3))
  await settle()
})

test('stale templates cannot apply, and applying rereads eligibility from the server', async () => {
  let calls = 0
  const ctx = await setup({
    applicable: async () => {
      calls++
      throw { code: 'KG.REVISION_CONFLICT' }
    },
  })
  try {
    await ctx.vm.applyTemplate(1)
    assert.equal(calls, 1)
    assert.equal(ctx.vm.selectedTemplateId, null)
    assert.notEqual(ctx.vm.templateError, '')
    ctx.vm.templates[0].stale = true
    await ctx.vm.applyTemplate(1)
    assert.equal(calls, 1)
    assert.equal(ctx.vm.selectedTemplateId, null)
  } finally {
    ctx.stop()
  }
})

test('obsolete apply response cannot change a new graph or a newer explicit selection', async () => {
  const response = deferred()
  let signal
  const ctx = await setup({
    applicable: (_id, _onto, _revision, currentSignal) => {
      signal = currentSignal
      return response.promise
    },
  })
  try {
    const applying = ctx.vm.applyTemplate(1)
    await ctx.router.push('/?graph=2')
    await settle()
    response.resolve(template(1, { time_property_iri: field.iri }))
    await applying
    assert.equal(signal.aborted, true)
    assert.equal(ctx.vm.selectedTemplateId, null)
    assert.deepEqual(ctx.vm.semanticConfig, {})
    assert.equal(ctx.vm.applyingTemplate, false)
  } finally {
    ctx.stop()
  }

  const late = deferred()
  const second = await setup({ applicable: () => late.promise })
  try {
    const applying = second.vm.applyTemplate(1)
    second.vm.configureSemantics({ time_property_iri: field.iri })
    late.resolve(template(1))
    await applying
    assert.equal(second.vm.legacyTemplate, false)
    assert.equal(second.vm.semanticConfig.time_property_iri, field.iri)
  } finally {
    second.stop()
  }
})

test('save/apply preserves explicit configuration; replay uses only the configured UTC field', async () => {
  let saved
  const ctx = await setup({
    create: async (payload) => {
      saved = template(1, payload.config)
      return saved
    },
    applicable: async () => saved,
  })
  try {
    ctx.vm.configureSemantics({ time_property_iri: field.iri })
    assert.deepEqual(ctx.vm.replayBounds, [1704070800000, 1704070800000])
    ctx.vm.templateName = 'Saved view'
    await ctx.vm.saveTemplate()
    await settle()
    assert.equal(saved.config.time_property_iri, field.iri)
    assert.equal(saved.config.semantic_version, 1)
    ctx.vm.configureSemantics({})
    assert.equal(ctx.vm.replayBounds, null)
    await ctx.vm.applyTemplate(1)
    assert.equal(ctx.vm.semanticConfig.time_property_iri, field.iri)
    assert.equal(ctx.vm.legacyTemplate, false)
  } finally {
    ctx.stop()
  }
})

test('legacy templates retain display only until the user explicitly selects a new layout', async () => {
  const ctx = await setup()
  try {
    await ctx.vm.applyTemplate(1)
    assert.equal(ctx.vm.legacyTemplate, true)
    ctx.vm.selectLayout('geo')
    assert.equal(ctx.vm.legacyTemplate, false)
  } finally {
    ctx.stop()
  }
})

test('page reload restores the explicit pinned template from its query parameter', async () => {
  const config = { semantic_version: 1, time_property_iri: field.iri }
  const ctx = await setup({ applicable: async () => template(1, config) }, '/?graph=1&template=1')
  try {
    await settle()
    assert.equal(ctx.vm.selectedTemplateId, 1)
    assert.equal(ctx.vm.semanticConfig.time_property_iri, field.iri)
    assert.equal(ctx.vm.legacyTemplate, false)
    assert.deepEqual(ctx.vm.replayBounds, [1704070800000, 1704070800000])
  } finally {
    ctx.stop()
  }
})

test('unmount aborts a pending save and its late response cannot alter page state', async () => {
  const result = deferred()
  let signal
  const ctx = await setup({
    create: (_payload, currentSignal) => {
      signal = currentSignal
      return result.promise
    },
  })
  ctx.vm.templateName = 'Still saving'
  const saving = ctx.vm.saveTemplate()
  ctx.stop()
  assert.equal(signal.aborted, true)
  result.resolve(template(1))
  await saving
  assert.equal(ctx.vm.templateName, 'Still saving')
})
