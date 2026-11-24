import type { components } from '../web/src/api/schema'
import {
  capture,
  expect,
  expectNoPageOverflow,
  responseData,
  settleApi,
  test,
  uniqueName,
} from './ui-redesign-fixtures'

const assetLists = [
  '/ontology/entity-types',
  '/ontology/relation-types',
  '/ontology/domains',
  '/ontology/ontologies',
  '/datasources',
  '/extraction',
  '/extraction/runs',
]
const assetCountKeys = [
  'entity_types',
  'relation_types',
  'domains',
  'ontologies',
  'datasources',
  'mappings',
  'runs',
] as const

for (const role of ['ADMIN', 'VIEWER'] as const) {
  test.describe(`${role} dashboard asset navigation`, () => {
    test.use({ role })
    test('all seven asset links open their lists with real and controlled zero counts', async ({
      signedIn: page,
      identity,
      evidence,
      network,
    }) => {
      const name = uniqueName('DashboardUx')
      const fixture = await responseData<components['schemas']['OntologyOut']>(
        await identity.api.post('/api/v1/ontologies', {
          data: {
            name,
            iri: `https://example.org/${name}`,
            label_i18n: { 'zh-CN': name, 'en-US': name },
          } satisfies components['schemas']['OntologyCreate'],
        }),
      )
      try {
        const actual = await responseData<components['schemas']['DashboardStatsOut']>(
          await identity.api.get('/api/v1/dashboard/stats'),
        )
        expect(actual.ontologies).toBeGreaterThan(0)
        const empty: components['schemas']['DashboardStatsOut'] = {
          entity_types: 0,
          relation_types: 0,
          domains: 0,
          ontologies: 0,
          datasources: 0,
          mappings: 0,
          runs: 0,
          current_graph_id: null,
          result_set_count: 0,
          quarantine_count: 0,
          unpublished_count: 0,
        }
        for (const stats of [actual, empty]) {
          // The suite shares populated data; only the zero-count response is controlled.
          if (stats === empty) await network.empty({ path: '/dashboard/stats' }, empty)
          for (let index = 0; index < assetLists.length; index++) {
            await page.goto('/')
            await settleApi(page, evidence)
            const links = page.locator('.asset-grid').getByRole('link')
            await expect(links).toHaveCount(7)
            const link = links.nth(index)
            await expect(link).toHaveAttribute('href', assetLists[index])
            await expect(link.locator('.asset-value')).toHaveText(
              String(stats[assetCountKeys[index]]),
            )
            await page.keyboard.press('Tab')
            await link.focus()
            await expect(link).toBeFocused()
            await expect(link).toHaveCSS('outline-style', 'solid')
            await page.keyboard.press('Enter')
            await expect.poll(() => new URL(page.url()).pathname).toBe(assetLists[index])
            await settleApi(page, evidence)
            await expectNoPageOverflow(page)
          }
        }
      } finally {
        await responseData(await identity.api.delete(`/api/v1/ontologies/${fixture.id}`))
      }
    })
  })
}

test('document evidence uses literal escaped source, accessible focus and retained edits across contexts', async ({
  signedIn: page,
  identity,
  evidence,
  network,
}, info) => {
  type Ontology = components['schemas']['OntologyOut']
  type Suggestion = components['schemas']['AiSuggestionOut']
  const created: number[] = []
  const quote = '<img src=x onerror="alert(1)">原文 😀'
  const source =
    '  Opening\n' +
    Array.from({ length: 60 }, (_, index) => `Paragraph ${index}: example text.`).join('\n') +
    '\n' +
    quote +
    '\nRepeated: ' +
    quote +
    '\n  '
  try {
    for (const suffix of ['A', 'B']) {
      const name = uniqueName('EvidenceUx' + suffix)
      const ontology = await responseData<Ontology>(
        await identity.api.post('/api/v1/ontologies', {
          data: {
            name,
            iri: 'https://example.org/' + name,
            label_i18n: { 'zh-CN': '证据 UX ' + suffix, 'en-US': 'Evidence UX ' + suffix },
          },
        }),
      )
      created.push(ontology.id)
    }
    const candidates: Suggestion[] = [quote, 'invented evidence', '   '].map((evidence, index) => ({
      id: index + 1,
      kind: 'DOCUMENT_FACTS',
      target_id: created[0],
      status: 'PENDING',
      title: 'Evidence candidate ' + index,
      payload: { evidence },
      explanation: '',
      created_at: '2026-11-19T00:00:00Z',
      resolved_at: null,
    }))
    // Controlled candidate payloads exercise invalid legacy/model evidence without calling a model.
    await network.empty({ path: '/ai/documents/extract', method: 'POST' }, candidates)
    await page.goto('/extraction/ai-assist')
    async function chooseOntology(label: string) {
      await page.locator('.source-panel').getByRole('combobox').click()
      await page.getByRole('option').filter({ hasText: label }).click()
    }
    await chooseOntology('证据 UX A')
    const input = page.getByRole('textbox', { name: /^待抽取文本(?: 此项必填)?$/ })
    await input.fill(source)
    await page.getByRole('button', { name: '生成建议', exact: true }).click()
    await expect(page.locator('.suggestion')).toHaveCount(3)
    await expect(page.getByText('未找到原文位置，请人工核对证据。', { exact: true })).toHaveCount(2)
    const locate = page.getByRole('button', { name: '定位原文证据', exact: true })
    await expect(locate).toHaveCount(1)
    await locate.focus()
    await page.keyboard.press('Enter')
    const highlight = page.getByTestId('ai-evidence-highlight')
    const region = page.getByTestId('ai-source-evidence')
    await expect(highlight).toBeFocused()
    expect(await highlight.textContent()).toBe(quote)
    expect(await region.textContent()).toBe(source)
    await expect(region.locator('img')).toHaveCount(0)
    const bounds = await region.boundingBox()
    const matchBounds = await highlight.boundingBox()
    expect(matchBounds!.y).toBeGreaterThanOrEqual(bounds!.y)
    expect(matchBounds!.y + matchBounds!.height).toBeLessThanOrEqual(bounds!.y + bounds!.height)
    expect(await region.evaluate((element) => element.scrollTop)).toBeGreaterThan(0)
    await capture(
      page,
      info,
      evidence,
      'ai-evidence-desktop',
      'Controlled candidate payload; literal source match and keyboard focus',
    )
    await page.keyboard.press('Tab')
    const edit = page.getByRole('button', { name: '返回编辑原文', exact: true })
    await expect(edit).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(input).toBeFocused()
    await expect(input).toHaveValue(source)
    await expect(highlight).toHaveCount(0)
    await input.fill(source + '\nEdited')
    await expect(page.locator('.suggestion')).toHaveCount(0)
    await page.getByRole('button', { name: '生成建议', exact: true }).click()
    await expect(locate).toHaveCount(1)
    await page.setViewportSize({ width: 390, height: 844 })
    await locate.click()
    await expect(highlight).toBeFocused()
    await expectNoPageOverflow(page)
    await capture(
      page,
      info,
      evidence,
      'ai-evidence-mobile',
      '390px: original source retained; exact escaped evidence',
    )
    await chooseOntology('证据 UX B')
    await expect(highlight).toHaveCount(0)
    await expect(page.locator('.suggestion')).toHaveCount(0)
    await expect(input).toHaveValue(source + '\nEdited')
    await settleApi(page, evidence)
    expect(
      evidence.responses.some((entry) =>
        /\/ai\/suggestions\/\d+\/(apply|discard)$/.test(entry.path),
      ),
    ).toBe(false)
  } finally {
    for (const id of created)
      await responseData(await identity.api.delete('/api/v1/ontologies/' + id))
  }
})
