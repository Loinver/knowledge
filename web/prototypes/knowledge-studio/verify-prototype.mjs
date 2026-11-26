import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'

import { chromium } from '@playwright/test'

const base = process.env.KG_PROTO_URL || 'http://127.0.0.1:4156/prototypes/knowledge-studio/'
const out = new URL('../../../docs/ui-redesign-2026-11-26/evidence/', import.meta.url)
await mkdir(out, { recursive: true })
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
  locale: 'zh-CN',
})
const page = await context.newPage()
const errors = [],
  network = []
page.on('pageerror', (e) => errors.push(e.message))
page.on('request', (r) => {
  if (r.url().includes('/api/')) network.push(r.url())
})
const manifest = [],
  checks = []
async function shot(name) {
  assert.equal(
    await page.locator('vite-error-overlay').count(),
    0,
    'No compiler overlay in visual evidence',
  )
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({ path: new URL(`${name}.png`, out).pathname })
  manifest.push({
    name,
    url: page.url(),
    viewport: page.viewportSize(),
    dpr: 1,
    zoom: 1,
    ...(await page.evaluate(() => ({
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
      canvas: (() => {
        const r = document.querySelector('.canvas-area')?.getBoundingClientRect()
        return r ? { width: r.width, height: r.height } : null
      })(),
    }))),
  })
}
async function goto(view, data = 'dense', direction = 'a') {
  await page.goto(`${base}?page=${view}&data=${data}&direction=${direction}`)
  await page.waitForSelector('.workspace-header')
  await page.waitForLoadState('networkidle')
}
for (const width of [1440, 1280, 1920]) {
  await page.setViewportSize({ width, height: width === 1440 ? 900 : width === 1280 ? 800 : 1080 })
  for (const view of ['dashboard', 'assets', 'designer']) {
    await goto(view)
    if (view === 'designer')
      await page.getByRole('button', { name: '查看 员工', exact: true }).click()
    await shot(`after-${view}-${width}`)
    if (view === 'assets') {
      await page.getByRole('button', { name: '查看 员工', exact: true }).first().click()
      await shot(`after-asset-detail-${width}`)
    }
  }
}
for (const width of [1440, 1280, 1920]) {
  await page.setViewportSize({ width, height: width === 1440 ? 900 : width === 1280 ? 800 : 1080 })
  for (const view of ['dashboard', 'assets', 'designer']) {
    await goto(view, 'reference')
    await shot(`paired-${view}-${width}`)
  }
}
await page.setViewportSize({ width: 1440, height: 900 })
for (const view of ['dashboard', 'assets']) {
  await goto(view, 'dense', 'b')
  await shot(`direction-b-${view}-1440`)
}
for (const view of ['mapping', 'runs', 'knowledge', 'governance', 'system']) {
  await goto(view)
  await shot(`after-${view}-1440`)
}
await goto('assets')
const search = page.getByRole('textbox', { name: '搜索名称、机读名或 IRI' })
await search.fill('供应商')
assert.equal(await page.locator('.asset-table tbody tr').count(), 1)
checks.push('asset text search')
await page
  .getByRole('button', { name: '查看 供应商资质审查与年度复核记录', exact: true })
  .first()
  .click()
await shot('after-long-name-1440')
await page.getByRole('tab', { name: '校验', exact: true }).click()
assert.match(await page.locator('.validation-state').innerText(), /未执行/)
checks.push('publication and validation states remain separate')
await page.getByRole('button', { name: '编辑草稿', exact: true }).click()
await page.getByLabel('显示名称').fill('供应商资质复核（原型）')
await page.getByRole('button', { name: '保存至本次原型', exact: true }).click()
assert.match(await page.locator('.asset-inspector').innerText(), /供应商资质复核/)
checks.push('local draft edit')
await search.fill('不存在的名称')
assert.equal(await page.locator('.empty-state').count(), 1)
checks.push('filtered empty state')
await page.getByRole('button', { name: '重置条件', exact: true }).click()
await page.getByRole('button', { name: '新建类型', exact: true }).click()
await page.getByRole('button', { name: '保存至本次原型', exact: true }).click()
assert.equal(await page.locator('.form-error').count(), 1)
await page.keyboard.press('Escape')
assert.equal(await page.locator('dialog[open]').count(), 0)
checks.push('required validation and Escape dismissal')
await page.keyboard.press('Meta+k')
assert.equal(await page.locator('dialog[open]').count(), 1)
await page.getByRole('textbox', { name: '输入页面名称' }).fill('本体')
await page.getByRole('button', { name: '本体建模', exact: true }).last().click()
assert.match(page.url(), /page=designer/)
checks.push('keyboard page navigation')
const node = page.getByRole('button', { name: '查看 组织部门', exact: true })
await node.focus()
await page.keyboard.press('Enter')
assert.match(await page.locator('.graph-inspector').innerText(), /组织部门/)
checks.push('keyboard canvas selection')
await page.getByRole('button', { name: '放大', exact: true }).click()
assert.match(await page.locator('.canvas-controls').innerText(), /110%/)
const panBefore = await page.locator('.graph-svg>g').getAttribute('style')
await page.locator('.graph-svg').hover()
await page.mouse.wheel(0, 90)
await page.waitForTimeout(100)
const panAfter = await page.locator('.graph-svg>g').getAttribute('style')
assert.notEqual(panBefore, panAfter)
assert.match(await page.locator('.canvas-controls').innerText(), /110%/)
checks.push('wheel pans without zooming')
await page.getByRole('button', { name: '专注模式', exact: true }).click()
assert.equal(await page.locator('.focus-mode').count(), 1)
await shot('after-designer-focus-1440')
await page.getByRole('button', { name: '退出专注', exact: true }).click()
checks.push('focus workspace toggle')
for (const state of ['loading', 'empty', 'error']) {
  await goto('assets')
  await page.getByRole('combobox', { name: '状态演示' }).selectOption(state)
  await shot(`state-${state}-1440`)
  if (state === 'error') {
    await page.getByRole('button', { name: '重试', exact: true }).click()
    assert.equal(await page.locator('.asset-table').count(), 1)
    checks.push('error retry restores content')
  }
}
await goto('mapping')
await page.locator('.mapping-table select').first().selectOption('小写')
await page.getByRole('button', { name: '预览字段结果' }).click()
assert.equal(await page.locator('dialog[open]').count(), 1)
checks.push('mapping input and preview')
const reviewUrl = new URL('./review.html', base).href
await page.goto(reviewUrl)
await page.waitForLoadState('networkidle')
await page.locator('#directions').scrollIntoViewIfNeeded()
const brokenImages = await page
  .locator('main img')
  .evaluateAll((imgs) => imgs.filter((i) => !i.complete || i.naturalWidth === 0).map((i) => i.src))
assert.deepEqual(brokenImages, [])
await page.getByRole('combobox', { name: '选择对比视口' }).selectOption('1920')
await page.getByRole('combobox', { name: '选择对比页面' }).selectOption('designer')
await page.locator('#after').evaluate((img) => img.decode())
assert.match(await page.locator('#after').getAttribute('src'), /paired-designer-1920/)
await page.locator('#directions').scrollIntoViewIfNeeded()
await page.screenshot({ path: new URL('review-directions-1440.png', out).pathname })
await page.locator('main img').first().click()
assert.equal(await page.locator('dialog[open]').count(), 1)
await page.keyboard.press('Escape')
assert.equal(await page.locator('dialog[open]').count(), 0)
checks.push('review gallery images, paired viewport switch, keyboard lightbox')
assert.deepEqual(errors, [])
assert.deepEqual(network, [])
checks.push('no browser runtime errors; no business API requests')
await writeFile(
  new URL('prototype-verification.json', out),
  JSON.stringify({ checks, errors, network, manifest }, null, 2),
)
console.warn(
  JSON.stringify(
    {
      checks,
      screenshots: manifest.length,
      overflow: manifest.filter((m) => m.documentWidth > m.viewport.width),
    },
    null,
    2,
  ),
)
await browser.close()
