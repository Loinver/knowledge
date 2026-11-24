import { mkdir, readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import { expect, test } from '@playwright/test'

import { ensureAdmin, loginAsAdmin } from '../../../../../e2e/admin.ts'
async function capture(page, name) {
  const directory = process.env.KG_OPERATIONS_SCREENSHOT_DIR
  if (!directory) return page.screenshot({ fullPage: true })
  await mkdir(directory, { recursive: true })
  return page.screenshot({ fullPage: true, path: resolve(directory, `${name}.png`) })
}
test.beforeEach(async ({ page }) => {
  const overlayPath = process.env.KG_OPERATIONS_LOCALE_OVERLAY
  if (!overlayPath) return
  const overlay = JSON.parse(await readFile(overlayPath, 'utf8'))
  await page.route(/\/src\/locales\/(zh-CN|en-US)\.json(?:\?.*)?$/, async (route) => {
    const locale = new URL(route.request().url()).pathname.includes('zh-CN') ? 'zh-CN' : 'en-US'
    const base = JSON.parse(await readFile(resolve(`web/src/locales/${locale}.json`), 'utf8'))
    await route.fulfill({
      contentType: 'text/javascript',
      body: `export default ${JSON.stringify({ ...base, ...overlay[locale] })}`,
    })
  })
})
async function expectFits(page) {
  await expect
    .poll(() =>
      page.evaluate(() => ({
        width: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth,
      })),
    )
    .toMatchObject({ width: (await page.viewportSize()).width })
  const size = await page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }))
  expect(size.scroll).toBeLessThanOrEqual(size.width + 1)
}
async function expectDrawerFits(page) {
  const drawer = page.getByRole('dialog').and(page.locator('.ui-sheet'))
  await expect
    .poll(async () => {
      const box = await drawer.boundingBox()
      const viewport = page.viewportSize()
      return Boolean(box && box.x >= -1 && box.x + box.width <= viewport.width + 1)
    })
    .toBe(true)
}
test('authentication purposes and recovery controls fit 375px in both themes', async ({
  page,
}, info) => {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.setViewportSize({ width: 375, height: 812 })
  for (const mode of ['dark', 'light']) {
    await page.addInitScript((theme) => localStorage.setItem('kg-theme-mode', theme), mode)
    for (const path of [
      '/login',
      '/register',
      '/forgot-password',
      '/reset-password',
      '/missing-workspace',
    ]) {
      await page.goto(path)
      await expect(page.locator('h1')).toBeVisible()
      await expectFits(page)
      await info.attach(`${mode}-${path.slice(1)}-375`, {
        body: await capture(page, `${mode}-${path.slice(1)}-375`),
        contentType: 'image/png',
      })
    }
  }
  await page.goto('/login')
  await page.getByRole('button', { name: '\u767B\u5F55', exact: true }).click()
  await expect(
    page.getByText('\u8BF7\u8F93\u5165\u8D26\u53F7\u6216\u90AE\u7BB1', { exact: true }),
  ).toBeVisible()
  await expect(page).toHaveURL(/\/login$/)
  expect(errors).toEqual([])
})
test('real aggregate and administration views preserve their business controls across viewports', async ({
  page,
}, info) => {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  await ensureAdmin(page)
  await loginAsAdmin(page)
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 960 })
    for (const path of [
      '/',
      '/account/profile',
      '/account/security',
      '/system/users',
      '/system/roles',
      '/system/audit-logs',
      '/system/ai-models',
      '/forbidden',
    ]) {
      await page.goto(path)
      await expect(page.locator('h1').last()).toBeVisible()
      if (path === '/') {
        await expect(page.locator('.asset')).toHaveCount(7)
        await expect(page.locator('.pipe-step')).toHaveCount(6)
        await expect(page.locator('.readout .metric')).toHaveCount(2)
      }
      await expectFits(page)
      await info.attach(`${path.replaceAll('/', '-') || 'dashboard'}-${width}`, {
        body: await capture(page, `${path.replaceAll('/', '-') || 'dashboard'}-${width}`),
        contentType: 'image/png',
      })
    }
    await page.goto('/system/ai-models')
    await page
      .getByRole('button', { name: '\u65B0\u5EFA\u6A21\u578B\u914D\u7F6E', exact: true })
      .click()
    await expect(
      page.getByRole('dialog').and(page.locator('.ui-sheet')).locator('fieldset'),
    ).toHaveCount(3)
    await expect(page.getByLabel('API \u5BC6\u94A5', { exact: true })).toHaveValue('')
    await expectFits(page)
    await expectDrawerFits(page)
    await page
      .getByRole('dialog')
      .and(page.locator('.ui-sheet'))
      .getByRole('button', { name: '\u53D6\u6D88', exact: true })
      .click()
  }
  expect(errors).toEqual([])
})
test('English light identity, settings and model inspector remain usable on mobile', async ({
  page,
}) => {
  await ensureAdmin(page)
  await loginAsAdmin(page)
  await page.addInitScript(() => {
    localStorage.setItem('kg-locale', 'en-US')
    localStorage.setItem('kg-theme-mode', 'light')
  })
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 960 })
    for (const path of ['/', '/account/profile', '/system/ai-models']) {
      await page.goto(path)
      await expect(page.locator('h1').last()).toBeVisible()
      await expectFits(page)
      await capture(page, `en-light-${path.replaceAll('/', '-') || 'dashboard'}-${width}`)
    }
    await page.getByRole('button', { name: 'New model configuration', exact: true }).click()
    await expect(
      page.getByRole('dialog').and(page.locator('.ui-sheet')).locator('fieldset'),
    ).toHaveCount(3)
    await expectFits(page)
    await expectDrawerFits(page)
    await capture(page, `en-light-model-inspector-${width}`)
    await page
      .getByRole('dialog')
      .and(page.locator('.ui-sheet'))
      .getByRole('button', { name: 'Cancel', exact: true })
      .click()
  }
})
