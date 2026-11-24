import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import type { components } from '../web/src/api/schema'
import {
  expect,
  expectNoPageOverflow,
  getData,
  responseData,
  test,
  uniqueName,
  waitForApi,
} from './ui-redesign-fixtures'

const copy = JSON.parse(readFileSync(resolve('web/src/locales/zh-CN.json'), 'utf8'))

// identity/network fixtures reject developer services and seed only the isolated Playwright DB.
test('C4 clauses: real required fields, failure draft, discard protection and NORMATIVE payload', async ({
  signedIn: page,
  network,
}) => {
  await page.goto('/governance/clauses')
  await page.getByRole('button', { name: copy.clauses.create, exact: true }).click()
  const dialog = page.getByRole('dialog')
  const fields = dialog.locator('form').getByRole('textbox')
  let writes = 0
  let nature: unknown
  page.on('request', (request) => {
    if (
      new URL(request.url()).pathname === '/api/v1/governance/clauses' &&
      request.method() === 'POST'
    ) {
      writes++
      nature = request.postDataJSON().appendix_nature
    }
  })
  await fields.nth(0).press('Enter')
  await expect(fields.nth(0)).toHaveAttribute('aria-invalid', 'true')
  const errorId = await fields.nth(0).getAttribute('aria-describedby')
  expect(errorId).toBeTruthy()
  await expect(page.locator(`[id="${errorId}"]`)).toContainText(copy.common.required)
  expect(writes).toBe(0)
  const name = uniqueName('C4Clause')
  await fields.nth(0).fill(name)
  await fields.nth(1).fill('1.1')
  await fields.nth(2).fill('自撰示例条款')
  await fields.nth(4).fill('自撰说明与示例，不复制标准正文。')
  await network.failOnce({ path: '/governance/clauses', method: 'POST' }, 503)
  const save = dialog.getByRole('button', { name: copy.common.save, exact: true })
  await save.click()
  await expect(
    dialog.getByRole('alert').filter({ hasText: copy.errors['KG.INTERNAL_ERROR'] }),
  ).toBeVisible()
  await expect(fields.nth(0)).toHaveValue(name)
  expect(nature).toBe('NORMATIVE')
  page.once('dialog', (confirmation) => confirmation.dismiss())
  await dialog.getByRole('button', { name: copy.common.cancel, exact: true }).click()
  await expect(dialog).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  await expectNoPageOverflow(page)
  const response = waitForApi(page, { path: '/governance/clauses', method: 'POST' })
  await save.click()
  await responseData(await response)
  expect(writes).toBe(2)
  await expect(dialog.getByRole('status').filter({ hasText: copy.clauses.saved })).toBeVisible()
  await dialog.getByRole('button', { name: copy.common.cancel, exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await expect(page.getByRole('table').getByRole('row').filter({ hasText: name })).toContainText(
    copy.clauses.normative,
  )
})

test('C4 knowledge: advanced help and zero, same-query failed retry keeps hits, clear/reset remove results', async ({
  signedIn: page,
  identity,
  network,
}) => {
  const query = uniqueName('C4Retrieval')
  const base = await responseData<components['schemas']['KnowledgeBaseOut']>(
    await identity.api.post('/api/v1/knowledge-bases', { data: { name: query } }),
  )
  const document = await responseData<components['schemas']['KnowledgeDocumentOut']>(
    await identity.api.post(`/api/v1/knowledge-bases/${base.id}/documents`, {
      data: Buffer.from(query + ' isolated retrieval example.'),
      headers: { 'Content-Type': 'application/octet-stream' },
      params: { filename: 'c4-example.txt', content_type: 'text/plain' },
    }),
  )
  await expect
    .poll(
      async () =>
        (
          await getData<components['schemas']['KnowledgeDocumentOut']>(
            identity.api,
            `/knowledge-bases/${base.id}/documents/${document.id}`,
          )
        ).searchable,
    )
    .toBe(true)
  await page.goto(`/knowledge-bases/${base.id}/search`)
  await page.getByRole('button', { name: copy.kb.advanced, exact: true }).click()
  const threshold = page.getByRole('spinbutton', { name: copy.kb.minSimilarity })
  await expect(threshold).toBeVisible()
  const helpId = await threshold.getAttribute('aria-describedby')
  expect(helpId).toBeTruthy()
  await expect(page.locator(`[id="${helpId}"]`)).toHaveText(copy.kb.scoreExplanation)
  await threshold.fill('0')
  await page.getByRole('searchbox').fill(query)
  await page.getByRole('searchbox').press('Enter')
  await expect(page.getByTestId('kb-search-hit')).toHaveCount(1)
  await expect(page).toHaveURL(/min_similarity=0/)
  await network.failOnce({ path: `/knowledge-bases/${base.id}/search`, method: 'POST' }, 503)
  await page.getByRole('button', { name: copy.kb.runSearch, exact: true }).click()
  await expect(
    page.getByRole('alert').filter({ hasText: copy.errors['KG.INTERNAL_ERROR'] }),
  ).toBeVisible()
  await expect(page.getByTestId('kb-search-hit')).toHaveCount(1)
  await expect(page.getByRole('searchbox')).toHaveValue(query)
  await page.getByRole('button', { name: copy.ds.search.clear, exact: true }).click()
  await expect(page.getByTestId('kb-search-hit')).toHaveCount(0)
  await page.getByRole('button', { name: copy.ds.search.reset, exact: true }).click()
  await expect(threshold).toHaveValue('0.25')
  await page.setViewportSize({ width: 1280, height: 720 })
  await expectNoPageOverflow(page)
})

test.describe('C4 viewer boundary', () => {
  test.use({ role: 'VIEWER' })
  test('knowledge and clauses keep write entrypoints disabled', async ({ signedIn: page }) => {
    await page.goto('/knowledge-bases')
    await expect(page.getByRole('button', { name: copy.kb.create, exact: true })).toBeDisabled()
    await page.goto('/governance/clauses')
    await expect(
      page.getByRole('button', { name: copy.clauses.create, exact: true }),
    ).toBeDisabled()
  })
})
