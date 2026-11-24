import { expect, getData, responseData, test, uniqueName, waitForApi } from './ui-redesign-fixtures'

for (const kind of ['enum-dictionaries', 'templates'] as const) {
  test(`${kind}: real remote pages, loading, recovery and submitted search stay consistent`, async ({
    signedIn: page,
    identity,
    network,
  }) => {
    const path = `/governance/${kind}`
    const prefix = uniqueName('SearchCollection')
    for (let index = 0; index < 21; index++) {
      const name = prefix + String(index).padStart(2, '0')
      await responseData(
        await identity.api.post('/api/v1' + path, {
          data: {
            name,
            label_i18n: { 'zh-CN': name, 'en-US': name },
            ...(kind === 'templates'
              ? { source: 'Isolated search verification', basis: 'UI regression', resources: [] }
              : {
                  definition_i18n: { 'zh-CN': '隔离搜索验证', 'en-US': 'UI regression' },
                  entries: [{ value: 'ACTIVE', label_i18n: { 'zh-CN': '有效' } }],
                }),
          },
        }),
      )
    }
    const collection = await getData<{ total: number }>(identity.api, path + '?q=' + prefix)
    expect(collection.total).toBe(21)
    const hold = await network.hold({ path })
    try {
      await page.goto(path + '?q=' + prefix + '&page=2')
      await expect.poll(hold.hits).toBe(1)
      await expect(page.getByRole('status').filter({ hasText: '加载' }).first()).toBeVisible()
      await expect(page.locator('main')).not.toContainText('当前 0 项')
    } finally {
      hold.release()
    }
    const table = page.locator('main table')
    await expect(table.locator('tbody tr')).toHaveCount(1)
    await expect(table).toContainText(prefix + '20')
    await expect(page.locator('.ui-pagination')).toHaveCount(1)
    await expect(page.locator('.ui-pagination')).toContainText('当前 21 项')
    const previous = waitForApi(page, { path, query: { page: '1', q: prefix } })
    await page.getByRole('button', { name: '上一页', exact: true }).click()
    await responseData(await previous)
    await expect(table.locator('tbody tr')).toHaveCount(20)

    await network.failOnce({ path })
    await page.getByRole('button', { name: '搜索', exact: true }).click()
    await expect(
      page
        .getByRole('alert')
        .filter({ hasText: /错误|失败/ })
        .first(),
    ).toBeVisible()
    await expect(page.getByText('暂无数据', { exact: true })).toHaveCount(0)
    const recovered = waitForApi(page, { path, query: { q: prefix } })
    await page.getByRole('button', { name: '重试', exact: true }).click()
    await responseData(await recovered)
    await expect(table.locator('tbody tr')).toHaveCount(20)

    let searches = 0
    page.on('request', (request) => {
      if (new URL(request.url()).pathname === '/api/v1' + path && request.method() === 'GET')
        searches++
    })
    const input = page.getByRole('searchbox')
    await input.fill(prefix + 'Missing')
    expect(searches).toBe(0)
    const noMatch = waitForApi(page, { path, query: { q: prefix + 'Missing', page: '1' } })
    await input.press('Enter')
    await responseData(await noMatch)
    await expect(page.getByText('没有符合当前筛选的对象', { exact: true })).toBeVisible()
    expect(searches).toBe(1)
    const reset = waitForApi(page, { path, query: { page: '1' } })
    await page.getByRole('button', { name: '重置条件', exact: true }).click()
    await responseData(await reset)
    await expect(input).toHaveValue('')
    await expect(page).not.toHaveURL(/[?&](q|page)=/)
    await expect(table.locator('tbody tr')).toHaveCount(20)
    expect(searches).toBe(2)
  })
}
