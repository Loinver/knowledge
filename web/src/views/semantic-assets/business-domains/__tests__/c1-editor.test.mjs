import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from '../../relation-types/__tests__/c1-view-harness.mjs'

const domain = (id, editRevision = 3) => ({
  id,
  name: `Domain${id}`,
  iri: `https://example.org/Domain${id}`,
  label_i18n: { 'zh-CN': `域${id}`, 'en-US': `Domain ${id}` },
  definition_i18n: {},
  status: 'DRAFT',
  current_revision: 2,
  edit_revision: editRevision,
})
const mountDomains = (api = {}) =>
  mount(
    'views/semantic-assets/business-domains/BusinessDomainsPage.vue',
    {
      '@/api/domains': {
        domainsApi: {
          list: async () => [domain(1), domain(2)],
          get: async (id) => domain(id),
          members: async () => [],
          ...api,
        },
      },
      '@/api/entity-types': { entityTypesApi: { list: async () => [] } },
      '@/api/relations': { relationsApi: { list: async () => [] } },
    },
    'items,select,selected,openBasicEditor,saveBasic,basicForm,basicFormRef,basicError,showBasicEditor,basicSaving,working,showCreate,handleCreate,formData,createFormRef,creating,createError,members,memberColumns',
  )

test('domain create takes one snapshot before validation and locks duplicate submissions', async (t) => {
  const validation = deferred()
  const writes = []
  const ctx = await mountDomains({ create: async (payload) => writes.push(payload) })
  t.after(ctx.stop)
  ctx.vm.showCreate = true
  Object.assign(ctx.vm.formData, {
    name: 'Example',
    iri: 'urn:example:domain',
    labelZh: '示例',
    parentId: 2,
  })
  ctx.vm.createFormRef = { validate: () => validation.promise, restoreValidation() {} }
  const saving = ctx.vm.handleCreate()
  await ctx.vm.handleCreate()
  ctx.vm.formData.parentId = null
  validation.resolve()
  await saving
  assert.equal(writes.length, 1)
  assert.equal(writes[0].parent_id, 2)
  assert.equal(writes[0].iri, 'urn:example:domain')
  assert.deepEqual(writes[0].label_i18n, { 'zh-CN': '示例' })
  assert.equal(ctx.vm.creating, false)
})

test('domain create ignores validation and write results belonging to an earlier session', async (t) => {
  for (const phase of ['validation', 'write']) {
    const pending = deferred()
    let writes = 0
    const ctx = await mountDomains({
      create: () => {
        writes++
        return pending.promise
      },
    })
    t.after(ctx.stop)
    ctx.vm.showCreate = true
    if (phase === 'validation')
      ctx.vm.createFormRef = { validate: () => pending.promise, restoreValidation() {} }
    const saving = ctx.vm.handleCreate()
    await settle()
    ctx.vm.showCreate = false
    ctx.vm.showCreate = true
    ctx.vm.formData.labelZh = '新草稿'
    pending.resolve({})
    await saving
    assert.equal(writes, phase === 'validation' ? 0 : 1)
    assert.equal(ctx.vm.showCreate, true)
    assert.equal(ctx.vm.formData.labelZh, '新草稿')
    assert.equal(ctx.vm.createError, '')
  }
})

test('domain basic validation cannot write a newly selected domain', async (t) => {
  const validation = deferred()
  const writes = []
  const ctx = await mountDomains({ update: async (...args) => writes.push(args) })
  t.after(ctx.stop)
  await ctx.vm.select(domain(1))
  ctx.vm.openBasicEditor()
  ctx.vm.basicFormRef = { validate: () => validation.promise, restoreValidation() {} }
  const saving = ctx.vm.saveBasic()
  ctx.vm.showBasicEditor = false
  await ctx.vm.select(domain(2))
  ctx.vm.openBasicEditor()
  ctx.vm.basicForm.labelZh = '域2草稿'
  validation.resolve()
  await saving
  assert.deepEqual(writes, [])
  assert.equal(ctx.vm.showBasicEditor, true)
  assert.equal(ctx.vm.basicForm.labelZh, '域2草稿')
})

test('domain basic save preserves captured fields, identity and both revision tokens', async (t) => {
  const validation = deferred()
  const writes = []
  const ctx = await mountDomains({
    update: async (id, payload) => {
      writes.push([id, payload])
      return domain(id, 4)
    },
  })
  t.after(ctx.stop)
  await ctx.vm.select(domain(1))
  ctx.vm.openBasicEditor()
  Object.assign(ctx.vm.basicForm, {
    labelZh: '提交值',
    parentId: null,
    definitionEn: 'Submitted definition',
  })
  ctx.vm.basicFormRef = { validate: () => validation.promise, restoreValidation() {} }
  const saving = ctx.vm.saveBasic()
  await ctx.vm.saveBasic()
  ctx.vm.basicForm.parentId = 2
  ctx.vm.basicForm.definitionEn = 'Later value'
  validation.resolve()
  await saving
  assert.equal(writes.length, 1)
  assert.equal(writes[0][0], 1)
  assert.equal(writes[0][1].parent_id, null)
  assert.equal(writes[0][1].definition_i18n['en-US'], 'Submitted definition')
  assert.equal(writes[0][1].if_match, 2)
  assert.equal(writes[0][1].if_edit_match, 3)
  assert.equal(ctx.vm.working, false)
  assert.equal(ctx.vm.basicSaving, false)
  assert.equal(ctx.vm.showBasicEditor, false)
})

test('domain members preserve two independent memberships of the same resource', async (t) => {
  const members = [
    { id: 11, resource_id: 1, as_ref: false },
    { id: 12, resource_id: 1, as_ref: true },
  ]
  const ctx = await mountDomains({ members: async () => members })
  t.after(ctx.stop)
  await ctx.vm.select(domain(1))
  assert.deepEqual(ctx.vm.members, members)
  assert.equal(ctx.vm.memberColumns.find((column) => column.key === 'actions').fixed, 'right')
})

test('old domain basic write cannot close or contaminate a newly opened editor', async (t) => {
  for (const fail of [false, true]) {
    const pending = deferred()
    const ctx = await mountDomains({ update: () => pending.promise })
    t.after(ctx.stop)
    await ctx.vm.select(domain(1))
    ctx.vm.openBasicEditor()
    const saving = ctx.vm.saveBasic()
    await settle()
    ctx.vm.showBasicEditor = false
    await ctx.vm.select(domain(2))
    ctx.vm.openBasicEditor()
    ctx.vm.basicForm.labelZh = '新编辑会话'
    if (fail) pending.reject({ code: 'KG.REVISION_CONFLICT' })
    else pending.resolve(domain(1, 4))
    await saving
    assert.equal(ctx.vm.selected.id, 2)
    assert.equal(ctx.vm.showBasicEditor, true)
    assert.equal(ctx.vm.basicForm.labelZh, '新编辑会话')
    assert.equal(ctx.vm.working, false)
    assert.equal(ctx.vm.basicSaving, false)
  }
})

test('current domain basic failure stays visible in the drawer and retains fields for retry', async (t) => {
  const ctx = await mountDomains({
    update: async () => {
      throw { code: 'KG.INVALID_NAME', params: { name: 'Example' } }
    },
  })
  t.after(ctx.stop)
  await ctx.vm.select(domain(1))
  ctx.vm.openBasicEditor()
  ctx.vm.basicForm.labelZh = '保留草稿'
  await ctx.vm.saveBasic()
  assert.equal(ctx.vm.showBasicEditor, true)
  assert.equal(ctx.vm.basicForm.labelZh, '保留草稿')
  assert.equal(ctx.vm.basicError, 'Invalid machine name: Example')
  assert.equal(ctx.vm.basicSaving, false)
  assert.equal(ctx.vm.working, false)
})

test('domain basic save preserves optional English absence and only stores an actual English label', async (t) => {
  for (const english of ['', '   ', '  Domain one  ']) {
    const writes = []
    const ctx = await mountDomains({
      get: async (id) => ({ ...domain(id), label_i18n: { 'zh-CN': '域一' } }),
      update: async (id, payload) => {
        writes.push({ id, payload })
        return domain(id, 4)
      },
    })
    t.after(ctx.stop)
    await ctx.vm.select(domain(1))
    ctx.vm.openBasicEditor()
    ctx.vm.basicForm.labelEn = english
    ctx.vm.basicFormRef = { validate: async () => {}, restoreValidation() {} }
    await ctx.vm.saveBasic()
    assert.equal(writes.length, 1)
    assert.equal(writes[0].id, 1)
    assert.deepEqual(writes[0].payload.label_i18n, {
      'zh-CN': '域一',
      ...(english.trim() ? { 'en-US': 'Domain one' } : {}),
    })
    assert.equal(writes[0].payload.if_match, 2)
    assert.equal(writes[0].payload.if_edit_match, 3)
  }
})
