import {
  expect,
  test,
  uniqueName,
  responseData,
  expectNoPageOverflow,
} from './ui-redesign-fixtures'

test.use({ viewport: { width: 1440, height: 900 } })

test('entity form validates fields, preserves numeric identity and blocks duplicate writes @design-system', async ({
  signedIn: page,
  entityCatalog,
  network,
}) => {
  await page.goto('/ontology/entity-types')
  await page.locator('.page-header .actions button').click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  const form = dialog.locator('form')
  const inputs = form.getByRole('textbox')
  let writes = 0
  let payload: Record<string, unknown> | undefined
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/v1/entity-types' && request.method() === 'POST') {
      writes++
      payload = request.postDataJSON() as Record<string, unknown>
    }
  })
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog.getByRole('alert').first()).toBeVisible()
  expect(writes).toBe(0)
  await expect(inputs.first()).toBeFocused()
  const namespace = form.getByRole('combobox')
  await expect(namespace).toHaveAttribute('aria-invalid', 'true')
  await inputs.nth(0).fill(uniqueName('PilotEntity'))
  await inputs.nth(1).fill('设计系统试点实体')
  await inputs.nth(2).fill('Design system pilot entity')
  await namespace.click()
  await page.getByRole('option', { name: new RegExp(entityCatalog.namespace.prefix) }).click()
  await expect(namespace).not.toHaveAttribute('aria-invalid', 'true')
  const held = await network.hold({ path: '/entity-types', method: 'POST' })
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect.poll(held.hits).toBe(1)
  await expect(dialog.getByRole('button', { name: '保存', exact: true })).toBeDisabled()
  await page.keyboard.press('Escape')
  await expect(dialog).toBeVisible()
  expect(writes).toBe(1)
  expect(typeof payload?.namespace_id).toBe('number')
  expect(payload?.namespace_id).toBe(entityCatalog.namespace.id)
  held.release()
  await expect(dialog).toHaveCount(0)
  await expect(page.getByRole('button', { name: '设计系统试点实体', exact: true })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  await expectNoPageOverflow(page)
  const table = page.getByRole('table')
  const action = table.getByRole('button', { name: '查看', exact: true }).first()
  await expect(action).toBeVisible()
  const geometry = await action.evaluate((element) => {
    const rect = element.getBoundingClientRect()
    return { left: rect.left, right: rect.right, width: innerWidth }
  })
  expect(geometry.left).toBeGreaterThanOrEqual(0)
  expect(geometry.right).toBeLessThanOrEqual(geometry.width)
})

test('knowledge form keeps failed drafts, rejects discard and restores trigger focus @design-system', async ({
  signedIn: page,
  network,
}) => {
  await page.goto('/knowledge-bases')
  const trigger = page.locator('.page-header .actions button')
  await trigger.click()
  const dialog = page.getByRole('dialog')
  const name = dialog.getByRole('textbox').first()
  const draft = uniqueName('RetainedKnowledge')
  await name.fill(draft)
  await network.failOnce({ path: '/knowledge-bases', method: 'POST' }, 503, 'KG.INTERNAL_ERROR')
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog.getByRole('alert').first()).toBeVisible()
  await expect(name).toHaveValue(draft)
  page.once('dialog', (confirmation) => confirmation.dismiss())
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  await expect(dialog).toBeVisible()
  await expect(name).toHaveValue(draft)
  page.once('dialog', (confirmation) => confirmation.accept())
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await expect(trigger).toBeFocused()
})

test('knowledge table uses actual remote totals and resets server pagination after sorting @design-system', async ({
  signedIn: page,
  identity,
}) => {
  const prefix = uniqueName('RemotePage')
  for (let index = 0; index < 25; index++) {
    await responseData(
      await identity.api.post('/api/v1/knowledge-bases', {
        data: { name: prefix + '-' + String(index).padStart(2, '0') },
      }),
    )
  }
  await page.goto('/knowledge-bases?q=' + prefix)
  await page.getByRole('button', { name: '表格视图', exact: true }).click()
  await expect(page.getByRole('table').getByRole('row')).toHaveCount(21)
  const response = page.waitForResponse((res) => {
    const url = new URL(res.url())
    return url.pathname === '/api/v1/knowledge-bases' && url.searchParams.get('page') === '2'
  })
  await page.getByRole('button', { name: '下一页', exact: true }).click()
  const pageTwo = await responseData<{ items: unknown[]; total: number; page: number }>(
    await response,
  )
  expect(pageTwo.total).toBe(25)
  expect(pageTwo.items).toHaveLength(5)
  expect(pageTwo.page).toBe(2)
  await expect(page.getByRole('table').getByRole('row')).toHaveCount(6)
  const sortResponse = page.waitForResponse((res) => {
    const url = new URL(res.url())
    return url.pathname === '/api/v1/knowledge-bases' && url.searchParams.get('sort') === 'name'
  })
  await page.getByRole('combobox').last().click()
  await page.getByRole('option').filter({ hasText: '名称' }).click()
  const sorted = await responseData<{
    items: Array<{ name: string }>
    total: number
    page: number
  }>(await sortResponse)
  expect(sorted.total).toBe(25)
  expect(sorted.page).toBe(1)
  expect(sorted.items[0].name).toBe(prefix + '-00')
  await expect(page.getByRole('link', { name: prefix + '-00', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '重置条件', exact: true }).click()
  await expect(page).not.toHaveURL(/q=RemotePage/)
  await expect(page).not.toHaveURL(/page=2/)
  await expectNoPageOverflow(page)
})

test('nested namespace dialog keeps the parent draft and restores focus in both themes @design-system', async ({
  signedIn: page,
}, testInfo) => {
  for (const theme of ['dark', 'light']) {
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
      await page.evaluate((mode) => localStorage.setItem('kg-theme-mode', mode), theme)
      await page.goto('/ontology/entity-types')
      await page.locator('.page-header .actions button').click()
      const parent = page.locator('#entity-create-form')
      const name = uniqueName('ParentDraft')
      await parent.getByRole('textbox').first().fill(name)
      const trigger = parent.getByRole('button', { name: '登记', exact: true })
      await trigger.click()
      const child = page.locator('.ui-dialog')
      await expect(child).toBeVisible()
      const input = child.getByRole('textbox').first()
      await input.fill(uniqueName('ns').toLowerCase())
      expect(
        await input.evaluate((element) => {
          const box = element.getBoundingClientRect()
          return (
            document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2) === element
          )
        }),
      ).toBe(true)
      await page.keyboard.press('Tab')
      await expect(child.getByRole('textbox').nth(1)).toBeFocused()
      await expectNoPageOverflow(page)
      await page.screenshot({ path: testInfo.outputPath('nested-' + theme + '-' + width + '.png') })
      page.once('dialog', (confirmation) => confirmation.accept())
      await child.getByRole('button', { name: '取消', exact: true }).click()
      await expect(child).toHaveCount(0)
      await expect(trigger).toBeFocused()
      await expect(parent.getByRole('textbox').first()).toHaveValue(name)
      page.once('dialog', (confirmation) => confirmation.accept())
      await page.getByRole('dialog').getByRole('button', { name: '取消', exact: true }).click()
      await expect(page.getByRole('dialog')).toHaveCount(0)
    }
  }
})

test.describe('viewer boundary', () => {
  test.use({ role: 'VIEWER' })
  test('viewer reads migrated tables and cannot open write forms @design-system', async ({
    signedIn: page,
  }) => {
    for (const path of ['/ontology/entity-types', '/knowledge-bases']) {
      await page.goto(path)
      await expect(page.locator('.page-header .actions button')).toBeDisabled()
      await expect(page.getByRole('dialog')).toHaveCount(0)
    }
    await expect(page.getByRole('button', { name: '系统管理', exact: true })).toHaveCount(0)
  })
})
