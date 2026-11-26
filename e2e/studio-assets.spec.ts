import {
  capture,
  expect,
  expectNoPageOverflow,
  responseData,
  settleApi,
  test,
  uniqueName,
} from './ui-redesign-fixtures'

test('asset selection uses an adjacent inspector on laptop and a focus-safe sheet on phone @studio @real-api', async ({
  signedIn: page,
  entityCatalog,
  evidence,
}, info) => {
  const { published } = entityCatalog
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/ontology/entity-types?q=' + published.name)
  const row = page.getByRole('row').filter({ hasText: published.name })
  const select = row.getByRole('button', { name: published.label_i18n['zh-CN'], exact: true })
  await select.click()
  const inspector = page.locator('.asset-inspector')
  await expect(inspector).toBeVisible()
  await expect(inspector).toContainText(published.iri)
  const [tableBox, inspectorBox] = await Promise.all([
    page.locator('.asset-catalog .card').boundingBox(),
    inspector.boundingBox(),
  ])
  expect(inspectorBox!.x).toBeGreaterThanOrEqual(tableBox!.x + tableBox!.width)
  await expectNoPageOverflow(page)
  await capture(
    page,
    info,
    evidence,
    'studio-inspector-laptop',
    'real asset in an adjacent inspector',
  )
  await inspector.getByRole('button', { name: '关闭', exact: true }).click()
  await expect(inspector).toHaveCount(0)
  await expect(select).toBeFocused()
  await page.setViewportSize({ width: 375, height: 812 })
  await select.click()
  await expect(page.getByRole('dialog').and(inspector)).toBeVisible()
  await expect(inspector).toContainText(published.iri)
  await expectNoPageOverflow(page)
  await capture(
    page,
    info,
    evidence,
    'studio-inspector-phone',
    'real asset in a narrow-screen sheet',
  )
  await page.keyboard.press('Escape')
  await expect(inspector).toHaveCount(0)
  await expect(select).toBeFocused()
  await expect.poll(() => new URL(page.url()).searchParams.get('preview')).toBeNull()
})

test('relation domain filters retry the failed read and ignore an obsolete domain response @studio @real-api', async ({
  signedIn: page,
  identity,
  routeCatalog: data,
  network,
  evidence,
}) => {
  const name = uniqueName('EmptyStudioDomain')
  const empty = await responseData<{ id: number }>(
    await identity.api.post('/api/v1/domains', {
      data: { name, iri: 'https://example.org/' + name, label_i18n: { 'zh-CN': name } },
    }),
  )
  await page.goto('/ontology/relation-types?q=' + data.relation.name)
  const domains = page.locator('.domain-sidebar')
  const originalDomain = domains.getByRole('button', {
    name: data.domain.label_i18n['zh-CN'],
    exact: true,
  })
  await network.failOnce({ path: `/domains/${data.domain.id}/members` })
  await originalDomain.click()
  const table = page.locator('.search-table')
  await expect(table.getByRole('alert')).toHaveCount(1)
  await expect(page.locator('.ledger-caption')).toContainText('当前 未知 项')
  await expect(page.getByRole('button', { name: '重试', exact: true })).toHaveCount(1)
  await page.getByRole('button', { name: '重试', exact: true }).click()
  const row = page.getByRole('row').filter({ hasText: data.relation.name })
  await expect(row).toBeVisible()
  await expect(page.locator('.ledger-caption')).toContainText('当前 1 项')
  await row.getByRole('button', { name: data.relation.label_i18n['zh-CN'], exact: true }).click()
  await expect(page.locator('.asset-inspector')).toContainText(data.relation.iri)
  const hold = await network.hold({ path: `/domains/${empty.id}/members` })
  try {
    await domains.getByRole('button', { name, exact: true }).click()
    await expect.poll(hold.hits).toBe(1)
    await expect(page.locator('.ledger-caption')).toContainText('当前 未知 项')
    await expect(page.locator('.asset-inspector')).toHaveCount(0)
    await originalDomain.click()
    await expect(row).toBeVisible()
  } finally {
    hold.release()
  }
  await settleApi(page, evidence)
  await expect(row).toBeVisible()
  await expect(originalDomain).toHaveAttribute('aria-pressed', 'true')
})
