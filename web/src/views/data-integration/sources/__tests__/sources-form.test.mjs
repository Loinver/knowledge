import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, settle } from '../../../../testing/view-harness.mjs'
import {
  button,
  click,
  contents,
  find,
  input,
  mountSources,
  submit,
} from './sources-render-harness.mjs'

const source = (id) => ({ id, name: `Source ${id}`, kind: 'sqlite', status: 'DISCONNECTED' })
const forms = (view) =>
  find(view.tree, (n) => n.type === 'form' && String(n.props.class).split(' ').includes('ui-form'))

test('real create fields reject empty writes, focus name, and clear hidden network errors', async (t) => {
  const view = await mountSources(t)
  const { vm, calls } = view
  vm.openCreate()
  await settle()
  await vm.createSource()
  await settle()
  assert.equal(calls.create.length, 0)
  assert.equal(view.tree.activeElement, view.field('name'))
  assert.equal(view.field('name').props.disabled, false)
  assert.equal(view.invalid().length, 2)
  for (const field of view.invalid()) {
    const description = find(view.tree, (n) => n.props.id === field.props['aria-describedby'])[0]
    assert.ok(description && contents(description))
  }
  view.i18n.global.locale.value = 'zh-CN'
  await settle()
  assert.ok(contents(view.tree).includes(view.i18n.global.t('dataAccess.sources.validation.name')))
  await input(view.field('name'), ' Source ')
  await input(view.field('database'), ' source.sqlite ')
  vm.form.kind = 'mysql'
  await settle()
  // A kind change must not mark untouched network inputs before submission.
  assert.equal(view.invalid().length, 0)
  await vm.testConnection()
  await settle()
  assert.equal(calls.testConnection.length, 0)
  assert.deepEqual(
    new Set(view.invalid().map((n) => n.props['aria-label'])),
    new Set([
      view.i18n.global.t('dataAccess.sources.fields.host'),
      view.i18n.global.t('dataAccess.sources.fields.user'),
    ]),
  )
  vm.form.kind = 'sqlite'
  await settle()
  assert.equal(view.invalid().length, 0)
  await submit(forms(view)[0])
  assert.equal(calls.create.length, 1)
  assert.deepEqual(calls.create[0][0], {
    name: 'Source',
    kind: 'sqlite',
    params: { database: 'source.sqlite' },
  })
})

test('real number/password fields preserve null defaults, zero and credential whitespace', async (t) => {
  const view = await mountSources(t)
  const { vm, calls } = view
  vm.openCreate()
  vm.form.kind = 'mysql'
  await settle()
  for (const [key, value] of Object.entries({
    name: ' Network ',
    host: ' db.local ',
    database: ' catalog ',
    user: ' reader ',
    credential: '  synthetic secret  ',
  }))
    await input(view.field(key), value)
  await input(view.field('port'), '0')
  await vm.testConnection()
  assert.deepEqual(calls.testConnection[0][0], {
    kind: 'mysql',
    params: { host: 'db.local', port: 0, database: 'catalog', user: 'reader' },
    credential: '  synthetic secret  ',
  })
  await input(view.field('port'), '')
  assert.equal(vm.form.port, null)
  await input(view.field('credential'), '')
  await vm.testConnection()
  assert.equal(calls.testConnection[1][0].params.port, 3306)
  assert.equal('credential' in calls.testConnection[1][0], false)
  vm.form.kind = 'postgresql'
  await settle()
  await vm.testConnection()
  assert.equal(calls.testConnection[2][0].params.port, 5432)
  vm.testResult = { ok: true, table_count: null }
  assert.ok(!vm.testFeedback.includes('0'))
  vm.testResult = { ok: true, table_count: 0 }
  assert.ok(vm.testFeedback.includes('0'))
  vm.testResult = { ok: false }
  assert.equal(vm.testFeedback, view.i18n.global.t('dataAccess.sources.connection.failed'))
})

test('real edit fields focus invalid name; PUT omits masked params and empty credential; failure retains draft', async (t) => {
  let fail = true
  const view = await mountSources(t, {
    update: async () => {
      if (fail) throw new Error('503')
      return { id: 7 }
    },
  })
  const { vm, calls } = view
  vm.openEdit({ ...source(7), params: { password: '***' } })
  await settle()
  assert.equal(vm.editForm.credential, '')
  await input(view.field('name'), ' ')
  await submit(forms(view)[0])
  assert.equal(calls.update.length, 0)
  assert.equal(view.tree.activeElement, view.field('name'))
  await input(view.field('name'), ' Renamed ')
  await vm.saveEdit()
  await settle()
  assert.deepEqual(calls.update[0], [7, { name: 'Renamed' }])
  assert.equal(vm.showEdit, true)
  assert.equal(vm.editForm.name, ' Renamed ')
  assert.ok(vm.editError)
  fail = false
  await input(view.field('credential'), '  ')
  await submit(forms(view)[0])
  assert.deepEqual(calls.update[1], [7, { name: 'Renamed', credential: '  ' }])
  assert.equal(vm.showEdit, false)
})

test('real async validation locks submissions without disabling focus and rejects changed sessions', async (t) => {
  const view = await mountSources(t)
  const { vm, calls } = view
  vm.openCreate()
  await settle()
  await input(view.field('name'), 'Source')
  await input(view.field('database'), 'source.sqlite')
  const gate = deferred()
  vm.rules.name.validator = () => gate.promise
  await settle()
  const first = vm.createSource()
  const duplicate = vm.createSource()
  assert.equal(vm.createBusy, true)
  assert.equal(vm.saving, false)
  assert.equal(view.field('name').props.disabled, false)
  gate.resolve(true)
  await Promise.all([first, duplicate])
  assert.equal(calls.create.length, 1)

  for (const change of ['draft', 'session', 'permission']) {
    vm.openCreate()
    await settle()
    vm.form.name = 'Source'
    vm.form.database = 'source.sqlite'
    await settle()
    const pending = deferred()
    vm.rules.name.validator = () => pending.promise
    await settle()
    const save = vm.createSource()
    if (change === 'draft') {
      vm.form.database = 'other'
      vm.form.database = 'source.sqlite'
    }
    if (change === 'session') {
      vm.showCreate = false
      vm.openCreate()
    }
    if (change === 'permission') vm.auth.user.role = 'VIEWER'
    pending.resolve(true)
    await save
    assert.equal(calls.create.length, 1, change)
  }
})

test('real SearchPanel sends one submit/clear/reset; SearchTable pages the complete 23-row collection', async (t) => {
  const view = await mountSources(t, {
    list: async () => Array.from({ length: 23 }, (_, index) => source(index + 1)),
  })
  const { vm, calls } = view
  const rows = () =>
    find(view.tree, (n) => n.type === 'tbody').flatMap((n) =>
      find(n, (child) => child.type === 'tr'),
    )
  assert.equal(rows().length, 20)
  vm.page = 2
  await settle()
  assert.equal(rows().length, 3)
  assert.ok(contents(rows()[0]).includes('Source 21'))
  const link = find(rows()[0], (n) => n.type === 'a')[0]
  assert.deepEqual(link.props['data-to'], { name: 'data-catalog', query: { datasourceId: 21 } })
  const search = find(view.tree, (n) => n.type === 'input' && n.props.type === 'search')[0]
  await input(search, '  submitted  ')
  assert.equal(calls.list.length, 1)
  assert.equal(rows().length, 3, 'unsubmitted query must not hide loaded rows')
  const panel = find(
    view.tree,
    (n) => n.type === 'form' && String(n.props.class).includes('search-panel'),
  )[0]
  await submit(panel)
  assert.equal(calls.list.length, 2)
  assert.equal(calls.list[1][0].q, 'submitted')
  assert.equal(vm.page, 1)
  vm.kindFilter = 'mysql'
  vm.statusFilter = 'CONNECTED'
  await click(button(view.tree, view.i18n.global.t('ds.search.clear')))
  assert.equal(calls.list.length, 3)
  assert.equal(vm.kindFilter, null)
  assert.equal(vm.statusFilter, null)
  assert.equal(vm.appliedQuery, '')
  panel.props.onReset({ preventDefault() {} })
  await settle()
  assert.equal(calls.list.length, 4)
  assert.equal(rows().length, 20)
})
