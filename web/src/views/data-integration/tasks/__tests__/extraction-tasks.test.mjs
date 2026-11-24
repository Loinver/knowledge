import 'axios'

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { test } from 'node:test'

import { renderToString } from '@vue/server-renderer'
import { createPinia } from 'pinia'
import { createSSRApp, reactive, watch } from 'vue'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'

import { deferred, mount, root, settle } from '../../../../testing/view-harness.mjs'
import { load as loadReal } from '../../../semantic-assets/relation-types/__tests__/c1-render-harness.mjs'

const entry = 'views/data-integration/tasks/ExtractionTasksPage.vue'
const expose =
  'tasks,page,loading,initialized,taskError,notice,canPrevious,canNext,previousPage,nextPage,loadTasks,loadOptions,optionLoading,openCreate,showCreate,createVisible,createSession,formModel,rules,formRef,selectedMappingId,selectedDatasourceId,publishedRevisionId,namespace,incremental,runAfter,chooseMapping,revisionLoading,createTask,createError,creating,validating,canCreate,cancelTask,cancellingId,cancellationRequested,auth,locale,progressText'
const task = (id = 1, extra = {}) => ({
  id,
  mapping_revision_id: 101,
  datasource_id: 5,
  namespace: 'urn:example:',
  status: 'PENDING',
  run_id: null,
  incremental: false,
  run_after: null,
  progress: {},
  watermark: null,
  error: null,
  created_at: '2026-11-23T00:00:00Z',
  started_at: null,
  finished_at: null,
  ...extra,
})

async function setup(t, overrides = {}, role = 'EDITOR') {
  const originalWindow = globalThis.window
  const originalDocument = globalThis.document
  const timers = new Map()
  const cleared = []
  const environment = { hidden: false, accept: true, confirmations: 0 }
  globalThis.window = {
    setInterval(callback, ms) {
      assert.equal(ms, 2000)
      timers.set(1, callback)
      return 1
    },
    clearInterval(id) {
      cleared.push(id)
      timers.delete(id)
    },
    addEventListener() {},
    removeEventListener() {},
    confirm() {
      environment.confirmations++
      return environment.accept
    },
  }
  globalThis.document = environment
  const reads = []
  const writes = []
  const view = await mount(
    entry,
    {
      '@/api/extraction': {
        extractionApi: {
          tasks: async (page, signal) => {
            reads.push({ page, signal })
            return [task()]
          },
          createTask: async (input) => {
            writes.push(input)
            return task(2, input)
          },
          cancelTask: async (id) => task(id, { status: 'RUNNING' }),
          ...overrides.extraction,
        },
      },
      '@/api/mappings': {
        mappingsApi: {
          list: async () => [{ id: 1, name: 'Published', status: 'PUBLISHED' }],
          published: async (id) => ({ id: 100 + id }),
          ...overrides.mappings,
        },
      },
      '@/api/datasources': { datasourcesApi: { list: async () => [{ id: 5, name: 'Source' }] } },
    },
    expose,
    '/',
    undefined,
    role,
  )
  let stopped = false
  const stop = () => {
    if (stopped) return
    stopped = true
    view.stop()
  }
  t.after(() => {
    stop()
    if (originalWindow === undefined) delete globalThis.window
    else globalThis.window = originalWindow
    if (originalDocument === undefined) delete globalThis.document
    else globalThis.document = originalDocument
  })
  return { ...view, stop, reads, writes, timers, cleared, environment }
}

async function ready(view) {
  view.vm.openCreate()
  await view.vm.chooseMapping(1)
  view.vm.selectedDatasourceId = 5
  view.vm.namespace = ' urn:example: '
  view.vm.formRef = { validate: async () => {}, restoreValidation() {} }
  await settle()
}

async function attachRealForm(t, view) {
  const rules = reactive({ ...view.vm.rules })
  t.after(
    watch(
      () => view.vm.rules,
      (next) => Object.assign(rules, next),
      { flush: 'sync' },
    ),
  )
  const form = await mount(
    'components/business/FormContainer.vue',
    {},
    'validate,validateField,restoreValidation,errors,registered,blocked',
    '/',
    (source) => source.replace('defineExpose<FormInst>({ validate, restoreValidation })', ''),
    'EDITOR',
    { model: view.vm.formModel, rules, disabled: false, submitting: false },
  )
  t.after(form.stop)
  view.vm.formRef = { validate: form.vm.validate, restoreValidation: form.vm.restoreValidation }
  return form
}

test('real task form rejects invalid input with zero writes, focuses mapping while unlocked and rechecks published pin errors', async (t) => {
  const view = await setup(t)
  view.vm.openCreate()
  const form = await attachRealForm(t, view)
  const focused = []
  form.vm.registered.set('mapping', () => ({
    querySelector: () => ({
      focus() {
        assert.equal(view.vm.creating, false)
        assert.equal(view.vm.validating, true)
        assert.equal(form.vm.blocked, false)
        focused.push('mapping')
      },
    }),
  }))
  await view.vm.createTask()
  assert.deepEqual(focused, ['mapping'])
  assert.ok(form.vm.errors.mapping)
  assert.ok(form.vm.errors.datasource)
  assert.deepEqual(view.writes, [])
  await view.vm.chooseMapping(1)
  await settle()
  assert.equal(form.vm.errors.mapping, undefined)
  view.vm.selectedDatasourceId = 5
  for (const [field, value] of [
    ['namespace', '  '],
    ['selectedDatasourceId', '5'],
    ['incremental', 'false'],
    ['runAfter', false],
    ['runAfter', '0'],
    ['runAfter', NaN],
    ['runAfter', 1.5],
    ['runAfter', 8.64e15],
  ]) {
    const prior = view.vm[field]
    view.vm[field] = value
    await view.vm.createTask()
    assert.deepEqual(view.writes, [], `${field} must never write`)
    assert.equal(view.vm.showCreate, true)
    view.vm[field] = prior
  }
  view.vm.runAfter = 0
  view.vm.incremental = false
  await view.vm.createTask()
  assert.deepEqual(view.writes, [
    {
      mapping_revision_id: 101,
      datasource_id: 5,
      namespace: 'https://example.org/kg/',
      incremental: false,
      run_after: '1970-01-01T00:00:00.000Z',
    },
  ])
  assert.equal(view.vm.runAfter, 0)
  assert.equal(view.vm.incremental, false)
  assert.equal(view.vm.showCreate, false)
  assert.equal(view.vm.creating, false)
})

test('task creation keeps a null schedule, boolean mode and immutable payload, and refreshes page one once', async (t) => {
  const response = deferred()
  const writes = []
  const view = await setup(t, {
    extraction: {
      createTask: (input) => {
        writes.push(input)
        return response.promise
      },
    },
  })
  await ready(view)
  await attachRealForm(t, view)
  view.vm.incremental = true
  view.vm.page = 3
  await settle()
  const before = view.reads.length
  const pending = view.vm.createTask()
  await settle()
  await view.vm.createTask()
  assert.equal(writes.length, 1)
  assert.equal(view.vm.creating, true)
  assert.equal(view.vm.validating, false)
  view.vm.namespace = 'Changed after dispatch'
  view.vm.selectedDatasourceId = 9
  assert.deepEqual(writes[0], {
    mapping_revision_id: 101,
    datasource_id: 5,
    namespace: 'urn:example:',
    incremental: true,
    run_after: null,
  })
  response.resolve(task(2))
  await pending
  await settle()
  assert.equal(view.vm.page, 1)
  assert.equal(view.reads.length, before + 1)
})

test('task validation prevents duplicates and invalidates changed input, permission and old sessions', async (t) => {
  const view = await setup(t)
  await ready(view)
  for (const change of [
    () => (view.vm.namespace = 'Changed'),
    () => {
      view.vm.namespace = 'Temporary'
      view.vm.namespace = 'Changed'
    },
    () => view.vm.chooseMapping(2),
    () => (view.vm.auth.user.role = 'VIEWER'),
  ]) {
    const validation = deferred()
    let validations = 0
    view.vm.formRef = {
      validate: () => {
        validations++
        return validation.promise
      },
      restoreValidation() {},
    }
    const pending = view.vm.createTask()
    await view.vm.createTask()
    assert.equal(validations, 1)
    assert.equal(view.vm.validating, true)
    assert.equal(view.vm.creating, false)
    await change()
    validation.resolve()
    await pending
    assert.deepEqual(view.writes, [])
    assert.equal(view.vm.validating, false)
    view.vm.auth.user.role = 'EDITOR'
  }
  const old = deferred()
  view.vm.formRef = { validate: () => old.promise, restoreValidation() {} }
  const first = view.vm.createTask()
  view.vm.showCreate = false
  await ready(view)
  const current = deferred()
  view.vm.formRef = { validate: () => current.promise, restoreValidation() {} }
  const second = view.vm.createTask()
  old.resolve()
  await first
  assert.equal(view.vm.validating, true)
  assert.deepEqual(view.writes, [])
  current.reject(new Error('FORM_INVALID'))
  await second
  assert.equal(view.vm.validating, false)
  assert.equal(view.vm.showCreate, true)
})

test('closed task create responses cannot close, report into or unlock the next pending create', async (t) => {
  for (const fails of [false, true]) {
    await t.test(fails ? 'old rejection' : 'old success', async (t) => {
      const requests = []
      const view = await setup(t, {
        extraction: {
          createTask: () => {
            const response = deferred()
            requests.push(response)
            return response.promise
          },
        },
      })
      await ready(view)
      const first = view.vm.createTask()
      await settle()
      view.vm.showCreate = false
      await ready(view)
      const second = view.vm.createTask()
      await settle()
      assert.equal(requests.length, 2)
      if (fails) requests[0].reject({ code: 'KG.REVISION_CONFLICT' })
      else requests[0].resolve(task(10))
      await first
      assert.equal(view.vm.showCreate, true)
      assert.equal(view.vm.creating, true)
      assert.equal(view.vm.createError, '')
      assert.equal(view.vm.notice, '')
      requests[1].reject({ code: 'KG.REVISION_CONFLICT' })
      await second
      assert.ok(view.vm.createError)
      assert.equal(view.vm.creating, false)
      assert.equal(view.vm.namespace, ' urn:example: ')
      assert.equal(view.vm.publishedRevisionId, 101)
    })
  }
})

test('task permission ABA expires real validation without unlocking a newer validation', async (t) => {
  const view = await setup(t)
  await ready(view)
  const form = await attachRealForm(t, view)
  const firstGate = deferred()
  const secondGate = deferred()
  let validations = 0
  form.vm.$props.rules.namespace = {
    ...form.vm.$props.rules.namespace,
    validator: () => [firstGate, secondGate][validations++].promise,
  }
  await settle()
  const first = view.vm.createTask()
  await settle()
  assert.equal(validations, 1)
  assert.equal(view.vm.validating, true)
  view.vm.auth.user.role = 'VIEWER'
  assert.equal(view.vm.validating, false)
  assert.equal(view.vm.creating, false)
  view.vm.auth.user.role = 'EDITOR'
  const second = view.vm.createTask()
  await settle()
  assert.equal(validations, 2)
  firstGate.resolve(true)
  await first
  assert.deepEqual(view.writes, [])
  assert.equal(view.vm.validating, true)
  assert.equal(view.vm.showCreate, true)
  assert.equal(view.vm.createError, '')
  assert.deepEqual(form.vm.errors, {})
  secondGate.resolve(true)
  await second
  assert.equal(view.writes.length, 1)
  assert.equal(view.writes[0].mapping_revision_id, 101)
  assert.equal(view.writes[0].incremental, false)
  assert.equal(view.writes[0].run_after, null)
})

test('task permission changes expire network success and errors without closing or unlocking current creation', async (t) => {
  for (const fails of [false, true]) {
    await t.test(fails ? 'late error' : 'late success', async (t) => {
      const responses = []
      const view = await setup(t, {
        extraction: {
          createTask: () => {
            const response = deferred()
            responses.push(response)
            return response.promise
          },
        },
      })
      await ready(view)
      await attachRealForm(t, view)
      const first = view.vm.createTask()
      await settle()
      assert.equal(responses.length, 1)
      assert.equal(view.vm.creating, true)
      const reads = view.reads.length
      view.vm.auth.user.role = 'VIEWER'
      assert.equal(view.vm.creating, false)
      assert.equal(view.vm.validating, false)
      if (fails) responses[0].reject({ code: 'KG.REVISION_CONFLICT' })
      else responses[0].resolve(task(20))
      await first
      assert.equal(view.vm.showCreate, true)
      assert.equal(view.vm.notice, '')
      assert.equal(view.vm.createError, '')
      assert.equal(view.reads.length, reads)
      assert.equal(view.vm.namespace, ' urn:example: ')
      assert.equal(view.vm.publishedRevisionId, 101)

      view.vm.auth.user.role = 'EDITOR'
      const second = view.vm.createTask()
      await settle()
      view.vm.auth.user.role = 'VIEWER'
      view.vm.auth.user.role = 'EDITOR'
      const third = view.vm.createTask()
      await settle()
      assert.equal(responses.length, 3)
      if (fails) responses[1].reject({ code: 'KG.REVISION_CONFLICT' })
      else responses[1].resolve(task(21))
      await second
      assert.equal(view.vm.showCreate, true)
      assert.equal(view.vm.creating, true)
      assert.equal(view.vm.notice, '')
      assert.equal(view.vm.createError, '')
      assert.equal(view.reads.length, reads)
      responses[2].resolve(task(22))
      await third
      assert.equal(view.vm.showCreate, false)
      assert.equal(view.reads.length, reads + 1)
    })
  }
})

test('task select change clears required errors without blur and validates the current value', async (t) => {
  const view = await setup(t)
  view.vm.openCreate()
  await view.vm.chooseMapping(1)
  const form = await attachRealForm(t, view)
  await view.vm.createTask()
  assert.ok(form.vm.errors.datasource)
  const key = '__task_select_change_field'
  const validations = []
  globalThis[key] = {
    field: {
      validate: (trigger) => {
        validations.push(trigger)
        return form.vm.validateField('datasource', trigger)
      },
    },
    disabled: { value: false },
    readonly: { value: false },
    attributes: { value: {} },
  }
  const select = await mount(
    'components/ui/UiSelect.vue',
    {},
    'update',
    '/',
    (source) =>
      source.replace(
        "import { useControlField } from './useControlField'",
        `const useControlField = () => globalThis.${key}`,
      ),
    'EDITOR',
    {
      value: null,
      options: [{ value: 5, label: 'Source' }],
      'onUpdate:value': (value) => {
        view.vm.selectedDatasourceId = value
      },
    },
  )
  t.after(() => {
    select.stop()
    delete globalThis[key]
  })
  select.vm.update(5)
  await settle()
  assert.equal(view.vm.selectedDatasourceId, 5)
  assert.deepEqual(validations, ['change'])
  assert.equal(form.vm.errors.datasource, undefined)
  assert.deepEqual(view.writes, [])
  view.vm.selectedMappingId = 0
  await form.vm.validateField('mapping', 'change')
  assert.ok(form.vm.errors.mapping)
  view.vm.selectedMappingId = 1
  await form.vm.validateField('mapping', 'change')
  assert.equal(form.vm.errors.mapping, undefined)
  assert.deepEqual(view.writes, [])
})

test('mapping A to B to A preserves only the newest published revision and closing invalidates pending lookups', async (t) => {
  const requests = []
  const view = await setup(t, {
    mappings: {
      published: (id) => {
        const request = { id, ...deferred() }
        requests.push(request)
        return request.promise
      },
    },
  })
  view.vm.openCreate()
  const first = view.vm.chooseMapping(1)
  const second = view.vm.chooseMapping(2)
  const third = view.vm.chooseMapping(1)
  requests[2].resolve({ id: 103 })
  await third
  requests[0].resolve({ id: 101 })
  requests[1].reject({ code: 'KG.RESOURCE_NOT_FOUND' })
  await Promise.all([first, second])
  assert.equal(view.vm.publishedRevisionId, 103)
  assert.equal(view.vm.createError, '')
  assert.equal(view.vm.revisionLoading, false)
  const closing = view.vm.chooseMapping(2)
  view.vm.showCreate = false
  view.vm.openCreate()
  requests[3].resolve({ id: 202 })
  await closing
  assert.equal(view.vm.selectedMappingId, null)
  assert.equal(view.vm.publishedRevisionId, null)
})

test('task prev and next load real pages once for 21 rows and allow returning from an empty last page', async (t) => {
  const all = Array.from({ length: 21 }, (_, i) => task(i + 1))
  const calls = []
  const view = await setup(t, {
    extraction: {
      tasks: async (page) => {
        calls.push(page)
        return all.slice((page - 1) * 20, page * 20)
      },
    },
  })
  assert.equal(view.vm.tasks.length, 20)
  view.vm.previousPage()
  await settle()
  assert.deepEqual(calls, [1])
  view.vm.nextPage()
  await settle()
  assert.deepEqual(calls, [1, 2])
  assert.equal(view.vm.tasks[0].id, 21)
  assert.equal(view.vm.tasks.length, 1)
  assert.equal(view.vm.canNext, false)
  view.vm.nextPage()
  await settle()
  assert.deepEqual(calls, [1, 2])
  all.pop()
  view.vm.previousPage()
  await settle()
  view.vm.nextPage()
  await settle()
  assert.deepEqual(calls, [1, 2, 1, 2])
  assert.deepEqual(view.vm.tasks, [])
  assert.equal(view.vm.canPrevious, true)
  view.vm.previousPage()
  await settle()
  assert.deepEqual(calls, [1, 2, 1, 2, 1])
})

test('late task pages cannot replace current loading, rows or errors; failures remain explicit', async (t) => {
  const requests = []
  const view = await setup(t, {
    extraction: {
      tasks: (page, signal) => {
        const request = { page, signal, ...deferred() }
        requests.push(request)
        return request.promise
      },
    },
  })
  view.vm.page = 2
  await settle()
  requests[0].reject({ code: 'KG.REVISION_CONFLICT' })
  await settle()
  assert.equal(view.vm.loading, true)
  assert.equal(view.vm.taskError, '')
  requests[1].resolve([task(21)])
  await settle()
  const old = view.vm.loadTasks()
  view.vm.page = 3
  await settle()
  requests[3].reject({ code: 'KG.REVISION_CONFLICT' })
  await settle()
  requests[2].resolve([task(99)])
  await old
  assert.equal(view.vm.tasks[0].id, 21)
  assert.ok(view.vm.taskError)
  assert.equal(view.vm.canNext, false)
  assert.equal(view.vm.canPrevious, true)
})

test('task polling pauses for hidden documents and active reads and is cleaned on unmount', async (t) => {
  const requests = []
  const view = await setup(t, {
    extraction: {
      tasks: (page, signal) => {
        const request = { page, signal, ...deferred() }
        requests.push(request)
        return request.promise
      },
    },
  })
  requests[0].resolve([task()])
  await settle()
  assert.equal(view.timers.size, 1)
  const poll = view.timers.get(1)
  view.environment.hidden = true
  poll()
  assert.equal(requests.length, 1)
  view.environment.hidden = false
  poll()
  poll()
  assert.equal(requests.length, 2)
  view.stop()
  assert.deepEqual(view.cleared, [1])
  assert.equal(requests[1].signal.aborted, true)
  requests[1].resolve([task(99)])
  await settle()
  poll()
  await view.vm.loadTasks()
  assert.equal(requests.length, 2)
  assert.equal(view.vm.tasks[0].id, 1)
})

test('VIEWER handlers cannot open, create or cancel and worker cancellation remains pending', async (t) => {
  const pending = task(1, { status: 'RUNNING' })
  let current = pending
  let cancellations = 0
  const view = await setup(t, {
    extraction: {
      tasks: async () => [current],
      cancelTask: async () => {
        cancellations++
        return pending
      },
    },
  })
  await view.vm.cancelTask(pending)
  assert.deepEqual(view.vm.cancellationRequested, [1])
  assert.notEqual(view.vm.tasks[0].status, 'CANCELLED')
  await ready(view)
  view.vm.auth.user.role = 'VIEWER'
  view.vm.showCreate = false
  view.vm.openCreate()
  assert.equal(view.vm.showCreate, false)
  await view.vm.createTask()
  await view.vm.cancelTask(task(2))
  assert.equal(view.vm.cancellingId, null)
  assert.deepEqual(view.writes, [])
  assert.deepEqual(view.vm.cancellationRequested, [1])
  assert.equal(cancellations, 1)
  current = task(1, { status: 'CANCELLED' })
  await view.vm.loadTasks()
  assert.deepEqual(view.vm.cancellationRequested, [])
  assert.equal(view.vm.tasks[0].status, 'CANCELLED')
})

test('task draft guard preserves declined drafts and an unmounted create cannot reload or report success', async (t) => {
  const response = deferred()
  const view = await setup(t, { extraction: { createTask: () => response.promise } })
  await ready(view)
  view.vm.namespace = 'Unsaved'
  view.environment.accept = false
  view.vm.createVisible = false
  assert.equal(view.vm.showCreate, true)
  assert.equal(view.environment.confirmations, 1)
  view.environment.accept = true
  view.vm.createVisible = false
  assert.equal(view.vm.showCreate, false)
  await ready(view)
  const pending = view.vm.createTask()
  await settle()
  const before = view.reads.length
  view.stop()
  response.resolve(task(99))
  await pending
  assert.equal(view.vm.notice, '')
  assert.equal(view.reads.length, before)
})

test('real task SearchTable renders every current-page row without a total or second paginator and retains failure state', async () => {
  const rows = Array.from({ length: 20 }, (_, i) => task(i + 21))
  const built = await loadReal(
    entry,
    `tasks.value = ${JSON.stringify(rows)}; page.value = 2; initialized.value = true`,
  )
  const en = JSON.parse(await readFile(path.join(root, 'web/src/locales/en-US.json'), 'utf8'))
  const i18n = createI18n({ legacy: false, locale: 'en-US', messages: { 'en-US': en } })
  const pinia = createPinia()
  pinia.state.value.auth = { user: { id: 1, role: 'EDITOR' } }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { render: () => null } }],
  })
  await router.push('/')
  const html = await renderToString(createSSRApp(built.default).use(i18n).use(pinia).use(router))
  assert.equal((html.match(/data-row-key=/g) ?? []).length, 20)
  assert.match(html, /data-row-key="21"/)
  assert.match(html, /data-row-key="40"/)
  assert.ok(html.includes('search-table'))
  assert.ok(html.includes('Page 2'))
  assert.ok(html.includes('Next'))
  assert.ok(html.includes('Previous'))
  assert.doesNotMatch(html, /type="search"|ui-pagination|20 results|class="n-data-table/)
  const failed = await loadReal(entry, "initialized.value = true; taskError.value = 'Read failed'")
  const errorHtml = await renderToString(
    createSSRApp(failed.default).use(i18n).use(pinia).use(router),
  )
  assert.ok(errorHtml.includes('Read failed'))
  assert.match(errorHtml, /role="alert"/)
  assert.ok(!errorHtml.includes(en.tasks.empty))
})

test('real task status translates cancellation reasons in both locales and retains unknown reason identifiers', async () => {
  const rows = [
    task(1, { status: 'CANCELLED', error: 'cancelled_before_start' }),
    task(2, { status: 'FAILED', error: 'unknown_fixture_reason' }),
  ]
  const built = await loadReal(
    entry,
    `tasks.value = ${JSON.stringify(rows)}; initialized.value = true`,
  )
  for (const locale of ['zh-CN', 'en-US']) {
    const messages = JSON.parse(
      await readFile(path.join(root, `web/src/locales/${locale}.json`), 'utf8'),
    )
    const i18n = createI18n({ legacy: false, locale, messages: { [locale]: messages } })
    const pinia = createPinia()
    pinia.state.value.auth = { user: { id: 1, role: 'EDITOR' } }
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { render: () => null } }],
    })
    await router.push('/')
    const html = await renderToString(createSSRApp(built.default).use(i18n).use(pinia).use(router))
    assert.ok(html.includes(messages.tasks.reasons.cancelled_before_start))
    assert.ok(html.includes('unknown_fixture_reason'))
    assert.ok(!html.includes('errors.cancelled_before_start'))
    assert.ok(!html.includes('tasks.reasons.unknown_fixture_reason'))
  }
})
