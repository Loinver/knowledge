import type { components } from '../web/src/api/schema'
import { capture, expect, getData, settleApi, test } from './ui-redesign-fixtures'

type Schemas = components['schemas']
const kbReturn = '/knowledge-bases/12/search?q=graph%20labels&source=7'

test('detail and evidence show frozen labels, preserve raw fact links and recover catalog failures', async ({
  signedIn: page,
  identity,
  routeCatalog: catalog,
  network,
  evidence,
}, info) => {
  const query = `graph_revision_id=${catalog.graphId}&iri=${encodeURIComponent(catalog.entityIri)}`
  const detail = await getData<Schemas['EntityDetailOut']>(
    identity.api,
    '/extraction/entity-detail?' + query,
  )
  const trace = await getData<Schemas['EntityTraceOut']>(
    identity.api,
    '/extraction/evidence/trace/entity?' + query,
  )
  expect(trace.evidences.length).toBeGreaterThan(0)
  const predicate = catalog.relation.name
  const fact = {
    subject: catalog.entityIri,
    predicate,
    object: catalog.entityIri,
  }
  const item = { ...trace.evidences[0], ...fact }
  // Controlled relation rows on a real extracted result set and real frozen relation catalog.
  await network.empty(
    { path: '/extraction/entity-detail' },
    {
      ...detail,
      out_edges: [
        { id: item.id, graph_revision_id: catalog.graphId, ...fact, object_: fact.object },
      ],
    },
  )
  await network.empty(
    { path: '/extraction/evidence/trace/entity' },
    {
      ...trace,
      evidences: [item],
      total_count: 1,
    },
  )
  await network.empty(
    { path: '/extraction/evidence/trace' },
    {
      graph_revision_id: catalog.graphId,
      fact,
      evidences: [item],
      total_count: 1,
      quarantined_count: 0,
    },
  )
  const detailUrl = `/graph/entities/${encodeURIComponent(catalog.entityIri)}?graph=${catalog.graphId}&kbReturn=${encodeURIComponent(kbReturn)}`
  await page.goto(detailUrl)
  await settleApi(page, evidence)
  await expect(page.getByRole('link', { name: '返回知识库检索', exact: true })).toHaveAttribute(
    'href',
    kbReturn,
  )
  await page.locator('.n-tabs-tab[data-name="out"]').click()
  await expect(page.getByText('UI 验收关系', { exact: true })).toBeVisible()
  await capture(
    page,
    info,
    evidence,
    'detail-frozen-label',
    'detail fact table uses the frozen relation label and raw predicate link',
  )
  const factLink = page.getByRole('link', { name: '追溯证据', exact: true })
  const destination = new URL((await factLink.getAttribute('href'))!, page.url())
  expect(destination.searchParams.get('predicate')).toBe(predicate)
  expect(destination.searchParams.get('graph')).toBe(String(catalog.graphId))
  expect(destination.searchParams.get('kbReturn')).toBe(kbReturn)
  await factLink.click()
  await settleApi(page, evidence)
  await expect(page.getByRole('link', { name: '返回知识库检索', exact: true })).toHaveAttribute(
    'href',
    kbReturn,
  )
  await expect(page.getByText('UI 验收关系', { exact: true })).toBeVisible()
  await expect(page.getByText('UI 验收关系', { exact: true })).toHaveAttribute('title', predicate)
  await page.getByRole('button', { name: '查看链', exact: true }).click()
  await expect(page.locator('.chain-card')).toContainText(predicate)
  await expect(page.locator('.chain-card')).toContainText('UI 验收关系')
  await capture(
    page,
    info,
    evidence,
    'evidence-frozen-label',
    'original evidence row and frozen relation label with raw predicate in the chain',
  )
  await page.getByRole('button', { name: '切换语言', exact: true }).click()
  await expect(page.getByText('UI acceptance relation', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Switch language', exact: true }).click()

  await network.failOnce({ path: '/view-templates/semantic-fields' })
  await page.reload()
  await settleApi(page, evidence)
  await expect(page.getByText(`${predicate} · 未翻译`, { exact: true })).toBeVisible()
  await expect(page.getByText('UI 验收关系', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('alert')).toContainText('KG.INTERNAL_ERROR')
  await capture(
    page,
    info,
    evidence,
    'evidence-label-failure',
    'catalog failure exposes raw predicate and untranslated marker',
  )
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await settleApi(page, evidence)
  await expect(page.getByText('UI 验收关系', { exact: true })).toBeVisible()

  // EvidenceTable renders labels separately and emits the original evidence row.
  await page.goto(detailUrl)
  await settleApi(page, evidence)
  await page.locator('.n-tabs-tab[data-name="evidence"]').click()
  await expect(page.getByText('UI 验收关系', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '查看链', exact: true }).click()
  await expect.poll(() => new URL(page.url()).searchParams.get('predicate')).toBe(predicate)
  await settleApi(page, evidence)
  expect(new URL(page.url()).searchParams.get('iri')).toBeNull()
  expect(new URL(page.url()).searchParams.get('kbReturn')).toBe(kbReturn)
  await page.getByRole('link', { name: '返回对象', exact: true }).click()
  await settleApi(page, evidence)
  expect(new URL(page.url()).searchParams.get('kbReturn')).toBe(kbReturn)
  await expect(page.getByRole('link', { name: '返回知识库检索', exact: true })).toHaveAttribute(
    'href',
    kbReturn,
  )
  await page.goto(
    detailUrl.replace(
      encodeURIComponent(kbReturn),
      encodeURIComponent('https://example.org/knowledge-bases/12/search'),
    ),
  )
  await settleApi(page, evidence)
  await expect(page.getByRole('link', { name: '返回知识库检索', exact: true })).toHaveCount(0)
})

test('unversioned reverse trace links to its returned result set and displays frozen labels', async ({
  signedIn: page,
  routeCatalog: catalog,
  network,
  evidence,
}, info) => {
  await network.empty(
    { path: '/extraction/evidence/trace/reverse' },
    {
      graph_revision_id: catalog.graphId,
      source_id: catalog.datasourceId,
      source_name: 'Isolated source',
      table_name: 'enterprise',
      row_key: '1',
      entities: [catalog.entityIri],
      facts: [
        {
          evidence_id: 1,
          subject: catalog.entityIri,
          predicate: catalog.relation.name,
          object: catalog.entityIri,
        },
      ],
    },
  )
  await page.goto(`/graph/evidence?kbReturn=${encodeURIComponent(kbReturn)}`)
  await expect(page.getByRole('link', { name: '返回知识库检索', exact: true })).toHaveAttribute(
    'href',
    kbReturn,
  )
  await page.getByText('按来源行反查', { exact: true }).click()
  await page.getByLabel('数据源 ID', { exact: true }).fill(String(catalog.datasourceId))
  await page.getByLabel('来源表', { exact: true }).fill('enterprise')
  await page.getByLabel('来源行键', { exact: true }).fill('1')
  await page.getByRole('button', { name: '追溯证据', exact: true }).click()
  await settleApi(page, evidence)
  await expect(page.locator('.reverse-facts')).toContainText('UI 验收关系')
  expect(new URL(page.url()).searchParams.get('graph')).toBeNull()
  const link = page.locator('.reverse-entities a')
  const destination = new URL((await link.getAttribute('href'))!, page.url())
  expect(destination.searchParams.get('graph')).toBe(String(catalog.graphId))
  expect(destination.searchParams.get('kbReturn')).toBe(kbReturn)
  await capture(
    page,
    info,
    evidence,
    'reverse-pinned-link',
    'unversioned query with a returned graph pin and real frozen catalog',
  )
  await link.click()
  await settleApi(page, evidence)
  await expect(page.locator('p.iri')).toHaveText(catalog.entityIri)
  expect(new URL(page.url()).searchParams.get('graph')).toBe(String(catalog.graphId))
  expect(new URL(page.url()).searchParams.get('kbReturn')).toBe(kbReturn)
})
