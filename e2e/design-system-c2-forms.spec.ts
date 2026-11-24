import { copyFileSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

import type { components } from '../web/src/api/schema'
import {
  capture,
  expect,
  expectNoPageOverflow,
  getData,
  responseData,
  test,
  uniqueName,
  waitForApi,
} from './ui-redesign-fixtures'

const copy = JSON.parse(readFileSync(resolve('web/src/locales/zh-CN.json'), 'utf8'))
const english = JSON.parse(readFileSync(resolve('web/src/locales/en-US.json'), 'utf8'))

test('source filter keeps its selected identity while translated labels update', async ({
  signedIn: page,
}) => {
  await page.goto('/datasources')
  const filter = page.getByRole('combobox', { name: copy.dataAccess.sources.filters.status })
  await filter.click()
  await page
    .getByRole('option', { name: copy.dataAccess.sources.status.connected, exact: true })
    .click()
  await expect(filter).toHaveValue(copy.dataAccess.sources.status.connected)
  await page.getByRole('button', { name: copy.layout.switchLocale, exact: true }).click()
  const translated = page.getByRole('combobox', { name: english.dataAccess.sources.filters.status })
  await expect(translated).toHaveValue(english.dataAccess.sources.status.connected)
  await translated.click()
  await expect(
    page.getByRole('option', { name: english.dataAccess.sources.status.connected, exact: true }),
  ).toHaveAttribute('aria-selected', 'true')
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: english.layout.switchLocale, exact: true }).click()
  await expect(filter).toHaveValue(copy.dataAccess.sources.status.connected)
})

test('mapping: empty entity collection focuses add action and rejects writes', async ({
  signedIn: page,
  identity,
  routeCatalog: catalog,
}) => {
  const published = await getData<components['schemas']['MappingRevisionOut']>(
    identity.api,
    `/mappings/${catalog.mappingId}/published`,
  )
  const draft = await responseData<{ id: number }>(
    await identity.api.post('/api/v1/mappings', {
      data: {
        name: uniqueName('C2EmptyMapping'),
        ontology_id: catalog.ontology.id,
        draft: { entity_maps: published.entity_maps, rel_maps: published.rel_maps },
      },
    }),
  )
  const source = await getData<{ name: string }>(
    identity.api,
    `/datasources/${catalog.datasourceId}`,
  )
  await page.goto(`/extraction?mapping=${draft.id}`)
  await expect(page.getByTestId('entity-mapping')).toHaveCount(1)
  await page.locator('.wizard-steps').getByRole('button').nth(1).click()
  await page.locator('.datasource-form').getByRole('combobox').first().click()
  await page.getByRole('option', { name: source.name + ' · sqlite', exact: true }).click()
  await expect(page.locator('.catalog-summary')).toBeVisible()
  await page.locator('.wizard-steps').getByRole('button').nth(2).click()
  await page
    .getByTestId('entity-mapping')
    .getByRole('button', { name: copy.common.delete, exact: true })
    .first()
    .click()
  await expect(page.getByTestId('entity-mapping')).toHaveCount(0)
  let writes = 0
  page.on('request', (request) => {
    if (
      /\/api\/v1\/mappings(?:\/|$)/.test(new URL(request.url()).pathname) &&
      ['POST', 'PUT', 'DELETE'].includes(request.method())
    )
      writes++
  })
  await page
    .getByRole('complementary', { name: copy.extractionUi.versionChain, exact: true })
    .getByRole('button', { name: copy.dataAccess.mapping.saveDraft, exact: true })
    .click()
  await expect(
    page.getByRole('alert').filter({ hasText: copy.dataAccess.mapping.errors.incomplete }),
  ).toBeVisible()
  const add = page.getByTestId('add-entity-mapping')
  await expect(add).toBeFocused()
  expect(writes).toBe(0)
  await add.press('Enter')
  await expect(page.getByTestId('entity-mapping')).toHaveCount(1)
  expect(writes).toBe(0)
})

test('sources: real field validation, failed save, draft protection, local pages and credential omission', async ({
  signedIn: page,
  identity,
  network,
  evidence,
}, info) => {
  const prefix = uniqueName('C2Source')
  const sourcePath = join(process.env.KG_E2E_TEMP_DIR!, prefix + '.sqlite')
  copyFileSync(resolve('samples/enterprise_demo.sqlite'), sourcePath)
  for (let index = 0; index < 21; index++) {
    await responseData(
      await identity.api.post('/api/v1/datasources', {
        data: { name: prefix + index, kind: 'sqlite', params: { database: sourcePath } },
      }),
    )
  }
  const submitted: { method: string; data: Record<string, unknown> }[] = []
  page.on('request', (request) => {
    if (
      /\/api\/v1\/datasources(?:\/\d+)?$/.test(new URL(request.url()).pathname) &&
      ['POST', 'PUT'].includes(request.method())
    ) {
      submitted.push({ method: request.method(), data: request.postDataJSON() })
    }
  })
  await page.goto('/datasources')
  const search = page.getByRole('searchbox')
  await search.fill(prefix)
  await search.press('Enter')
  const table = page.locator('main table')
  await expect(table.locator('tbody tr[data-row-key]')).toHaveCount(20)
  await page.getByRole('button', { name: copy.runs.next, exact: true }).click()
  await expect(table.locator('tbody tr[data-row-key]')).toHaveCount(1)
  await page.getByRole('button', { name: copy.runs.previous, exact: true }).click()
  await expect(table.locator('tbody tr[data-row-key]')).toHaveCount(20)
  let searches = 0
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/v1/datasources' && request.method() === 'GET')
      searches++
  })
  await search.fill(prefix + 'Missing')
  expect(searches).toBe(0)
  await search.press('Enter')
  await expect(
    page.getByText(copy.dataAccess.sources.states.noMatch, { exact: true }),
  ).toBeVisible()
  expect(searches).toBe(1)
  await page.getByRole('button', { name: copy.ds.search.reset, exact: true }).click()
  await expect(table.locator('tbody tr[data-row-key]')).toHaveCount(20)
  expect(searches).toBe(2)

  await page
    .getByRole('button', { name: copy.dataAccess.sources.actions.create, exact: true })
    .click()
  const dialog = page.getByRole('dialog')
  const save = dialog.getByRole('button', { name: copy.common.save, exact: true })
  const name = dialog.getByRole('textbox', {
    name: copy.dataAccess.sources.fields.name,
    exact: false,
  })
  await save.click()
  await expect(
    dialog.getByText(copy.dataAccess.sources.validation.name, { exact: true }),
  ).toBeVisible()
  await expect(name).toBeFocused()
  expect(submitted).toHaveLength(0)
  await name.fill(prefix + 'New')
  await dialog
    .getByRole('textbox', { name: copy.dataAccess.sources.fields.database, exact: false })
    .fill(sourcePath)
  page.once('dialog', (prompt) => prompt.dismiss())
  await dialog.getByRole('button', { name: copy.common.close, exact: true }).click()
  await expect(dialog).toBeVisible()
  await expect(name).toHaveValue(prefix + 'New')
  await network.failOnce({ path: '/datasources', method: 'POST' })
  await save.click()
  await expect(dialog.getByRole('alert').filter({ hasText: /错误|失败/ })).toBeVisible()
  await expect(name).toHaveValue(prefix + 'New')
  expect(submitted).toHaveLength(1)
  const hold = await network.hold({ path: '/datasources', method: 'POST' })
  const saved = waitForApi(page, { path: '/datasources', method: 'POST' })
  try {
    await save.click()
    await expect.poll(hold.hits).toBe(1)
    await expect(save).toBeDisabled()
    await page.keyboard.press('Enter')
    expect(hold.hits()).toBe(1)
  } finally {
    hold.release()
  }
  const created = await responseData<components['schemas']['DatasourceOut']>(await saved)
  await expect(dialog).toHaveCount(0)
  expect(submitted).toHaveLength(2)
  await search.fill(prefix + 'New')
  await search.press('Enter')
  const row = table.locator('tbody tr[data-row-key]').filter({ hasText: prefix + 'New' })
  await row.getByRole('button', { name: copy.common.edit, exact: true }).click()
  await expect(
    dialog.getByLabel(copy.dataAccess.sources.fields.credential, { exact: true }),
  ).toHaveValue('')
  await name.fill(prefix + 'Renamed')
  const edited = waitForApi(page, { path: `/datasources/${created.id}`, method: 'PUT' })
  await save.click()
  await responseData(await edited)
  expect(submitted.at(-1)).toEqual({ method: 'PUT', data: { name: prefix + 'Renamed' } })
  await expect(dialog).toHaveCount(0)
  const actual = await getData<{ name: string }>(identity.api, `/datasources/${created.id}`)
  expect(actual.name).toBe(prefix + 'Renamed')
  await page
    .getByRole('button', { name: copy.dataAccess.sources.actions.create, exact: true })
    .click()
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1280, height: 720 },
    { width: 768, height: 1024 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport)
    await expectNoPageOverflow(page)
    const bounds = await dialog.boundingBox()
    expect(bounds!.width).toBeLessThanOrEqual(viewport.width)
    expect(bounds!.height).toBeLessThanOrEqual(viewport.height)
    await capture(
      page,
      info,
      evidence,
      `c2-source-form-${viewport.width}`,
      'empty new source form after verified real create/edit and local paging',
    )
  }
})

test('tasks: validated frozen revision, scheduled date and boolean survive failed creation and retry', async ({
  signedIn: page,
  identity,
  routeCatalog: catalog,
  network,
  evidence,
}, info) => {
  const mapping = await getData<{ name: string }>(identity.api, `/mappings/${catalog.mappingId}`)
  const revision = await getData<{ id: number }>(
    identity.api,
    `/mappings/${catalog.mappingId}/published`,
  )
  const source = await getData<{ name: string }>(
    identity.api,
    `/datasources/${catalog.datasourceId}`,
  )
  const writes: Record<string, unknown>[] = []
  page.on('request', (request) => {
    if (
      new URL(request.url()).pathname === '/api/v1/extraction/tasks' &&
      request.method() === 'POST'
    )
      writes.push(request.postDataJSON())
  })
  await page.goto('/extraction/tasks')
  await page.getByRole('button', { name: copy.tasks.createTitle, exact: true }).click()
  const dialog = page.getByRole('dialog')
  const save = dialog.getByRole('button', { name: copy.tasks.create, exact: true })
  const mappingInput = dialog.getByRole('combobox', { name: copy.tasks.mapping, exact: false })
  // Autofocus opens the first combobox. Dismiss its menu before testing form submission.
  if ((await mappingInput.getAttribute('aria-expanded')) === 'true')
    await page.keyboard.press('Escape')
  await save.click()
  await expect(dialog.getByText(copy.tasks.mappingRequired, { exact: true })).toBeVisible()
  await expect(
    dialog.getByRole('combobox', { name: copy.tasks.mapping, exact: false }),
  ).toBeFocused()
  expect(writes).toHaveLength(0)
  await dialog.getByRole('combobox', { name: copy.tasks.mapping, exact: false }).click()
  await page.getByRole('option', { name: mapping.name, exact: true }).click()
  await dialog.getByRole('combobox', { name: copy.tasks.datasource, exact: false }).click()
  await page.getByRole('option', { name: source.name + ' · sqlite', exact: true }).click()
  const date = dialog.getByLabel(copy.tasks.runAfter, { exact: true })
  await date.fill('2099-01-01T10:30')
  const checkbox = dialog.getByRole('checkbox')
  await checkbox.check()
  await checkbox.uncheck()
  await network.failOnce({ path: '/extraction/tasks', method: 'POST' })
  await save.click()
  await expect(dialog.getByRole('alert').filter({ hasText: /错误|失败/ })).toBeVisible()
  await expect(date).toHaveValue('2099-01-01T10:30')
  await expect(checkbox).not.toBeChecked()
  expect(writes).toHaveLength(1)
  expect(writes[0]).toMatchObject({
    mapping_revision_id: revision.id,
    datasource_id: catalog.datasourceId,
    incremental: false,
  })
  expect(typeof writes[0].run_after).toBe('string')
  expect(Number.isFinite(Date.parse(writes[0].run_after as string))).toBe(true)
  const hold = await network.hold({ path: '/extraction/tasks', method: 'POST' })
  const created = waitForApi(page, { path: '/extraction/tasks', method: 'POST' })
  try {
    await save.click()
    await expect.poll(hold.hits).toBe(1)
    await expect(save).toBeDisabled()
  } finally {
    hold.release()
  }
  const task = await responseData<{ id: number; status: string; run_after: string }>(await created)
  expect(task.status).toBe('PENDING')
  await expect(dialog).toHaveCount(0)
  expect(writes).toHaveLength(2)
  expect(writes[1]).toEqual(writes[0])
  await expect(page.locator(`tr[data-row-key="${task.id}"]`)).toBeVisible()
  await page.getByRole('button', { name: copy.tasks.createTitle, exact: true }).click()
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1280, height: 720 },
    { width: 768, height: 1024 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport)
    await expectNoPageOverflow(page)
    const bounds = await save.boundingBox()
    expect(bounds).not.toBeNull()
    expect(bounds!.x).toBeGreaterThanOrEqual(0)
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(viewport.height)
    const display = await page.evaluate(() => ({
      dpr: window.devicePixelRatio,
      scale: window.visualViewport?.scale,
    }))
    await info.attach(`c2-task-form-${viewport.width}-display`, {
      body: JSON.stringify(display),
      contentType: 'application/json',
    })
    await capture(
      page,
      info,
      evidence,
      `c2-task-form-${viewport.width}`,
      'empty new task drawer with stable footer after verified creation',
    )
  }
})
