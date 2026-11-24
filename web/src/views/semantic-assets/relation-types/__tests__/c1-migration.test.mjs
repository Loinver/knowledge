import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from './c1-view-harness.mjs'

const relation = (id) => ({
  id,
  name: `Relation${id}`,
  iri: `https://example.org/Relation${id}`,
  namespace_id: 1,
  label_i18n: { 'zh-CN': `关系${id}` },
  status: 'DRAFT',
  current_revision: 0,
  edit_revision: 3,
  domain_spec: { type_id: 1, cardinality: { min: 0, max: -1 } },
  range_spec: { type_id: 2, cardinality: { min: 0, max: -1 } },
  enable_attributes: false,
  owl: { functional: false, inverse_functional: false, symmetric: false, transitive: false },
})
const mountList = (api = {}) =>
  mount(
    'views/semantic-assets/relation-types/RelationTypesPage.vue',
    {
      '@/api/relations': {
        relationsApi: { list: async () => [], get: async (id) => relation(id), ...api },
      },
      '@/api/entity-types': { entityTypesApi: { list: async () => [] } },
      '@/api/namespaces': { namespacesApi: { list: async () => [] } },
    },
    'openCreate,handleCreate,createFormRef,showCreate,creating,createError,formData,page,pageSize,searchQuery,statusFilter,search,resetFilters,changePageSize,filtered,columns,createRules,editRules',
  )

test('both relation forms recreate paired rules when either endpoint bound changes', async (t) => {
  const ctx = await mountList()
  t.after(ctx.stop)
  for (const side of ['domainCardinality', 'rangeCardinality']) {
    for (const correcting of ['min', 'max']) {
      ctx.vm.formData[side] = { min: 3, max: 2 }
      const before = [ctx.vm.createRules, ctx.vm.editRules]
      for (const rules of before)
        for (const bound of ['min', 'max'])
          assert.equal(rules[`${side}.${bound}`].validator(), false)
      ctx.vm.formData[side][correcting] = correcting === 'min' ? 1 : 4
      await settle()
      const after = [ctx.vm.createRules, ctx.vm.editRules]
      for (let index = 0; index < after.length; index++) {
        assert.notEqual(after[index], before[index])
        for (const bound of ['min', 'max'])
          assert.equal(after[index][`${side}.${bound}`].validator(), true)
      }
    }
  }
})

test('relation create locks before validation and preserves both cardinalities and false flags', async (t) => {
  const validation = deferred()
  const writes = []
  const ctx = await mountList({ create: async (payload) => writes.push(payload) })
  t.after(ctx.stop)
  ctx.vm.openCreate()
  Object.assign(ctx.vm.formData, {
    name: 'WorksIn',
    namespace_id: 1,
    labelZh: '任职',
    domainType: 1,
    rangeType: 2,
    domainCardinality: { min: 0, max: 2 },
    rangeCardinality: { min: 1, max: -1 },
  })
  ctx.vm.createFormRef = { validate: () => validation.promise, restoreValidation() {} }
  const saving = ctx.vm.handleCreate()
  await ctx.vm.handleCreate()
  ctx.vm.formData.domainCardinality.max = 99
  validation.resolve()
  await saving
  assert.equal(writes.length, 1)
  assert.deepEqual(writes[0].domain_spec, { type_id: 1, cardinality: { min: 0, max: 2 } })
  assert.deepEqual(writes[0].range_spec, { type_id: 2, cardinality: { min: 1, max: -1 } })
  assert.equal(writes[0].enable_attributes, false)
  assert.equal(writes[0].owl.functional, false)
  assert.deepEqual(writes[0].label_i18n, { 'zh-CN': '任职' })
  assert.equal(ctx.vm.creating, false)
})

test('relation validation cannot submit after closing and reopening the create session', async (t) => {
  const validation = deferred()
  const writes = []
  const ctx = await mountList({ create: async (payload) => writes.push(payload) })
  t.after(ctx.stop)
  ctx.vm.openCreate()
  ctx.vm.createFormRef = { validate: () => validation.promise, restoreValidation() {} }
  const saving = ctx.vm.handleCreate()
  ctx.vm.showCreate = false
  ctx.vm.openCreate()
  ctx.vm.formData.labelZh = '下一会话'
  validation.resolve()
  await saving
  assert.deepEqual(writes, [])
  assert.equal(ctx.vm.showCreate, true)
  assert.equal(ctx.vm.formData.labelZh, '下一会话')
})

test('invalid bounds in either relation endpoint prevent a create request and retain the draft', async (t) => {
  const writes = []
  const ctx = await mountList({ create: async (payload) => writes.push(payload) })
  t.after(ctx.stop)
  ctx.vm.openCreate()
  ctx.vm.formData.labelZh = '保留输入'
  for (const side of ['domainCardinality', 'rangeCardinality']) {
    for (const invalid of [
      { min: -1, max: 2 },
      { min: 2, max: 1 },
      { min: 0.5, max: -1 },
      { min: 0, max: -2 },
    ]) {
      ctx.vm.formData[side] = invalid
      await ctx.vm.handleCreate()
      assert.equal(ctx.vm.showCreate, true)
      assert.equal(ctx.vm.formData.labelZh, '保留输入')
      assert.equal(
        ctx.vm.createError,
        'Cardinality must use integers: minimum >= 0, maximum = -1 or maximum >= minimum',
      )
      assert.equal(ctx.vm.creating, false)
      ctx.vm.formData[side] = { min: 0, max: -1 }
    }
  }
  assert.deepEqual(writes, [])
})

test('old relation create success and error cannot finish a new pending create', async (t) => {
  for (const fail of [false, true]) {
    const first = deferred()
    const second = deferred()
    let requests = 0
    const ctx = await mountList({
      create: () => (++requests === 1 ? first.promise : second.promise),
    })
    t.after(ctx.stop)
    ctx.vm.openCreate()
    const old = ctx.vm.handleCreate()
    await settle()
    ctx.vm.showCreate = false
    ctx.vm.openCreate()
    ctx.vm.formData.labelZh = '当前输入'
    const current = ctx.vm.handleCreate()
    await settle()
    if (fail) first.reject({ code: 'KG.REVISION_CONFLICT' })
    else first.resolve({})
    await old
    assert.equal(ctx.vm.showCreate, true)
    assert.equal(ctx.vm.formData.labelZh, '当前输入')
    assert.equal(ctx.vm.creating, true)
    assert.equal(ctx.vm.createError, '')
    second.reject({ code: 'KG.INVALID_NAME', params: { name: 'Example' } })
    await current
    assert.equal(ctx.vm.formData.labelZh, '当前输入')
    assert.equal(ctx.vm.creating, false)
    assert.equal(ctx.vm.createError, 'Invalid machine name: Example')
  }
})

test('relation search, reset and page size always return to page one without deduplicating relations', async (t) => {
  const queries = []
  const ctx = await mountList({
    list: async (params) => {
      queries.push(params?.q)
      return [relation(1), relation(2)]
    },
  })
  t.after(ctx.stop)
  ctx.vm.page = 4
  ctx.vm.searchQuery = 'Works'
  ctx.vm.search()
  await settle()
  assert.equal(ctx.vm.page, 1)
  assert.equal(queries.at(-1), 'Works')
  assert.deepEqual(
    ctx.vm.filtered.map((row) => row.id),
    [1, 2],
  )
  ctx.vm.page = 4
  ctx.vm.changePageSize(50)
  assert.equal(ctx.vm.page, 1)
  assert.equal(ctx.vm.pageSize, 50)
  ctx.vm.statusFilter = 'PUBLISHED'
  ctx.vm.page = 4
  ctx.vm.resetFilters()
  await settle()
  assert.equal(ctx.vm.page, 1)
  assert.equal(ctx.vm.statusFilter, '')
  assert.equal(queries.at(-1), '')
  assert.equal(ctx.vm.columns.find((column) => column.key === 'actions').fixed, 'right')
  assert.equal(
    ctx.vm.columns.find((column) => column.key === 'iri').render(relation(1)).props.title,
    relation(1).iri,
  )
})

test('relation detail publication finishes loading after refresh and an obsolete revision cannot unlock a newer write', async (t) => {
  const old = deferred()
  const current = deferred()
  const calls = []
  const ctx = await mount(
    'views/semantic-assets/relation-types/RelationTypeDetailPage.vue',
    {
      '@/api/entity-types': { entityTypesApi: { list: async () => [] } },
      '@/api/relations': {
        relationsApi: {
          get: async (id) => ({ ...relation(id), status: id === 1 ? 'PUBLISHED' : 'DRAFT' }),
          usages: async () => ({}),
          unpublish: (id) => {
            calls.push(['revision', id])
            return old.promise
          },
          publish: (id) => {
            calls.push(['publish', id])
            return current.promise
          },
        },
      },
    },
    'startRevision,handlePublish,busy,error,notice',
    '/entities/1',
  )
  t.after(ctx.stop)
  const revising = ctx.vm.startRevision()
  await settle()
  await ctx.router.push('/entities/2')
  await settle()
  const publishing = ctx.vm.handlePublish()
  await settle()
  old.reject({ code: 'KG.REVISION_CONFLICT' })
  await revising
  assert.equal(ctx.vm.busy, true)
  assert.equal(ctx.vm.error, '')
  current.resolve({ revision: 1, checksum: 'example' })
  await publishing
  assert.equal(ctx.vm.busy, false)
  assert.ok(ctx.vm.notice)
  assert.deepEqual(calls, [
    ['revision', 1],
    ['publish', 2],
  ])
})
