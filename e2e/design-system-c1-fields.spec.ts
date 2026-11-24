import type { Locator } from '@playwright/test'

import { expect, getData, responseData, test, uniqueName } from './ui-redesign-fixtures'

const field = (container: Locator, label: string) =>
  container
    .locator('.ui-field')
    .filter({ has: container.page().locator('.ui-field-label', { hasText: label }) })
    .last()

test('template metadata fields block invalid writes and retain the draft after a failed save', async ({
  signedIn: page,
  network,
  identity,
}) => {
  await page.goto('/governance/templates')
  await page.getByRole('button', { name: '新建模板', exact: true }).click()
  const editor = page.getByRole('dialog')
  const name = field(editor, '机读名').getByRole('textbox')
  let writes = 0
  page.on('request', (request) => {
    if (
      new URL(request.url()).pathname === '/api/v1/governance/templates' &&
      request.method() === 'POST'
    )
      writes++
  })
  const save = editor.getByRole('button', { name: '保存', exact: true })
  await save.click()
  await expect(name).toBeFocused()
  await expect(name).toHaveAttribute('aria-invalid', 'true')
  expect(writes).toBe(0)
  await name.fill('N'.repeat(129))
  await field(editor, '来源').getByRole('textbox').fill('UI verification')
  await field(editor, '中文标签').getByRole('textbox').fill('模板字段验证')
  await field(editor, '依据与说明').getByRole('textbox').fill('Isolated browser check')
  await save.click()
  await expect(name).toHaveAttribute('aria-invalid', 'true')
  expect(writes).toBe(0)
  const validName = uniqueName('FieldTemplate')
  await name.fill(validName)
  await name.press('Tab')
  await expect(name).not.toHaveAttribute('aria-invalid', 'true')
  await network.failOnce(
    { path: '/governance/templates', method: 'POST' },
    503,
    'KG.INTERNAL_ERROR',
  )
  await save.click()
  await expect(editor.getByRole('alert').first()).toBeVisible()
  await expect(name).toHaveValue(validName)
  expect(writes).toBe(1)
  const savedResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === '/api/v1/governance/templates' &&
      response.request().method() === 'POST' &&
      response.ok(),
  )
  await save.click()
  const saved = await responseData<{ id: number; revision: number }>(await savedResponse)
  await expect(editor).toBeVisible()
  await expect(editor.getByText('模板已保存。', { exact: true })).toBeVisible()
  await expect(editor.getByRole('button', { name: '删除', exact: true })).toBeEnabled()
  await expect(name).toHaveValue(validName)
  const persisted = await getData<{ name: string; revision: number; resources: unknown[] }>(
    identity.api,
    `/governance/templates/${saved.id}`,
  )
  expect(persisted).toMatchObject({ name: validName, revision: saved.revision, resources: [] })
  expect(writes).toBe(2)
})

test('template instantiation keeps its pinned template while validating metadata before a single write', async ({
  signedIn: page,
  identity,
}) => {
  const templateName = uniqueName('InstanceFieldTemplate')
  const template = await responseData<{ id: number; revision: number }>(
    await identity.api.post('/api/v1/governance/templates', {
      data: {
        name: templateName,
        label_i18n: { 'zh-CN': templateName },
        source: 'UI verification',
        basis: 'Isolated browser check',
        resources: [],
      },
    }),
  )
  await page.goto('/governance/templates?q=' + templateName)
  await page
    .getByRole('row')
    .filter({ hasText: templateName })
    .getByRole('button', { name: '预览模板', exact: true })
    .click()
  const editor = page.getByRole('dialog')
  await editor.getByRole('button', { name: '继续填写新本体', exact: true }).click()
  const name = field(editor, '机读名').getByRole('textbox')
  const iri = field(editor, 'IRI').getByRole('textbox')
  let writes = 0
  let match: string | undefined
  page.on('request', (request) => {
    if (
      new URL(request.url()).pathname ===
        `/api/v1/governance/templates/${template.id}/instantiate` &&
      request.method() === 'POST'
    ) {
      writes++
      match = request.headers()['if-match']
    }
  })
  const save = editor.getByRole('button', { name: '按模板创建本体', exact: true })
  await save.click()
  await expect(name).toBeFocused()
  expect(writes).toBe(0)
  const nameValue = uniqueName('InstantiatedOntology')
  await name.fill(nameValue)
  await iri.fill('https://example.org/' + 'x'.repeat(641))
  await field(editor, '中文标签').getByRole('textbox').fill('实例化字段验证')
  await save.click()
  await expect(iri).toHaveAttribute('aria-invalid', 'true')
  expect(writes).toBe(0)
  await iri.fill('https://example.org/' + nameValue)
  await save.click()
  await expect(editor).toHaveCount(0)
  expect(writes).toBe(1)
  expect(match).toBe(String(template.revision))
})

test('relation create validates both endpoint pairs and clears sibling errors after either correction', async ({
  signedIn: page,
  entityCatalog,
}) => {
  await page.goto('/ontology/relation-types?view=table')
  await page.locator('.page-header .actions').getByRole('button').click()
  const editor = page.getByRole('dialog')
  await field(editor, '机读名').getByRole('textbox').fill(uniqueName('PairRelation'))
  await field(editor, '中文标签').getByRole('textbox').fill('端点联动校验')
  await field(editor, '命名空间').getByRole('combobox').click()
  await page.getByRole('option', { name: new RegExp(entityCatalog.namespace.prefix) }).click()
  for (const side of ['domain', 'range']) {
    await editor.locator(`[data-endpoint="${side}"]`).getByRole('combobox').click()
    await page.getByRole('option', { name: 'UI 验收已发布类型', exact: true }).click()
  }
  let writes = 0
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/v1/relations' && request.method() === 'POST')
      writes++
  })
  const bounds = editor.getByRole('spinbutton')
  for (const offset of [0, 2]) {
    const min = bounds.nth(offset)
    const max = bounds.nth(offset + 1)
    await min.fill('3')
    await max.fill('2')
    await editor.getByRole('button', { name: '保存', exact: true }).click()
    await expect(min).toHaveAttribute('aria-invalid', 'true')
    await expect(max).toHaveAttribute('aria-invalid', 'true')
    await expect(min).toBeFocused()
    expect(writes).toBe(0)
    await (offset === 0 ? min : max).fill(offset === 0 ? '1' : '4')
    await (offset === 0 ? min : max).press('Tab')
    await expect(min).not.toHaveAttribute('aria-invalid', 'true')
    await expect(max).not.toHaveAttribute('aria-invalid', 'true')
  }
  await editor.getByRole('button', { name: '保存', exact: true }).click()
  await expect(editor).toHaveCount(0)
  expect(writes).toBe(1)
})

test('dictionary dynamic fields focus invalid input, clear duplicates after row removal and retain failed drafts', async ({
  signedIn: page,
  network,
}) => {
  await page.goto('/governance/enum-dictionaries')
  await page.locator('.page-header .actions').getByRole('button').click()
  const editor = page.getByRole('dialog')
  const name = field(editor, '机读名').getByRole('textbox')
  let writes = 0
  page.on('request', (request) => {
    if (
      new URL(request.url()).pathname === '/api/v1/governance/enum-dictionaries' &&
      request.method() === 'POST'
    )
      writes++
  })
  await editor.getByRole('button', { name: '保存', exact: true }).click()
  await expect(name).toBeFocused()
  await expect(name).toHaveAttribute('aria-invalid', 'true')
  expect(writes).toBe(0)
  await name.fill(uniqueName('FieldsDictionary'))
  await editor.locator('fieldset').nth(0).getByRole('textbox').nth(1).fill('动态字典')
  await editor.locator('fieldset').nth(1).getByRole('textbox').first().fill('动态条目验证')
  const rows = editor.locator('.entry-row')
  await rows.nth(0).getByRole('textbox').nth(0).fill('OTHER')
  await rows.nth(0).getByRole('textbox').nth(1).fill('第一项')
  await editor.getByRole('button', { name: '添加枚举值', exact: true }).click()
  await rows.nth(1).getByRole('textbox').nth(0).fill('SAME')
  await rows.nth(1).getByRole('textbox').nth(1).fill('第二项')
  await editor.getByRole('button', { name: '添加枚举值', exact: true }).click()
  await rows.nth(2).getByRole('textbox').nth(0).fill('SAME')
  await rows.nth(2).getByRole('textbox').nth(1).fill('第三项')
  await editor.getByRole('button', { name: '保存', exact: true }).click()
  for (const index of [1, 2])
    await expect(rows.nth(index).getByRole('textbox').nth(0)).toHaveAttribute(
      'aria-invalid',
      'true',
    )
  expect(writes).toBe(0)
  await rows.nth(0).getByRole('button').click()
  await expect(rows).toHaveCount(2)
  for (const index of [0, 1])
    await expect(rows.nth(index).getByRole('textbox').nth(0)).toHaveAttribute(
      'aria-invalid',
      'true',
    )
  await expect(rows.nth(0).getByRole('textbox').nth(0)).toBeFocused()
  await rows.nth(1).getByRole('button').click()
  await expect(rows).toHaveCount(1)
  await expect(rows.nth(0).getByRole('textbox').nth(0)).not.toHaveAttribute('aria-invalid', 'true')
  await expect(editor.locator('[aria-invalid="true"]')).toHaveCount(0)
  await network.failOnce(
    { path: '/governance/enum-dictionaries', method: 'POST' },
    503,
    'KG.INTERNAL_ERROR',
  )
  await editor.getByRole('button', { name: '保存', exact: true }).click()
  await expect(editor.getByRole('alert').first()).toBeVisible()
  await expect(rows.nth(0).getByRole('textbox').nth(0)).toHaveValue('SAME')
  expect(writes).toBe(1)
})

test('entity property validates cardinalities and exact decimal bounds before writing its original string values', async ({
  signedIn: page,
  entityCatalog,
  identity,
}) => {
  const entity = await responseData<{ id: number }>(
    await identity.api.post('/api/v1/entity-types', {
      data: {
        name: uniqueName('PropertyFields'),
        namespace_id: entityCatalog.namespace.id,
        label_i18n: { 'zh-CN': '属性校验实体', 'en-US': 'Property validation entity' },
      },
    }),
  )
  await page.goto(`/ontology/entity-types/${entity.id}`)
  await page.getByRole('tab', { name: '数据属性', exact: true }).click()
  await page.getByRole('button', { name: '添加属性', exact: true }).click()
  const editor = page.getByRole('dialog')
  let writes = 0
  page.on('request', (request) => {
    if (
      new URL(request.url()).pathname.includes(`/entity-types/${entity.id}`) &&
      ['POST', 'PUT', 'PATCH'].includes(request.method())
    )
      writes++
  })
  const name = field(editor, '机读名').getByRole('textbox')
  await editor.getByRole('button', { name: '保存', exact: true }).click()
  await expect(name).toHaveAttribute('aria-invalid', 'true')
  await expect(name).toBeFocused()
  await name.fill('MeasuredValue')
  await field(editor, '中文标签').getByRole('textbox').fill('测量值')
  await field(editor, '数据类型').getByRole('combobox').click()
  await page.getByRole('option', { name: '小数', exact: true }).click()
  const minCount = field(editor, '最小基数').getByRole('textbox')
  const maxCount = field(editor, '最大基数').getByRole('textbox')
  const minValue = field(editor, '最小值').getByRole('textbox')
  const maxValue = field(editor, '最大值').getByRole('textbox')
  await minCount.fill('3')
  await maxCount.fill('2')
  await minValue.fill('9007199254740993.000000000000000001')
  await maxValue.fill('9007199254740993.000000000000000000')
  await editor.getByRole('button', { name: '保存', exact: true }).click()
  await expect(maxCount).toHaveAttribute('aria-invalid', 'true')
  await expect(maxValue).toHaveAttribute('aria-invalid', 'true')
  expect(writes).toBe(0)
  await minCount.fill('0')
  await minValue.fill('9007199254740992.999999999999999999')
  await minValue.press('Tab')
  await expect(maxCount).not.toHaveAttribute('aria-invalid', 'true')
  await expect(maxValue).not.toHaveAttribute('aria-invalid', 'true')
  await editor.getByRole('button', { name: '保存', exact: true }).click()
  await expect(editor).toHaveCount(0)
  expect(writes).toBe(1)
  const saved = await getData<{
    data_props: {
      name: string
      min_cardinality: number
      max_cardinality: number
      min_value: string
      max_value: string
    }[]
  }>(identity.api, `/entity-types/${entity.id}`)
  expect(saved.data_props.find((prop) => prop.name === 'MeasuredValue')).toMatchObject({
    min_cardinality: 0,
    max_cardinality: 2,
    min_value: '9007199254740992.999999999999999999',
    max_value: '9007199254740993.000000000000000000',
  })
})

test('existing URI property rejects malformed defaults and preserves a relative Unicode reference', async ({
  signedIn: page,
  entityCatalog,
  identity,
}) => {
  const entity = await responseData<{ id: number }>(
    await identity.api.post('/api/v1/entity-types', {
      data: {
        name: uniqueName('UriPropertyFields'),
        namespace_id: entityCatalog.namespace.id,
        label_i18n: { 'zh-CN': 'URI属性校验' },
        data_props: [
          {
            name: 'Link',
            label_i18n: { 'zh-CN': '资源链接' },
            datatype: 'anyURI',
            nullable: true,
            default_value: '../original',
          },
        ],
      },
    }),
  )
  await page.goto(`/ontology/entity-types/${entity.id}`)
  await page.getByRole('tab', { name: '数据属性', exact: true }).click()
  await page
    .getByRole('row')
    .filter({ hasText: 'Link' })
    .getByRole('button', { name: '编辑', exact: true })
    .click()
  const editor = page.getByRole('dialog')
  const value = field(editor, '默认值').getByRole('textbox')
  let writes = 0
  page.on('request', (request) => {
    if (
      new URL(request.url()).pathname === `/api/v1/entity-types/${entity.id}` &&
      request.method() === 'PUT'
    )
      writes++
  })
  for (const invalid of ['bad%escape', 'bad value', 'https://[invalid']) {
    await value.fill(invalid)
    await editor.getByRole('button', { name: '保存', exact: true }).click()
    await expect(value).toHaveAttribute('aria-invalid', 'true')
    await expect(value).toBeFocused()
    expect(writes).toBe(0)
  }
  const relative = '../资料/条目%20一'
  await value.fill(relative)
  await value.press('Tab')
  await expect(value).not.toHaveAttribute('aria-invalid', 'true')
  await editor.getByRole('button', { name: '保存', exact: true }).click()
  await expect(editor).toHaveCount(0)
  expect(writes).toBe(1)
  const saved = await getData<{
    data_props: { name: string; datatype: string; default_value: string }[]
  }>(identity.api, `/entity-types/${entity.id}`)
  expect(saved.data_props.find((prop) => prop.name === 'Link')).toMatchObject({
    datatype: 'anyURI',
    default_value: relative,
  })
})
