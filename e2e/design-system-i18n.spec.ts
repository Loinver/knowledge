import { expect, responseData, test } from './ui-redesign-fixtures'

const chineseOntology = '本体显示标签'
const chineseEntity = '实体显示标签'
const chineseRelation = '关系显示标签'

test('mapping label changes preserve ontology and machine-name selections in the open draft', async ({
  signedIn: page,
  routeCatalog: data,
  evidence,
}, info) => {
  await page.route('**/api/v1/ontologies**', async (route) => {
    if (route.request().method() !== 'GET') return route.continue()
    const response = await route.fetch()
    const body = await response.json()
    const items = Array.isArray(body.data) ? body.data : [body.data]
    for (const item of items) {
      if (item?.id === data.ontology.id && 'label_i18n' in item)
        item.label_i18n = { 'zh-CN': chineseOntology, 'en-US': ' ' }
    }
    await route.fulfill({ response, json: body })
  })
  for (const [path, id, chinese] of [
    ['entity-types', data.published.id, chineseEntity],
    ['relations', data.relation.id, chineseRelation],
  ] as const) {
    await page.route(`**/api/v1/${path}/${id}`, async (route) => {
      const response = await route.fetch()
      const body = await response.json()
      body.data.label_i18n = { 'zh-CN': chinese, 'en-US': ' ' }
      await route.fulfill({ response, json: body })
    })
  }
  const writes: string[] = []
  page.on('request', (request) => {
    if (request.method() !== 'GET' && request.url().includes('/api/v1/mappings'))
      writes.push(request.url())
  })
  await page.goto('/extraction')
  await page.getByRole('button', { name: '新建映射', exact: true }).click()
  await page.getByRole('button', { name: '切换语言', exact: true }).click()
  const name = page.getByRole('textbox', { name: /^Mapping name/ })
  await name.fill('Preserved untranslated draft')
  const ontology = page.getByRole('combobox', { name: /^Choose ontology/ })
  await ontology.click()
  await page
    .getByRole('option', {
      name: `${data.ontology.name} (Not translated) · ${data.ontology.name}`,
      exact: true,
    })
    .click()
  await expect(ontology).toHaveValue(
    `${data.ontology.name} (Not translated) · ${data.ontology.name}`,
  )
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  const source = page.getByRole('combobox', { name: /^Data source/ })
  await source.click()
  const sourceOption = page
    .getByRole('option')
    .filter({ hasText: /UiSource/ })
    .first()
  await sourceOption.click()
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await page.getByRole('button', { name: 'Add entity mapping', exact: true }).click()
  await page.getByRole('button', { name: 'Add relation mapping', exact: true }).click()
  const entity = page.getByTestId('entity-mapping').getByRole('combobox').first()
  const relation = page.locator('.relation-editor').getByRole('combobox').first()
  await expect(entity).toHaveValue(`${data.published.name} (Not translated)`)
  await expect(relation).toHaveValue(`${data.relation.name} (Not translated)`)
  await page.getByRole('button', { name: 'Switch language', exact: true }).click()
  await expect(entity).toHaveValue(chineseEntity)
  await expect(relation).toHaveValue(chineseRelation)
  await expect(page.locator('[data-testid="entity-mapping"]')).toContainText(data.published.name)
  await expect(page.locator('.relation-editor')).toContainText(data.relation.name)
  expect(writes).toEqual([])
  expect(evidence.pageErrors).toEqual([])
  await info.attach('locale-and-identity', {
    body: JSON.stringify({
      route: page.url(),
      ontologyId: data.ontology.id,
      entity: data.published.name,
      relation: data.relation.name,
      writes,
    }),
    contentType: 'application/json',
  })
})

test('export label changes keep the selected ontology and frozen revision in the same form', async ({
  signedIn: page,
  routeCatalog: data,
}) => {
  await page.route('**/api/v1/ontologies?*', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    for (const item of body.data)
      if (item.id === data.ontology.id) item.label_i18n = { 'zh-CN': chineseOntology, 'en-US': ' ' }
    await route.fulfill({ response, json: body })
  })
  await page.goto(`/governance/export?ontology=${data.ontology.id}&revision=1`)
  await page.getByRole('button', { name: '切换语言', exact: true }).click()
  const ontology = page.locator('.exchange-controls').getByRole('combobox').first()
  await expect(ontology).toHaveValue(`Not translated · ${data.ontology.name}`)
  const revision = page.locator('.exchange-controls').getByRole('spinbutton')
  await expect(revision).toHaveValue('1')
  await page.getByRole('button', { name: 'Switch language', exact: true }).click()
  await expect(ontology).toHaveValue(`${chineseOntology} · ${data.ontology.name}`)
  await expect(revision).toHaveValue('1')
  await expect(page).toHaveURL(new RegExp(`ontology=${data.ontology.id}&revision=1`))
})

test('a real newly created domain leaves optional English absent and marks it on language switch', async ({
  signedIn: page,
  identity,
}) => {
  await page.goto('/ontology/domains')
  await page.getByRole('button', { name: '创建', exact: true }).click()
  const drawer = page.getByRole('dialog').and(page.locator('.ui-sheet'))
  const name = `UntranslatedDomain${Date.now()}`
  await drawer.getByRole('textbox', { name: /^机读名/ }).fill(name)
  await drawer.getByRole('textbox', { name: /^IRI/ }).fill(`urn:example:${name}`)
  await drawer.getByRole('textbox', { name: /^中文标签/ }).fill('领域未翻译验证')
  const response = page.waitForResponse(
    (res) => res.request().method() === 'POST' && res.url().endsWith('/api/v1/domains'),
  )
  await drawer.getByRole('button', { name: '保存', exact: true }).click()
  const result = await responseData<{ id: number }>(await response)
  const saved = await responseData<{ label_i18n: Record<string, string> }>(
    await identity.api.get(`/api/v1/domains/${result.id}`),
  )
  expect(saved.label_i18n).toEqual({ 'zh-CN': '领域未翻译验证' })
  await expect(drawer).toBeHidden()
  const node = page.getByRole('treeitem').filter({ hasText: '领域未翻译验证' })
  await expect(node).toBeVisible()
  await node.click()
  await page.locator('.detail-actions').getByRole('button', { name: '编辑', exact: true }).click()
  const editor = page.getByRole('dialog').and(page.locator('.ui-sheet'))
  await editor.getByRole('textbox', { name: '英文标签', exact: true }).fill('   ')
  const updated = page.waitForResponse(
    (res) => res.request().method() === 'PUT' && res.url().endsWith(`/api/v1/domains/${result.id}`),
  )
  await editor.getByRole('button', { name: '保存', exact: true }).click()
  const accepted = await updated
  expect(accepted.ok()).toBe(true)
  expect(accepted.request().postDataJSON().label_i18n).toEqual({ 'zh-CN': '领域未翻译验证' })
  await expect(editor).toBeHidden()
  await page.getByRole('button', { name: '切换语言', exact: true }).click()
  await expect(
    page.getByRole('treeitem').filter({ hasText: `${name} (Not translated)` }),
  ).toBeVisible()
})
