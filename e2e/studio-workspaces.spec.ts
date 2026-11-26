import { capture, expect, expectNoPageOverflow, settleApi, test } from './ui-redesign-fixtures'

for (const kind of ['designer', 'graph'] as const) {
  test(`${kind} focus mode contains keyboard focus and restores its trigger @studio @real-api`, async ({
    signedIn: page,
    routeCatalog: data,
    evidence,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.goto(
      kind === 'designer'
        ? `/ontology/designer?ontology=${data.ontology.id}`
        : `/graph?graph=${data.graphId}`,
    )
    await settleApi(page, evidence)
    const workspace = page.locator(kind === 'designer' ? '.designer' : '.graph-page')
    const trigger = workspace.getByRole('button', { name: '焦点模式', exact: true })
    await trigger.click()
    await expect(workspace).toHaveClass(/focus-mode/)
    for (const key of ['Tab', 'Shift+Tab']) {
      for (let index = 0; index < 35; index++) {
        await page.keyboard.press(key)
        expect(
          await workspace.evaluate((element) => element.contains(document.activeElement)),
        ).toBe(true)
      }
    }
    if (kind === 'graph') {
      await workspace.getByRole('button', { name: '历史图谱版本', exact: true }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect
        .poll(() => dialog.evaluate((element) => element.contains(document.activeElement)))
        .toBe(true)
      await page.keyboard.press('Escape')
      await expect(dialog).toHaveCount(0)
      await expect(workspace).toHaveClass(/focus-mode/)
    }
    await page.keyboard.press('Escape')
    await expect(workspace).not.toHaveClass(/focus-mode/)
    await expect(trigger).toBeFocused()
    await expectNoPageOverflow(page)
    await page.setViewportSize({ width: 375, height: 812 })
    await page.locator('#nav-toggle').click()
    const navigation = page.locator('.app-sider')
    await expect
      .poll(() => navigation.evaluate((element) => element.contains(document.activeElement)))
      .toBe(true)
    for (let index = 0; index < 20; index++) {
      await page.keyboard.press('Tab')
      expect(await navigation.evaluate((element) => element.contains(document.activeElement))).toBe(
        true,
      )
    }
    await page.keyboard.press('Escape')
    await expect(page.locator('#nav-toggle')).toBeFocused()
  })
}

test('catalog samples remain unobstructed below the tree at laptop width @studio @real-api', async ({
  signedIn: page,
  routeCatalog: data,
  evidence,
}, info) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto(`/datasources/catalog?datasourceId=${data.datasourceId}`)
  await page
    .locator('.catalog-tree .table-row')
    .filter({ has: page.getByText('enterprise', { exact: true }) })
    .click()
  const samples = page.locator('.catalog-samples')
  await samples.getByRole('button', { name: '预览', exact: true }).click()
  await expect(samples.getByRole('row')).toHaveCount(6)
  await samples.scrollIntoViewIfNeeded()
  await settleApi(page, evidence)
  const [tree, result] = await Promise.all([
    page.locator('.catalog-tree').boundingBox(),
    samples.boundingBox(),
  ])
  expect(tree!.y + tree!.height).toBeLessThanOrEqual(result!.y)
  const cell = samples.getByRole('cell').first()
  await cell.scrollIntoViewIfNeeded()
  expect(
    await cell.evaluate((element) => {
      const box = element.getBoundingClientRect()
      return element.contains(
        document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2),
      )
    }),
  ).toBe(true)
  await capture(
    page,
    info,
    evidence,
    'studio-catalog-samples-laptop',
    'real API five-row preview with no tree overlap',
  )
})
