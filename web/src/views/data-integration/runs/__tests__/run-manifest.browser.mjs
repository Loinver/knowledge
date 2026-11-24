import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

import {
  capture,
  expect,
  getData,
  responseData,
  settleApi,
  test,
} from '../../../../../../e2e/ui-redesign-fixtures.ts'

const copy = JSON.parse(readFileSync(resolve('web/src/locales/zh-CN.json'), 'utf8'))
async function postData(api, path, data) {
  return responseData(await api.post(`/api/v1${path}`, { data }))
}

test('real run summary links the published snapshot, keeps kbReturn and exports loaded quarantine', async ({
  signedIn: page,
  routeCatalog: catalog,
  identity,
  evidence,
}, info) => {
  // The run export intentionally returns its whitelist directly, without the JSON envelope.
  const response = await identity.api.get(`/api/v1/extraction/runs/${catalog.runId}/export`)
  expect(response.ok()).toBe(true)
  const report = await response.json()
  const rows = await getData(identity.api, `/extraction/runs/${catalog.runId}/quarantine`)
  expect(report.publication.graph_revision_id).toBe(catalog.graphId)
  const kbReturn = '/knowledge-bases/12/search?q=source%20evidence&mode=KEYWORD'
  await page.goto(`/extraction/runs?run=${catalog.runId}&kbReturn=${encodeURIComponent(kbReturn)}`)
  await settleApi(page, evidence)
  const drawer = page.getByRole('dialog')
  await expect(drawer).toBeVisible()
  const graph = drawer.getByRole('link', { name: copy.page.graphBrowse, exact: true })
  const target = new URL(await graph.getAttribute('href'), page.url())
  expect(target.pathname).toBe('/graph')
  expect(target.searchParams.get('graph')).toBe(String(catalog.graphId))
  expect(target.searchParams.get('kbReturn')).toBe(kbReturn)
  await expect(drawer.getByText(copy.graph.history, { exact: true })).toBeVisible()
  await drawer.getByRole('button', { name: copy.extractionUi.summary, exact: true }).click()
  await settleApi(page, evidence)
  if (rows.length)
    await expect(drawer.locator('.run-quarantine tbody tr')).toHaveCount(Math.min(rows.length, 20))
  else await expect(drawer.getByText(copy.graph.noQuarantine, { exact: true })).toBeVisible()
  const pending = page.waitForEvent('download')
  await drawer.getByRole('button', { name: copy.graph.export.title, exact: true }).click()
  const file = await pending
  expect(file.suggestedFilename()).toBe(`run-${catalog.runId}-quarantine.json`)
  expect(JSON.parse(readFileSync(await file.path(), 'utf8'))).toEqual({
    run_id: catalog.runId,
    quarantine: rows,
  })
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 900 })
    await capture(
      page,
      info,
      evidence,
      `run-summary-${width}`,
      'real publication manifest and loaded run quarantine',
    )
  }
})

test('real failed run retains the current graph, has no fabricated publication and exports nonempty quarantine', async ({
  signedIn: page,
  routeCatalog: catalog,
  identity,
  evidence,
}, info) => {
  const sourcePath = join(
    mkdtempSync(join(process.env.KG_E2E_TEMP_DIR, 'run-failure-source-')),
    'source.sqlite',
  )
  execFileSync(resolve('server/.venv/bin/python'), [
    '-c',
    `import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as connection:
    connection.execute('CREATE TABLE enterprise (id INTEGER PRIMARY KEY, name TEXT, business_key TEXT)')
    connection.execute("INSERT INTO enterprise VALUES (1, 'Example enterprise', NULL)")`,
    sourcePath,
  ])
  const source = await postData(identity.api, '/datasources', {
    name: `FailedBusinessKeySource${Date.now()}`,
    kind: 'sqlite',
    params: { database: sourcePath },
  })
  await postData(identity.api, `/datasources/${source.id}/metadata/capture`)
  const mapping = await postData(identity.api, '/mappings', {
    name: `FailedBusinessKeyMapping${Date.now()}`,
    ontology_id: catalog.ontology.id,
    draft: {
      entity_maps: [
        {
          entity_type: catalog.published.name,
          table: 'enterprise',
          schema: 'main',
          key_fields: ['id'],
          match_keys: ['business_key'],
          fusion: { priority: 1, null_policy: 'IGNORE', conflict_policy: 'PRIORITY' },
          field_maps: [
            {
              target_attr: 'name',
              source_field: 'name',
              transform: 'IDENTITY',
              null_policy: 'REQUIRED',
            },
          ],
        },
      ],
      rel_maps: [],
    },
  })
  const revision = await postData(identity.api, `/mappings/${mapping.id}/publish`, {
    if_match: mapping.current_revision,
  })
  const result = await postData(identity.api, '/extraction/runs', {
    mapping_revision_id: revision.id,
    datasource_id: source.id,
    namespace: catalog.ontology.iri,
  })
  expect(result.run.status).toBe('FAILED')
  // The start endpoint returns the current graph, including the previous successful
  // publication after a failed run. It must not claim that the failed run published it.
  expect(result.graph_revision.id).toBe(catalog.graphId)
  expect(result.graph_revision.run_id).toBe(catalog.runId)
  const rows = await getData(identity.api, `/extraction/runs/${result.run.id}/quarantine`)
  expect(rows.length).toBeGreaterThan(0)
  const graphs = await getData(identity.api, '/extraction/graph/revisions')
  expect(graphs.find((graph) => graph.is_current).id).toBe(catalog.graphId)
  await page.goto(`/extraction/runs?run=${result.run.id}`)
  await settleApi(page, evidence)
  const drawer = page.getByRole('dialog')
  await expect(drawer.getByText(copy.extractionUi.resultProtected, { exact: true })).toBeVisible()
  await expect(drawer.getByRole('link', { name: copy.page.graphBrowse, exact: true })).toHaveCount(
    0,
  )
  await drawer.getByRole('button', { name: copy.extractionUi.summary, exact: true }).click()
  await settleApi(page, evidence)
  await expect(drawer.locator('.run-quarantine tbody tr')).toHaveCount(Math.min(rows.length, 20))
  const pending = page.waitForEvent('download')
  await drawer.getByRole('button', { name: copy.graph.export.title, exact: true }).click()
  const file = await pending
  expect(JSON.parse(readFileSync(await file.path(), 'utf8'))).toEqual({
    run_id: result.run.id,
    quarantine: rows,
  })
  await capture(
    page,
    info,
    evidence,
    'failed-run-quarantine',
    'real missing-business-key failure with retained current graph and original quarantine fields',
  )
})

test('array-only run pages keep all rows and can return from the empty page after a full batch', async ({
  signedIn: page,
  routeCatalog: catalog,
  identity,
}) => {
  const source = await getData(identity.api, `/extraction/runs/${catalog.runId}`)
  // Controlled HTTP rows in the isolated test only; this endpoint has no total field.
  const rows = Array.from({ length: 20 }, (_, index) => ({ ...source, id: 8001 + index }))
  const pages = []
  await page.route('**/api/v1/extraction/runs?*', async (route) => {
    const requested = Number(new URL(route.request().url()).searchParams.get('page'))
    pages.push(requested)
    await route.fulfill({
      json: { code: 'KG.OK', message: '', data: requested === 1 ? rows : [] },
    })
  })
  await page.goto('/extraction/runs')
  await expect(page.locator('main table tbody tr[data-row-key]')).toHaveCount(20)
  await expect(page.getByText('当前 20 项', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: copy.runs.next, exact: true })).toBeEnabled()
  await page.getByRole('button', { name: copy.runs.next, exact: true }).click()
  await expect(page.getByText(copy.runs.empty, { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: copy.runs.next, exact: true })).toBeDisabled()
  await page.getByRole('button', { name: copy.runs.previous, exact: true }).click()
  await expect(page.locator('main table tbody tr[data-row-key]')).toHaveCount(20)
  expect(pages).toEqual([1, 2, 1])
})
