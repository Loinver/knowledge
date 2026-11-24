import assert from 'node:assert/strict'
import { test } from 'node:test'

import { deferred, mount, render, settle } from './catalog-harness.mjs'

const source = (id) => ({ id, name: `Source ${id}`, kind: 'SQLITE', status: 'CONNECTED' })
const column = (name, extra = {}) => ({
  name,
  type: 'INTEGER',
  nullable: false,
  primary_key: false,
  foreign_key: null,
  ...extra,
})
const snapshot = (id, datasource_id = 1, extra = {}) => ({
  id,
  datasource_id,
  revision: id,
  captured_at: '2026-11-23T01:02:03Z',
  catalog: {
    table_count: 1,
    column_count: 1,
    schemas: [
      {
        schema: 'main',
        tables: [{ name: `items${id}`, type: 'table', columns: [column('zero')] }],
      },
    ],
  },
  diff: null,
  ...extra,
})
const preview = (rows = [], truncated = false) => ({
  datasource_id: 1,
  schema: 'main',
  table: 'items10',
  columns: [{ name: 'value', type: 'INTEGER' }],
  rows,
  truncated,
  total_returned: rows.length,
})
const noSnapshot = { code: 'KG.RESOURCE_NOT_FOUND', params: { reason: 'no_snapshot' } }
const failure = { code: 'KG.SOURCE_UNREACHABLE' }
const catalogExpose =
  'auth,datasources,datasourceId,snapshots,snapshotId,snapshot,catalog,diff,schemas,visibleColumns,selectedSchema,selectedTable,selectedColumn,expandedSchemas,references,loadingDatasources,loadingCatalog,capturing,loadingReferences,datasourceError,catalogError,referencesError,hasSnapshot,canWrite,datasourceOptions,snapshotOptions,loadDatasources,loadDatasourceCatalog,loadSnapshot,selectSnapshot,chooseTable,loadReferences,captureMetadata,openPreview,formatNumber'
const previewExpose =
  'auth,datasources,datasourceId,snapshot,selectedSchema,selectedTable,limit,offset,result,datasourcesLoading,metadataLoading,previewLoading,datasourcesError,metadataError,previewError,noMetadata,rowData,tableColumns,rangeLabel,canPreview,loadDatasources,loadLatestMetadata,captureMetadata,runPreview,renderCell'

async function setup(t, entry = 'DataCatalogPage.vue', overrides = {}, role = 'EDITOR', start) {
  const api = {
    datasourcesApi: {
      list: async () => [source(1), source(2), source(0)],
      preview: async () => preview(),
      ...overrides.datasourcesApi,
    },
    metadataApi: {
      snapshots: async (id) => [
        { id: id * 10, revision: id * 10, captured_at: '2026-11-23T01:02:03Z' },
      ],
      latest: async (id) => snapshot(id * 10, id),
      get: async (id) => snapshot(id),
      references: async (table) => ({ table, references: [] }),
      capture: async (id) => snapshot(id * 10 + 1, id),
      ...overrides.metadataApi,
    },
  }
  const ctx = await mount(
    entry,
    api,
    entry === 'DataCatalogPage.vue' ? catalogExpose : previewExpose,
    start ?? (entry === 'DataCatalogPage.vue' ? '/catalog' : '/preview'),
    role,
  )
  t.after(ctx.stop)
  return ctx
}

test('catalog datasource A to B ignores stale metadata success, error and finally', async (t) => {
  for (const oldFails of [false, true])
    await t.test(String(oldFails), async (t) => {
      const old = deferred(),
        current = deferred()
      const { vm } = await setup(t, undefined, {
        metadataApi: { latest: (id) => (id === 1 ? old.promise : current.promise) },
      })
      vm.datasourceId = 2
      if (oldFails) old.reject(failure)
      else old.resolve(snapshot(10))
      await settle()
      assert.equal(vm.loadingCatalog, true)
      assert.equal(vm.snapshot, null)
      assert.equal(vm.catalogError, '')
      current.resolve(snapshot(20, 2))
      await settle()
      assert.equal(vm.snapshot.id, 20)
      assert.equal(vm.loadingCatalog, false)
    })
})

test('catalog snapshot A to B to A retains the latest A and rejects stale finalizers', async (t) => {
  const requests = []
  const { vm } = await setup(t, undefined, {
    metadataApi: {
      get: () => {
        const request = deferred()
        requests.push(request)
        return request.promise
      },
    },
  })
  for (const id of [11, 12, 11]) {
    vm.snapshotId = id
    vm.selectSnapshot()
  }
  requests[0].resolve(snapshot(11))
  requests[1].reject(failure)
  await settle()
  assert.equal(vm.snapshot, null)
  assert.equal(vm.loadingCatalog, true)
  assert.equal(vm.catalogError, '')
  requests[2].resolve(snapshot(11, 1, { revision: 99 }))
  await settle()
  assert.equal(vm.snapshot.revision, 99)
  assert.equal(vm.selectedTable, 'items11')
})

test('references A to B to A ignore stale success, error and finally', async (t) => {
  const requests = []
  const { vm } = await setup(t, undefined, {
    metadataApi: {
      references: (table, signal) => {
        if (table.startsWith('items')) return Promise.resolve({ table, references: [] })
        const request = deferred()
        requests.push({ ...request, signal })
        return request.promise
      },
    },
  })
  for (const name of ['A', 'B', 'A']) vm.chooseTable('main', name)
  requests[0].resolve({ references: [{ mapping_id: 1 }] })
  requests[1].reject(failure)
  await settle()
  assert.equal(requests[0].signal.aborted, true)
  assert.equal(requests[1].signal.aborted, true)
  assert.equal(vm.references, null)
  assert.equal(vm.referencesError, '')
  assert.equal(vm.loadingReferences, true)
  requests[2].resolve({ references: [{ mapping_id: 3 }] })
  await settle()
  assert.equal(vm.references.references[0].mapping_id, 3)
})

test('catalog capture uses captured datasource, suppresses duplicates and does not clear a newer capture', async (t) => {
  const requests = []
  const { vm } = await setup(t, undefined, {
    metadataApi: {
      capture: (id) => {
        const request = deferred()
        requests.push({ ...request, id })
        return request.promise
      },
    },
  })
  const old = vm.captureMetadata()
  await vm.captureMetadata()
  assert.deepEqual(
    requests.map((r) => r.id),
    [1],
  )
  vm.datasourceId = 2
  await settle()
  const current = vm.captureMetadata()
  requests[0].resolve(snapshot(11, 1))
  await old
  assert.equal(vm.snapshot.datasource_id, 2)
  assert.equal(vm.capturing, true)
  requests[1].resolve(snapshot(21, 2))
  await current
  assert.equal(vm.snapshot.id, 21)
  assert.equal(vm.capturing, false)
  assert.equal(vm.snapshots[0].id, 21)
})

test('catalog snapshot load invalidates capture busy state and its late failure', async (t) => {
  const pending = deferred()
  const { vm } = await setup(t, undefined, { metadataApi: { capture: () => pending.promise } })
  const capture = vm.captureMetadata()
  await vm.loadSnapshot(9)
  pending.reject(failure)
  await capture
  assert.equal(vm.snapshot.id, 9)
  assert.equal(vm.capturing, false)
  assert.equal(vm.catalogError, '')
})

test('catalog preserves removed columns and every removed table in an absent schema', async (t) => {
  const { vm } = await setup(t)
  vm.diff = {
    tables: [
      { schema: 'old', name: 'a', type: 'removed' },
      { schema: 'old', name: 'b', type: 'removed' },
    ],
    columns: [
      {
        schema: 'main',
        table: 'items10',
        column: 'gone',
        type: 'removed',
        details: 'removed field',
      },
    ],
    summary: {},
  }
  assert.deepEqual(
    vm.schemas.find((s) => s.name === 'old').tables.map((x) => x.name),
    ['a', 'b'],
  )
  assert.equal(vm.visibleColumns.find((c) => c.name === 'gone').diff.type, 'removed')
  assert.equal(vm.visibleColumns.find((c) => c.name === 'zero').nullable, false)
  assert.equal(vm.visibleColumns.find((c) => c.name === 'zero').foreign_key, null)
  vm.chooseTable('old', 'b')
  await settle()
  await vm.openPreview()
  assert.equal(vm.selectedTable, 'b')
})

test('catalog preview route retains datasource, schema, table and structure snapshot', async (t) => {
  const { vm, router } = await setup(t)
  vm.openPreview()
  await settle()
  assert.equal(router.currentRoute.value.name, 'sample-preview')
  assert.deepEqual(router.currentRoute.value.query, {
    datasourceId: '1',
    schema: 'main',
    table: 'items10',
    snapshot: '10',
  })
})

test('catalog zero IDs remain numbers and null clears identity and expires metadata', async (t) => {
  const pending = deferred()
  const { vm } = await setup(t, undefined, {
    metadataApi: { latest: (id) => (id === 0 ? pending.promise : Promise.resolve(snapshot(10))) },
  })
  vm.datasourceId = 0
  assert.equal(typeof vm.datasourceOptions.find((x) => x.value === 0).value, 'number')
  vm.datasourceId = null
  pending.resolve(snapshot(0, 0))
  await settle()
  assert.equal(vm.snapshot, null)
  assert.equal(vm.snapshotId, null)
  assert.equal(vm.hasSnapshot, false)
  assert.equal(vm.loadingCatalog, false)
})

test('catalog no_snapshot is empty while ordinary failure remains an error', async (t) => {
  for (const error of [noSnapshot, failure])
    await t.test(error.code, async (t) => {
      const { vm } = await setup(t, undefined, {
        metadataApi: {
          snapshots: async () => [],
          latest: async () => {
            throw error
          },
        },
      })
      assert.equal(vm.hasSnapshot, false)
      assert.equal(Boolean(vm.catalogError), error !== noSnapshot)
    })
})

test('both pages reject VIEWER capture even when called directly', async (t) => {
  for (const entry of ['DataCatalogPage.vue', 'preview/SamplePreviewPage.vue'])
    await t.test(entry, async (t) => {
      let writes = 0
      const { vm } = await setup(
        t,
        entry,
        {
          metadataApi: {
            capture: async () => {
              writes++
              return snapshot(1)
            },
          },
        },
        'VIEWER',
      )
      assert.equal(vm.canWrite ?? vm.auth.user.role === 'EDITOR', false)
      await vm.captureMetadata()
      assert.equal(writes, 0)
    })
})

test('both datasource loaders ignore stale retry success and finally', async (t) => {
  for (const entry of ['DataCatalogPage.vue', 'preview/SamplePreviewPage.vue'])
    await t.test(entry, async (t) => {
      const requests = []
      const { vm } = await setup(t, entry, {
        datasourcesApi: {
          list: (_params, signal) => {
            const request = deferred()
            requests.push({ ...request, signal })
            return request.promise
          },
        },
      })
      const retry = vm.loadDatasources()
      requests[0].resolve([source(0)])
      await settle()
      assert.equal(requests[0].signal.aborted, true)
      assert.equal(vm.datasources.length, 0)
      assert.equal(vm.loadingDatasources ?? vm.datasourcesLoading, true)
      requests[1].resolve([source(2)])
      await retry
      await settle()
      assert.equal(vm.datasourceId, 2)
    })
})

test('preview metadata A to B to A ignores stale success, failure and finally', async (t) => {
  const requests = []
  const { vm } = await setup(t, 'preview/SamplePreviewPage.vue', {
    metadataApi: {
      latest: () => {
        const request = deferred()
        requests.push(request)
        return request.promise
      },
    },
  })
  vm.datasourceId = 2
  const b = vm.loadLatestMetadata()
  vm.datasourceId = 1
  const a = vm.loadLatestMetadata()
  requests[0].resolve(snapshot(10))
  requests[1].reject(failure)
  await b
  await settle()
  assert.equal(vm.metadataLoading, true)
  assert.equal(vm.metadataError, '')
  assert.equal(vm.snapshot, null)
  requests[2].resolve(snapshot(12))
  await a
  assert.equal(vm.snapshot.id, 12)
})

test('preview capture completion belongs to its datasource and newer metadata stays busy', async (t) => {
  const capture = deferred(),
    latest = deferred()
  const { vm } = await setup(t, 'preview/SamplePreviewPage.vue', {
    metadataApi: {
      capture: () => capture.promise,
      latest: (id) => (id === 2 ? latest.promise : Promise.resolve(snapshot(10))),
    },
  })
  const old = vm.captureMetadata()
  vm.datasourceId = 2
  const current = vm.loadLatestMetadata()
  capture.resolve(snapshot(11))
  await old
  assert.equal(vm.snapshot, null)
  assert.equal(vm.metadataLoading, true)
  latest.resolve(snapshot(20, 2))
  await current
  assert.equal(vm.snapshot.datasource_id, 2)
})

test('preview limit change synchronously aborts stale success/error/finally', async (t) => {
  for (const oldFails of [false, true])
    await t.test(String(oldFails), async (t) => {
      const requests = []
      const { vm } = await setup(t, 'preview/SamplePreviewPage.vue', {
        datasourcesApi: {
          preview: (payload, signal) => {
            const request = deferred()
            requests.push({ ...request, payload, signal })
            return request.promise
          },
        },
      })
      const old = vm.runPreview()
      await vm.runPreview()
      assert.equal(requests.length, 1)
      vm.limit = 50
      assert.equal(requests[0].signal.aborted, true)
      const current = vm.runPreview()
      if (oldFails) requests[0].reject(failure)
      else requests[0].resolve(preview([{ value: 0 }]))
      await old
      assert.equal(vm.result, null)
      assert.equal(vm.previewError, '')
      assert.equal(vm.previewLoading, true)
      assert.equal(requests[0].payload.limit, 20)
      assert.equal(requests[1].payload.limit, 50)
      requests[1].resolve(preview([{ value: false }]))
      await current
      assert.equal(vm.result.rows[0].value, false)
    })
})

test('preview table and schema selection expire pending samples immediately', async (t) => {
  for (const field of ['selectedTable', 'selectedSchema'])
    await t.test(field, async (t) => {
      const pending = deferred()
      let signal
      const { vm } = await setup(t, 'preview/SamplePreviewPage.vue', {
        datasourcesApi: {
          preview: (_payload, currentSignal) => {
            signal = currentSignal
            return pending.promise
          },
        },
      })
      vm.snapshot.catalog.schemas.push({
        schema: 'other',
        tables: [{ name: 'other', columns: [] }],
      })
      const operation = vm.runPreview()
      vm[field] = 'other'
      assert.equal(signal.aborted, true)
      assert.equal(vm.previewLoading, false)
      pending.resolve(preview([{ value: 'old table' }]))
      await operation
      assert.equal(vm.result, null)
      assert.equal(vm.previewError, '')
    })
})

test('preview cells preserve zero, false, null, missing and source row-number fields', async (t) => {
  const { vm } = await setup(t, 'preview/SamplePreviewPage.vue')
  const raw = { zero: 0, flag: false, empty: null, __rowNumber: 77, rowNumber: 88, row: 99 }
  vm.result = preview([raw])
  assert.deepEqual(vm.rowData[0].row, raw)
  assert.equal(vm.rowData[0].rowNumber, 1)
  assert.equal(vm.renderCell(0).children, '0')
  assert.equal(vm.renderCell(false).children, 'false')
  assert.notEqual(vm.renderCell(null).children, vm.renderCell(undefined).children)
  for (const value of [
    0.0001,
    1.23456,
    1234567890123.4568,
    Number.MAX_SAFE_INTEGER,
    Number.MAX_VALUE,
    Number.MIN_VALUE,
  ]) {
    const cell = vm.renderCell(value)
    assert.equal(cell.children, String(value))
    assert.equal(cell.props.title, String(value))
    assert.equal(Number(cell.children), value)
  }
  assert.equal(vm.renderCell(1234).children, '1234')
  assert.equal(vm.tableColumns[0].render({ row: {}, rowNumber: 1234 }).children, '1,234')
})

test('preview pagination uses offsets and truncated batches, including empty last page', async (t) => {
  const payloads = []
  const { vm } = await setup(t, 'preview/SamplePreviewPage.vue', {
    datasourcesApi: {
      preview: async (payload) => {
        payloads.push({ ...payload })
        return payload.offset === 0
          ? preview(
              Array.from({ length: 20 }, (_, value) => ({ value })),
              true,
            )
          : preview([], false)
      },
    },
  })
  await vm.runPreview()
  assert.equal(vm.result.truncated, true)
  await vm.runPreview(20)
  assert.equal(vm.result.truncated, false)
  assert.equal(vm.result.rows.length, 0)
  assert.equal(vm.offset, 20)
  await vm.runPreview(0)
  assert.deepEqual(
    payloads.map((x) => x.offset),
    [0, 20, 0],
  )
  assert.ok(payloads.every((x) => typeof x.limit === 'number' && !('total' in x)))
  for (const invalid of [null, 0, 101]) {
    vm.limit = invalid
    await vm.runPreview()
  }
  assert.equal(payloads.length, 3)
})

test('preview missing metadata and empty results remain distinct from errors', async (t) => {
  const { vm } = await setup(t, 'preview/SamplePreviewPage.vue', {
    datasourcesApi: {
      preview: async () => {
        throw failure
      },
    },
  })
  await vm.runPreview()
  assert.equal(vm.result, null)
  assert.equal(vm.previewError, failure.code)
  assert.equal(vm.previewLoading, false)
})

test('unmounted catalog and preview ignore late operations', async (t) => {
  for (const entry of ['DataCatalogPage.vue', 'preview/SamplePreviewPage.vue'])
    await t.test(entry, async (t) => {
      const pending = deferred()
      const { vm, stop } = await setup(t, entry, {
        metadataApi: { capture: () => pending.promise },
      })
      const before = vm.snapshot.id
      const operation = vm.captureMetadata()
      stop()
      pending.resolve(snapshot(99))
      await operation
      assert.equal(vm.snapshot?.id ?? null, entry === 'DataCatalogPage.vue' ? before : null)
    })
})

test('real catalog UI renders labeled selectors, permissions, removed diff and selected identity', async () => {
  const seed = `datasources.value = [${JSON.stringify(source(1))}]; datasourceId.value = 1; loadingDatasources.value = false; loadingCatalog.value = false; snapshot.value = ${JSON.stringify(snapshot(10))}; snapshotId.value = 10; snapshots.value = [{id:10, revision:10, captured_at:'2026-11-23T01:02:03Z'}]; hasSnapshot.value = true; catalog.value = parseCatalog(snapshot.value.catalog); diff.value = {tables:[], columns:[{schema:'main',table:'items10',column:'gone',type:'removed'}],summary:{columns_removed:1}}; selectedSchema.value='main'; selectedTable.value='items10'; selectedColumn.value='zero'; expandedSchemas.value=new Set(['main']);`
  for (const locale of ['en-US', 'zh-CN']) {
    const { html, t } = await render('DataCatalogPage.vue', seed, '/catalog', 'VIEWER', locale)
    assert.match(html, /id="catalog-datasource"/)
    assert.match(html, /id="catalog-snapshot"/)
    assert.match(html, /role="combobox"/)
    assert.match(html, /aria-expanded="true"/)
    assert.match(html, /aria-pressed="true"/)
    assert.match(html, /data-row-key="gone"/)
    assert.ok(html.includes(t('dataAccess.catalog.diff.removed')))
    assert.match(
      html,
      /<button[^>]*disabled[^>]*>[\s\S]*?Capture|<button[^>]*disabled[^>]*>[\s\S]*?采集/,
    )
    assert.doesNotMatch(html, /n-select|n-data-table|<select/)
  }
})

test('real catalog empty snapshot blocks VIEWER capture and separates errors/loading/empty', async () => {
  const base = `datasources.value=[${JSON.stringify(source(1))}]; loadingDatasources.value=false; datasourceId.value=1; loadingCatalog.value=false;`
  const empty = await render('DataCatalogPage.vue', base, '/catalog', 'VIEWER')
  assert.ok(empty.html.includes(empty.t('dataAccess.catalog.states.noSnapshot')))
  const captureButtons = empty.html
    .match(/<button[^>]*>[\s\S]*?<\/button>/g)
    .filter((x) => x.includes('Capture schema'))
  assert.equal(captureButtons.length, 2)
  assert.ok(captureButtons.every((x) => x.includes('disabled')))
  const error = await render('DataCatalogPage.vue', `${base} catalogError.value='catalog failure';`)
  assert.match(error.html, /catalog failure/)
  assert.ok(!error.html.includes(error.t('dataAccess.catalog.states.noSnapshot')))
  const loading = await render('DataCatalogPage.vue', `${base} loadingCatalog.value=true;`)
  assert.match(loading.html, /role="status"/)
  assert.ok(!loading.html.includes(loading.t('dataAccess.catalog.states.noSnapshot')))
})

test('real preview UI preserves numeric precision and raw values in both locales, with no false total', async () => {
  const values = {
    value: 0,
    flag: false,
    empty: null,
    __rowNumber: 77,
    small: 0.0001,
    decimal: 1.23456,
    largeDecimal: 1234567890123.4568,
    largeInteger: Number.MAX_SAFE_INTEGER,
    largest: Number.MAX_VALUE,
    smallest: Number.MIN_VALUE,
  }
  const data = {
    ...preview([values], true),
    columns: [...Object.keys(values), 'missing'].map((name) => ({
      name,
      type: 'value',
    })),
  }
  const seed = `datasources.value=[${JSON.stringify(source(1))}]; datasourceId.value=1; snapshot.value=${JSON.stringify(snapshot(10))}; selectedSchema.value='main'; selectedTable.value='items10'; metadataLoading.value=false; result.value=${JSON.stringify(data)};`
  for (const locale of ['en-US', 'zh-CN']) {
    const { html, t } = await render(
      'preview/SamplePreviewPage.vue',
      seed,
      '/preview?datasourceId=1&snapshot=9',
      'EDITOR',
      locale,
    )
    assert.ok(html.includes(t('ui.livePreviewContext')))
    for (const id of ['preview-datasource', 'preview-schema', 'preview-table', 'preview-limit'])
      assert.ok(html.includes(`id="${id}"`))
    assert.match(html, /data-row-key="1"/)
    assert.match(html, />false</)
    assert.match(html, />77</)
    for (const value of Object.values(values).filter((value) => typeof value === 'number')) {
      const text = String(value)
      assert.ok(html.includes(`title="${text}">${text}</span>`), `${locale}: ${text}`)
    }
    assert.ok(html.includes('title="false">false</span>'))
    assert.ok(html.includes(t('dataAccess.preview.nullValue')))
    assert.ok(html.includes(t('extractionUi.notRecorded')))
    assert.ok(html.includes(t('dataAccess.preview.truncated')))
    assert.doesNotMatch(html, /n-data-table|n-select|ui-pagination/)
  }
})

test('real preview error renders retry without a success-empty result', async () => {
  const { html, t } = await render(
    'preview/SamplePreviewPage.vue',
    `previewError.value='SOURCE_TEST_ERROR';`,
    '/preview',
  )
  assert.match(html, /SOURCE_TEST_ERROR/)
  assert.ok(html.includes(t('dataAccess.preview.previewFailed')))
  assert.ok(html.includes(t('dataAccess.preview.errorCode', { code: 'SOURCE_TEST_ERROR' })))
  assert.ok(html.includes(t('ui.retry')) || html.includes(t('ds.retry')))
  assert.ok(!html.includes(t('dataAccess.preview.emptyResult')))
})
