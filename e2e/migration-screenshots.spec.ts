import { createHash } from 'node:crypto'
import { mkdir, readdir, readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'

import type { Page, TestInfo } from '@playwright/test'

import { expect, responseData, test, uniqueName } from './ui-redesign-fixtures'

async function shot(page: Page, name: string, info: TestInfo): Promise<void> {
  await expect(page.locator('[aria-busy="true"]:visible')).toHaveCount(0)
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({
    path: info.outputPath(`${name}.png`),
    animations: 'disabled',
    fullPage: false,
  })
}

async function writeScreenshotManifest(outDir: string) {
  const files = (await readdir(outDir)).filter((name) => name.endsWith('.png')).sort()
  const entries = []
  for (const name of files) {
    const digest = createHash('sha256')
      .update(await readFile(join(outDir, name)))
      .digest('hex')
    entries.push(`${digest}  ${name}`)
  }
  await writeFile(join(outDir, 'SHA256SUMS'), `${entries.join('\n')}\n`)
}

test.use({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' })

const testWithBase = test.extend<object, { screenshotBase: { id: number; documentId: string } }>({
  screenshotBase: [
    async ({ identity }, use) => {
      const base = await responseData<{ id: number }>(
        await identity.api.post('/api/v1/knowledge-bases', {
          data: { name: uniqueName('VisualEvidence'), description: 'Formal visual evidence' },
        }),
      )
      const document = await responseData<{ id: string }>(
        await identity.api.post(`/api/v1/knowledge-bases/${base.id}/documents`, {
          params: { filename: 'visual-evidence.txt', content_type: 'text/plain' },
          headers: { 'Content-Type': 'application/octet-stream' },
          data: Buffer.from('Screenshot evidence for the formal knowledge platform.'),
        }),
      )
      await expect
        .poll(async () => {
          const state = await responseData<{ searchable: boolean }>(
            await identity.api.get(`/api/v1/knowledge-bases/${base.id}/documents/${document.id}`),
          )
          return state.searchable
        })
        .toBe(true)
      await use({ ...base, documentId: document.id })
    },
    { scope: 'worker' },
  ],
})

testWithBase(
  'formal design evidence across page families and viewports @visual @real-api',
  async ({ signedIn: page, routeCatalog: data, screenshotBase: base }, info) => {
    await mkdir(info.outputDir, { recursive: true })
    const families = [
      { name: 'dashboard-dark-1440', path: '/', theme: 'dark' },
      { name: 'dashboard-light-1440', path: '/', theme: 'light' },
      {
        name: 'semantic-ledger-dark-1440',
        path: '/ontology/entity-types',
        theme: 'dark',
      },
      {
        name: 'entity-detail-light-1440',
        path: `/ontology/entity-types/${data.published.id}`,
        theme: 'light',
      },
      {
        name: 'configuration-three-level-dark-1440',
        path: '/governance/enum-dictionaries',
        theme: 'dark',
      },
      {
        name: 'ontology-designer-dark-1440',
        path: `/ontology/designer?ontology=${data.ontology.id}`,
        theme: 'dark',
      },
      {
        name: 'graph-browse-light-1440',
        path: `/graph?graph=${data.graphId}`,
        theme: 'light',
      },
      {
        name: 'evidence-trace-dark-1440',
        path: '/graph/evidence',
        theme: 'dark',
      },
      {
        name: 'mapping-workbench-dark-1440',
        path: `/extraction?mapping=${data.mappingId}`,
        theme: 'dark',
      },
      {
        name: 'validation-report-light-1440',
        path: '/graph/reports',
        theme: 'light',
      },
      {
        name: 'knowledge-detail-dark-1440',
        path: `/knowledge-bases/${base.id}?doc=${base.documentId}`,
        theme: 'dark',
      },
      { name: 'system-roles-light-1440', path: '/system/roles', theme: 'light' },
    ] as const

    for (const family of families) {
      await page.evaluate((theme) => localStorage.setItem('kg-theme-mode', theme), family.theme)
      await page.goto(family.path)
      await expect(page.locator('h1').first()).toBeVisible()
      await shot(page, family.name, info)
    }

    for (const width of [1024, 768, 375]) {
      await page.setViewportSize({ width, height: width === 375 ? 812 : 900 })
      await page.evaluate(() => localStorage.setItem('kg-theme-mode', 'dark'))
      for (const pagePath of [
        { name: 'semantic', path: '/ontology/namespaces' },
        { name: 'graph', path: `/graph?graph=${data.graphId}` },
        { name: 'knowledge', path: `/knowledge-bases/${base.id}/search` },
      ]) {
        await page.goto(pagePath.path)
        await expect(page.locator('h1').first()).toBeVisible()
        await shot(page, `${pagePath.name}-dark-${width}`, info)
      }
    }
    await writeScreenshotManifest(info.outputDir)
  },
)
