import { mkdir, writeFile } from 'node:fs/promises'

import { chromium } from '@playwright/test'

const out = new URL('../../../docs/ui-redesign-2026-11-26/evidence/', import.meta.url)
await mkdir(out, { recursive: true })
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
  locale: 'zh-CN',
})
const page = await context.newPage()
await page.goto('http://127.0.0.1:4156/login')
await page.getByPlaceholder('用户名或邮箱', { exact: true }).fill('e2e_admin')
await page.getByPlaceholder('请输入密码', { exact: true }).fill('E2E-Admin-Password-2026!')
await page.getByRole('button', { name: '登录', exact: true }).click()
await page.waitForURL('http://127.0.0.1:4156/')
await page.evaluate(() => localStorage.setItem('kg-theme-mode', 'light'))
const token = await page.evaluate(
  () =>
    localStorage.getItem('kg-access-token') ||
    JSON.parse(
      localStorage.getItem(`kg-token-pair:${localStorage.getItem('kg-session-generation')}`) ||
        '{}',
    ).access_token,
)
const dataset = {}
for (const path of [
  '/dashboard/stats',
  '/entity-types?page=1&page_size=100',
  '/ontologies',
  '/knowledge-bases?page=1&page_size=20',
]) {
  const r = await context.request.get(`http://127.0.0.1:4156/api/v1${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  dataset[path] = { status: r.status(), body: await r.json() }
}
await writeFile(new URL('current-data.json', out), JSON.stringify(dataset, null, 2))
const observations = []
const routes = [
  ['dashboard', '/'],
  ['assets', '/ontology/entity-types'],
  ['designer', '/ontology/designer?ontology=1'],
  ['graph', '/graph?graph=1'],
  ['mapping', '/extraction?mapping=1'],
  ['runs', '/extraction/runs'],
  ['knowledge', '/knowledge-bases'],
  ['governance', '/governance/rules'],
  ['system', '/system/roles'],
]
for (const [name, path] of routes) {
  await page.goto(`http://127.0.0.1:4156${path}`)
  await page.waitForLoadState('networkidle')
  await page.screenshot({ path: new URL(`before-${name}-1440.png`, out).pathname })
  observations.push({
    name,
    path,
    text: (await page.locator('#main-content').innerText()).slice(0, 13000),
    viewport: { width: 1440, height: 900 },
    dpr: 1,
    zoom: 1,
  })
}
for (const width of [1280, 1920]) {
  await page.setViewportSize({ width, height: width === 1280 ? 800 : 1080 })
  for (const [name, path] of routes.slice(0, 4)) {
    await page.goto(`http://127.0.0.1:4156${path}`)
    await page.waitForLoadState('networkidle')
    await page.screenshot({ path: new URL(`before-${name}-${width}.png`, out).pathname })
  }
}
await writeFile(new URL('current-observations.json', out), JSON.stringify(observations, null, 2))
console.warn(
  JSON.stringify({
    captured: 17,
    pages: observations.map((o) => ({ name: o.name, text: o.text.slice(0, 140) })),
    data: Object.fromEntries(Object.entries(dataset).map(([k, v]) => [k, v.status])),
  }),
)
await browser.close()
