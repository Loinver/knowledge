import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, settle } from './c1-view-harness.mjs'

const relation = (id) => ({
  id,
  name: `Relation${id}`,
  namespace_id: 1,
  label_i18n: { 'zh-CN': `关系${id}`, 'en-US': `Relation ${id}` },
  status: 'DRAFT',
  current_revision: 0,
  edit_revision: 1,
  domain_spec: { type_id: 1, cardinality: { min: 0, max: -1 } },
  range_spec: { type_id: 2, cardinality: { min: 0, max: -1 } },
  enable_attributes: false,
  owl: {},
})

const mountEditor = (api) =>
  mount(
    'views/semantic-assets/relation-types/RelationTypesPage.vue',
    {
      '@/api/relations': { relationsApi: { list: async () => [], ...api } },
      '@/api/entity-types': { entityTypesApi: { list: async () => [] } },
      '@/api/namespaces': { namespacesApi: { list: async () => [] } },
    },
    'openEdit,openCreate,handleEdit,showEdit,showCreate,formData,editingDetail,editError,editing,editVisible,editFormRef',
  )

test('late detail response cannot replace the active relation draft', async (t) => {
  const first = deferred()
  const second = deferred()
  const writes = []
  const ctx = await mountEditor({
    get: (id) => (id === 1 ? first.promise : second.promise),
    update: async (id, payload) => {
      writes.push({ id, payload })
      return { ...relation(id), ...payload }
    },
  })
  t.after(ctx.stop)

  const openingFirst = ctx.vm.openEdit(1)
  const openingSecond = ctx.vm.openEdit(2)
  second.resolve(relation(2))
  await openingSecond
  ctx.vm.formData.labelZh = '关系2用户草稿'
  first.resolve(relation(1))
  await openingFirst

  assert.equal(ctx.vm.editingDetail.id, 2)
  assert.equal(ctx.vm.formData.labelZh, '关系2用户草稿')
  await ctx.vm.handleEdit()
  assert.equal(writes[0].id, 2)
  assert.equal(writes[0].payload.label_i18n['zh-CN'], '关系2用户草稿')
})

test('current detail read failure remains visible after the synchronous open watcher', async (t) => {
  const ctx = await mountEditor({
    get: async () => Promise.reject({ code: 'KG.RESOURCE_NOT_FOUND' }),
  })
  t.after(ctx.stop)

  await ctx.vm.openEdit(1)
  assert.equal(ctx.vm.showEdit, true)
  assert.equal(ctx.vm.editingDetail, null)
  assert.equal(ctx.vm.editError, 'KG.RESOURCE_NOT_FOUND')
})

test('closing or opening create invalidates a pending relation detail read', async (t) => {
  const first = deferred()
  const pending = deferred()
  const pendingCreate = deferred()
  const ctx = await mountEditor({
    get: (id) => (id === 1 ? first.promise : id === 2 ? pending.promise : pendingCreate.promise),
  })
  t.after(ctx.stop)

  const openingFirst = ctx.vm.openEdit(1)
  first.resolve(relation(1))
  await openingFirst
  const openingSecond = ctx.vm.openEdit(2)
  ctx.vm.editVisible = false
  pending.resolve(relation(2))
  await openingSecond
  assert.equal(ctx.vm.showEdit, false)
  assert.equal(ctx.vm.editingDetail, null)

  ctx.vm.showCreate = false
  const openingForCreate = ctx.vm.openEdit(3)
  await settle()
  ctx.vm.openCreate()
  pendingCreate.resolve(relation(3))
  await openingForCreate
  assert.equal(ctx.vm.showCreate, true)
  assert.equal(ctx.vm.showEdit, false)
  assert.equal(ctx.vm.editingDetail, null)
})

test('validation completion is bound to the editor session and request payload is snapshotted', async (t) => {
  const validation = deferred()
  const writes = []
  const ctx = await mountEditor({
    get: async (id) => relation(id),
    update: async (id, payload) => {
      writes.push({ id, payload })
      return { ...relation(id), ...payload }
    },
  })
  t.after(ctx.stop)
  await ctx.vm.openEdit(1)
  ctx.vm.editFormRef = { validate: () => validation.promise, restoreValidation() {} }
  const savingOld = ctx.vm.handleEdit()
  await settle()
  await ctx.vm.openEdit(2)
  ctx.vm.formData.labelZh = '关系2草稿'
  validation.resolve()
  await savingOld
  assert.equal(writes.length, 0)

  ctx.vm.editFormRef = { validate: async () => undefined, restoreValidation() {} }
  const savingCurrent = ctx.vm.handleEdit()
  ctx.vm.formData.labelZh = '校验后改动'
  await savingCurrent
  assert.equal(writes[0].id, 2)
  assert.equal(writes[0].payload.label_i18n['zh-CN'], '关系2草稿')
})

test('old write success or failure cannot close or contaminate a newer editor', async (t) => {
  for (const fail of [false, true]) {
    const oldWrite = deferred()
    const ctx = await mountEditor({
      get: async (id) => relation(id),
      update: (id) => (id === 1 ? oldWrite.promise : Promise.resolve(relation(id))),
    })
    t.after(ctx.stop)
    await ctx.vm.openEdit(1)
    ctx.vm.editFormRef = { validate: async () => undefined, restoreValidation() {} }
    const savingOld = ctx.vm.handleEdit()
    await settle()
    await ctx.vm.openEdit(2)
    ctx.vm.formData.labelZh = '关系2草稿'
    if (fail) oldWrite.reject({ code: 'KG.REVISION_CONFLICT' })
    else oldWrite.resolve(relation(1))
    await savingOld

    assert.equal(ctx.vm.showEdit, true)
    assert.equal(ctx.vm.editingDetail.id, 2)
    assert.equal(ctx.vm.formData.labelZh, '关系2草稿')
    assert.equal(ctx.vm.editError, '')
    assert.equal(ctx.vm.editing, false)
  }
})

test('returning to the same relation rejects old detail success and failure', async (t) => {
  for (const fail of [false, true]) {
    const requests = []
    const ctx = await mountEditor({
      get: (id, signal) => {
        const request = { id, signal, ...deferred() }
        requests.push(request)
        return request.promise
      },
    })
    t.after(ctx.stop)
    const first = ctx.vm.openEdit(1)
    const second = ctx.vm.openEdit(2)
    const third = ctx.vm.openEdit(1)
    assert.equal(requests[0].signal.aborted, true)
    assert.equal(requests[1].signal.aborted, true)
    requests[2].resolve(relation(1))
    await third
    ctx.vm.formData.labelZh = '当前会话草稿'
    if (fail) requests[0].reject({ code: 'KG.RESOURCE_NOT_FOUND' })
    else requests[0].resolve(relation(1))
    requests[1].reject({ code: 'ERR_CANCELED' })
    await Promise.all([first, second])
    assert.equal(ctx.vm.editingDetail.id, 1)
    assert.equal(ctx.vm.formData.labelZh, '当前会话草稿')
    assert.equal(ctx.vm.editError, '')
  }
})

test('draft guard retains declined changes and allows confirmed switching to create', async (t) => {
  const ctx = await mountEditor({ get: async (id) => relation(id) })
  t.after(ctx.stop)
  const originalWindow = globalThis.window
  let discard = false
  const confirmations = []
  globalThis.window = {
    confirm: (message) => {
      confirmations.push(message)
      return discard
    },
    addEventListener() {},
    removeEventListener() {},
  }
  t.after(() => {
    if (originalWindow === undefined) delete globalThis.window
    else globalThis.window = originalWindow
  })
  await ctx.vm.openEdit(1)
  await settle()
  ctx.vm.formData.labelZh = '保留草稿'
  ctx.vm.editVisible = false
  assert.equal(ctx.vm.showEdit, true)
  await ctx.vm.openEdit(2)
  assert.equal(ctx.vm.editingDetail.id, 1)
  assert.equal(ctx.vm.formData.labelZh, '保留草稿')
  ctx.vm.openCreate()
  assert.equal(ctx.vm.showCreate, false)
  discard = true
  ctx.vm.openCreate()
  assert.equal(ctx.vm.showCreate, true)
  assert.equal(ctx.vm.showEdit, false)
  assert.equal(confirmations.length, 4)
})

test('old completion finishes its captured rename without resetting a newer pending save', async (t) => {
  const firstWrite = deferred()
  const secondWrite = deferred()
  const renames = []
  const ctx = await mountEditor({
    get: async (id) => relation(id),
    update: (id) => (id === 1 ? firstWrite.promise : secondWrite.promise),
    rename: async (id, name) => {
      renames.push({ id, name })
      return { ...relation(id), name }
    },
  })
  t.after(ctx.stop)
  await ctx.vm.openEdit(1)
  ctx.vm.formData.name = 'Renamed1'
  const first = ctx.vm.handleEdit()
  await settle()
  // Simulate a confirmed close; draft-guard confirmation is covered separately.
  ctx.vm.showEdit = false
  await ctx.vm.openEdit(2)
  const second = ctx.vm.handleEdit()
  await settle()
  firstWrite.resolve(relation(1))
  await first
  assert.equal(ctx.vm.editing, true)
  assert.deepEqual(renames, [{ id: 1, name: 'Renamed1' }])
  assert.equal(ctx.vm.showEdit, true)
  secondWrite.resolve(relation(2))
  await second
  assert.equal(ctx.vm.editing, false)
  assert.equal(ctx.vm.showEdit, false)
})

test('closing during update still renames the captured relation without changing the next draft', async (t) => {
  const update = deferred()
  const rename = deferred()
  const calls = []
  const ctx = await mountEditor({
    get: async (id) => relation(id),
    update: (id, payload) => {
      calls.push({ operation: 'update', id, payload })
      return update.promise
    },
    rename: (id, name) => {
      calls.push({ operation: 'rename', id, name })
      return rename.promise
    },
  })
  t.after(ctx.stop)
  await ctx.vm.openEdit(1)
  ctx.vm.formData.name = 'RenamedA'
  ctx.vm.formData.labelZh = 'A label'
  const savingA = ctx.vm.handleEdit()
  await settle()

  ctx.vm.showEdit = false
  await ctx.vm.openEdit(2)
  ctx.vm.formData.labelZh = 'B unsaved draft'
  update.resolve(relation(1))
  await settle()
  assert.deepEqual(
    calls.map(({ operation, id }) => [operation, id]),
    [
      ['update', 1],
      ['rename', 1],
    ],
  )
  assert.equal(calls[1].name, 'RenamedA')
  rename.resolve({ ...relation(1), name: 'RenamedA' })
  await savingA

  assert.equal(ctx.vm.showEdit, true)
  assert.equal(ctx.vm.editingDetail.id, 2)
  assert.equal(ctx.vm.formData.labelZh, 'B unsaved draft')
  assert.equal(ctx.vm.editError, '')
})

test('unmount aborts detail reads and ignores pending validation and write completions', async () => {
  const pendingRead = deferred()
  let readSignal
  const reader = await mountEditor({
    get: (_id, signal) => {
      readSignal = signal
      return pendingRead.promise
    },
  })
  const reading = reader.vm.openEdit(1)
  reader.stop()
  assert.equal(readSignal.aborted, true)
  pendingRead.resolve(relation(1))
  await reading
  assert.equal(reader.vm.editingDetail, null)

  for (const duringValidation of [false, true]) {
    const pending = deferred()
    const writes = []
    const ctx = await mountEditor({
      get: async (id) => relation(id),
      update: (id) => {
        writes.push(id)
        return pending.promise
      },
    })
    await ctx.vm.openEdit(1)
    if (duringValidation)
      ctx.vm.editFormRef = { validate: () => pending.promise, restoreValidation() {} }
    const saving = ctx.vm.handleEdit()
    await settle()
    ctx.stop()
    pending.resolve(relation(1))
    await saving
    assert.deepEqual(writes, duringValidation ? [] : [1])
    assert.equal(ctx.vm.editingDetail, null)
    assert.equal(ctx.vm.editError, '')
  }
})

test('current save preserves conflict drafts and renames with the submitted snapshot', async (t) => {
  const update = deferred()
  const renames = []
  let fail = true
  const ctx = await mountEditor({
    get: async (id) => relation(id),
    update: async () => {
      if (fail) throw { code: 'KG.REVISION_CONFLICT' }
      return update.promise
    },
    rename: async (id, name) => {
      renames.push({ id, name })
      return { ...relation(id), name }
    },
  })
  t.after(ctx.stop)
  await ctx.vm.openEdit(1)
  ctx.vm.formData.name = 'SubmittedName'
  await ctx.vm.handleEdit()
  assert.equal(ctx.vm.showEdit, true)
  assert.equal(ctx.vm.formData.name, 'SubmittedName')
  assert.notEqual(ctx.vm.editError, '')
  assert.equal(ctx.vm.editing, false)
  fail = false
  const saving = ctx.vm.handleEdit()
  await settle()
  ctx.vm.formData.name = 'LaterName'
  update.resolve(relation(1))
  await saving
  assert.deepEqual(renames, [{ id: 1, name: 'SubmittedName' }])
  assert.equal(ctx.vm.showEdit, false)
  assert.equal(ctx.vm.editing, false)
})
