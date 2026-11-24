import { randomUUID } from 'node:crypto'

import type { components } from '../web/src/api/schema'
import { expect, getData, responseData, settleApi, test } from './ui-redesign-fixtures'

type Relation = components['schemas']['RelationTypeOut']

test('relation cardinality corrections clear both field errors before a single valid write', async ({
  signedIn: page,
  identity,
  entityCatalog,
}) => {
  const name = `Cardinality${randomUUID().replaceAll('-', '').slice(0, 10)}`
  const original = await responseData<Relation>(
    await identity.api.post('/api/v1/relations', {
      data: {
        name,
        namespace_id: entityCatalog.namespace.id,
        label_i18n: { 'zh-CN': '基数校验关系', 'en-US': 'Cardinality validation relation' },
        domain_spec: { type_id: entityCatalog.published.id },
        range_spec: { type_id: entityCatalog.published.id },
      },
    }),
  )
  await page.goto(`/ontology/relation-types?q=${name}&view=table`)
  await page
    .getByRole('row')
    .filter({ hasText: name })
    .getByRole('button', { name: '编辑', exact: true })
    .click()
  const drawer = page.locator('.ui-sheet:visible')
  const minimum = drawer.getByRole('spinbutton').nth(0)
  const maximum = drawer.getByRole('spinbutton').nth(1)
  await expect(minimum).toHaveValue('0')
  let writes = 0
  page.on('request', (request) => {
    if (
      new URL(request.url()).pathname === `/api/v1/relations/${original.id}` &&
      request.method() === 'PUT'
    )
      writes++
  })
  await minimum.fill('3')
  await maximum.fill('2')
  await drawer.getByRole('button', { name: '保存', exact: true }).click()
  await expect(minimum).toHaveAttribute('aria-invalid', 'true')
  await expect(maximum).toHaveAttribute('aria-invalid', 'true')
  expect(writes).toBe(0)
  await maximum.fill('4')
  await maximum.press('Tab')
  await expect(maximum).not.toHaveAttribute('aria-invalid', 'true')
  await expect(minimum).not.toHaveAttribute('aria-invalid', 'true')
  await drawer.getByRole('button', { name: '保存', exact: true }).click()
  await expect(drawer).toHaveCount(0)
  expect(writes).toBe(1)
  const saved = await getData<Relation>(identity.api, `/relations/${original.id}`)
  expect(saved.domain_spec.cardinality).toEqual(expect.objectContaining({ min: 3, max: 4 }))
})

test('closing a saving relation editor completes the submitted rename on the original resource', async ({
  signedIn: page,
  identity,
  entityCatalog,
  evidence,
  network,
}) => {
  const name = `PdcaRename${randomUUID().replaceAll('-', '').slice(0, 10)}`
  const original = await responseData<Relation>(
    await identity.api.post('/api/v1/relations', {
      data: {
        name,
        namespace_id: entityCatalog.namespace.id,
        label_i18n: { 'zh-CN': 'PDCA完整保存', 'en-US': 'PDCA complete save' },
        domain_spec: { type_id: entityCatalog.published.id },
        range_spec: { type_id: entityCatalog.published.id },
      },
    }),
  )
  await page.goto(`/ontology/relation-types?q=${name}&view=table`)
  await settleApi(page, evidence)
  await page
    .locator('tr')
    .filter({ hasText: name })
    .getByRole('button', { name: '编辑', exact: true })
    .click()
  const drawer = page.locator('.ui-sheet:visible')
  const nameInput = drawer.locator('.ui-field').filter({ hasText: '机读名' }).locator('input')
  await expect(nameInput).toHaveValue(name)
  const submittedName = name + 'Renamed'
  await nameInput.fill(submittedName)
  await drawer
    .locator('.ui-field')
    .filter({ hasText: '中文标签' })
    .locator('input')
    .fill('PDCA已完整保存')
  const pendingWrite = await network.hold({ path: `/relations/${original.id}`, method: 'PUT' })
  try {
    await drawer.getByRole('button', { name: '保存', exact: true }).click()
    await expect.poll(pendingWrite.hits).toBe(1)
    let confirmedClose = false
    page.once('dialog', async (dialog) => {
      expect(dialog.type()).toBe('confirm')
      confirmedClose = true
      await dialog.accept()
    })
    await drawer.locator('.ui-overlay-close').click()
    expect(confirmedClose).toBe(true)
    await expect(drawer).toBeHidden()
    const renamed = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === `/api/v1/relations/${original.id}/rename` &&
        response.request().method() === 'PATCH',
    )
    pendingWrite.release()
    expect((await renamed).ok()).toBe(true)
    await settleApi(page, evidence)
    const saved = await getData<Relation>(identity.api, `/relations/${original.id}`)
    expect(saved.name).toBe(submittedName)
    expect(saved.label_i18n['zh-CN']).toBe('PDCA已完整保存')
    await expect(drawer).toBeHidden()
  } finally {
    pendingWrite.release()
  }
})

test('late relation edit reads preserve the selected draft and save only its resource', async ({
  signedIn: page,
  identity,
  entityCatalog,
  evidence,
  network,
}) => {
  const suffix = randomUUID().replaceAll('-', '').slice(0, 10)
  const namePrefix = `PdcaRelation${suffix}`
  const createRelation = async (suffix: string) =>
    responseData<Relation>(
      await identity.api.post('/api/v1/relations', {
        data: {
          name: namePrefix + suffix,
          namespace_id: entityCatalog.namespace.id,
          label_i18n: { 'zh-CN': `PDCA关系${suffix}`, 'en-US': `PDCA relation ${suffix}` },
          domain_spec: { type_id: entityCatalog.published.id },
          range_spec: { type_id: entityCatalog.published.id },
        },
      }),
    )
  const first = await createRelation('A')
  const second = await createRelation('B')
  await page.goto(`/ontology/relation-types?q=${namePrefix}&view=table`)
  await settleApi(page, evidence)
  const row = (name: string) => page.locator('tr').filter({ hasText: name })
  await expect(row(first.name)).toBeVisible()
  await expect(row(second.name)).toBeVisible()

  // Delay an actual edit request after the page's initial detail reads have settled.
  const oldRead = await network.hold({ path: `/relations/${first.id}`, method: 'GET' })
  try {
    await row(first.name).getByRole('button', { name: '编辑', exact: true }).click()
    await expect.poll(oldRead.hits).toBe(1)
    const drawer = page.locator('.ui-sheet:visible')
    // A pending editor can be closed before a new table selection is made.
    if (await drawer.isVisible()) {
      await drawer.getByRole('button', { name: '取消', exact: true }).click()
      await expect(drawer).toBeHidden()
    }
    await row(second.name).getByRole('button', { name: '编辑', exact: true }).click()
    const label = drawer.locator('.ui-field').filter({ hasText: '中文标签' }).locator('input')
    await expect(label).toHaveValue('PDCA关系B')
    await label.fill('PDCA关系B已修改')
    oldRead.release()
    await settleApi(page, evidence)
    await expect(label).toHaveValue('PDCA关系B已修改')

    const writes: number[] = []
    page.on('request', (request) => {
      const match = new URL(request.url()).pathname.match(/^\/api\/v1\/relations\/(\d+)$/)
      if (match && request.method() === 'PUT') writes.push(Number(match[1]))
    })
    await drawer.getByRole('button', { name: '保存', exact: true }).click()
    await expect(drawer).toBeHidden()
    await settleApi(page, evidence)
    expect(writes).toEqual([second.id])
    const savedFirst = await getData<Relation>(identity.api, `/relations/${first.id}`)
    const savedSecond = await getData<Relation>(identity.api, `/relations/${second.id}`)
    expect(savedFirst.label_i18n).toEqual(first.label_i18n)
    expect(savedFirst.edit_revision).toBe(first.edit_revision)
    expect(savedSecond.label_i18n['zh-CN']).toBe('PDCA关系B已修改')
    expect(savedSecond.edit_revision).toBeGreaterThan(second.edit_revision)
  } finally {
    oldRead.release()
  }
})
