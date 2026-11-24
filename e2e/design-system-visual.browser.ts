// Paired visual evidence runs only under design-system-visual.config.ts.
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'

import { expect, test as plainTest } from '@playwright/test'
import type { Page } from '@playwright/test'

import { ADMIN, loginAsAdmin } from './admin'
import { responseData, test, uniqueName } from './ui-redesign-fixtures'

const phase = process.env.KG_DESIGN_PHASE ?? 'before'
const root = process.env.KG_DESIGN_EVIDENCE_DIR
if (!root || !['before', 'after'].includes(phase)) {
  throw new Error('Set KG_DESIGN_EVIDENCE_DIR and KG_DESIGN_PHASE=before|after')
}
const scenarioFile = join(process.env.KG_E2E_TEMP_DIR!, 'design-system-scenario.json')
type Family = { name: string; path: string; theme: string; width: number; height: number }
type Scenario = { families: Family[]; dataset: Record<string, unknown>; sha256: string }

async function capture(page: Page, scenario: Scenario) {
  const observations = []
  const output = join(root!, phase)
  await mkdir(output, { recursive: true })
  for (const family of scenario.families) {
    await page.setViewportSize({ width: family.width, height: family.height })
    await page.evaluate((theme) => localStorage.setItem('kg-theme-mode', theme), family.theme)
    await page.goto(family.path)
    await expect(page.locator('h1').first()).toBeVisible()
    await page.waitForLoadState('networkidle')
    await page.evaluate(() => document.fonts.ready)
    const runtime = await page.evaluate(() => {
      const box = (selector: string) => {
        const rect = document.querySelector(selector)?.getBoundingClientRect()
        return rect ? { x: rect.x, y: rect.y, width: rect.width, height: rect.height } : null
      }
      return {
        viewport: { width: innerWidth, height: innerHeight },
        dpr: devicePixelRatio,
        visualScale: visualViewport?.scale ?? 1,
        cssZoom: getComputedStyle(document.documentElement).zoom,
        theme: document.documentElement.dataset.theme ?? 'light',
        locale: document.documentElement.lang,
        header: box('.app-header'),
        brand: box('.brand'),
        documentWidth: document.documentElement.scrollWidth,
      }
    })
    const path = join(output, family.name + '.png')
    await page.screenshot({ path, animations: 'disabled', fullPage: false })
    observations.push({ ...family, ...runtime, url: family.path, path })
  }
  await writeFile(
    join(output, 'manifest.json'),
    JSON.stringify(
      {
        phase,
        datasetSha256: scenario.sha256,
        observations,
      },
      null,
      2,
    ) + '\n',
  )
}

if (phase === 'before') {
  test('capture the unchanged real UI with a replayable isolated dataset', async ({
    signedIn: page,
    routeCatalog: data,
    identity,
  }) => {
    const base = await responseData<{ id: number }>(
      await identity.api.post('/api/v1/knowledge-bases', {
        data: {
          name: uniqueName('DesignSystem'),
          description: 'Shared design system visual evidence',
        },
      }),
    )
    const families: Family[] = []
    const paths = [
      { name: 'dashboard', path: '/' },
      { name: 'entity-types', path: '/ontology/entity-types' },
      { name: 'knowledge-bases', path: '/knowledge-bases' },
      { name: 'designer', path: `/ontology/designer?ontology=${data.ontology.id}` },
      { name: 'graph', path: `/graph?graph=${data.graphId}` },
      { name: 'mapping', path: `/extraction?mapping=${data.mappingId}` },
    ]
    for (const viewport of [
      { width: 1440, height: 900 },
      { width: 1280, height: 720 },
      { width: 768, height: 1024 },
      { width: 390, height: 844 },
    ]) {
      for (const theme of ['dark', 'light']) {
        for (const entry of paths)
          families.push({
            ...entry,
            ...viewport,
            theme,
            name: `${entry.name}-${theme}-${viewport.width}`,
          })
      }
    }
    const dataset: Record<string, unknown> = { data, base }
    for (const path of [
      '/dashboard/stats',
      '/entity-types?page=1&page_size=20',
      '/knowledge-bases?page=1&page_size=20',
    ]) {
      dataset[path] = await responseData(await identity.api.get('/api/v1' + path))
    }
    const sha256 = createHash('sha256').update(JSON.stringify(dataset)).digest('hex')
    const scenario = { families, dataset, sha256 }
    await writeFile(scenarioFile, JSON.stringify(scenario, null, 2) + '\n')
    await mkdir(root!, { recursive: true })
    await writeFile(join(root!, 'scenario.json'), JSON.stringify(scenario, null, 2) + '\n')
    await capture(page, scenario)
  })
} else {
  plainTest(
    'capture the migrated real UI against the exact same isolated dataset',
    async ({ page }) => {
      const scenario = JSON.parse(await readFile(scenarioFile, 'utf8')) as Scenario
      await loginAsAdmin(page)
      const tokens = await responseData<{ access_token: string }>(
        await page.request.post('/api/v1/auth/login', { data: ADMIN }),
      )
      for (const [path, expected] of Object.entries(scenario.dataset)) {
        if (!path.startsWith('/')) continue
        const actual = await responseData(
          await page.request.get('/api/v1' + path, {
            headers: { Authorization: `Bearer ${tokens.access_token}` },
          }),
        )
        expect(actual, `Same API dataset for ${path}`).toEqual(expected)
      }
      await capture(page, scenario)
    },
  )
}
