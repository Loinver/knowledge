import {
  capture,
  expect,
  getData,
  responseData,
  settleApi,
  test,
} from '../../../../../../e2e/ui-redesign-fixtures.ts'

test('reports run real graph, working ontology and pinned frozen checks without inventing four states', async ({
  signedIn: page,
  identity,
  routeCatalog: catalog,
  evidence,
}, info) => {
  await page.goto(`/graph/reports?graph=${catalog.graphId}`)
  await expect(page.getByRole('heading', { name: '校验与质量', exact: true })).toBeVisible()
  await expect(page.locator('.report-readouts strong')).toHaveText(['—', '—', '—', '—'])
  const run = async (target, buttonName) => {
    const response = page.waitForResponse(
      (res) => res.request().method() === 'POST' && new URL(res.url()).pathname.endsWith(target),
    )
    await page.getByRole('button', { name: buttonName, exact: true }).click()
    return { response: await response, report: await responseData(await response) }
  }
  const graph = await run(`/validation/graph/${catalog.graphId}`, '运行实例校验')
  await settleApi(page, evidence)
  await expect(page.locator('.report-readouts strong')).toHaveText(
    [
      graph.report.summary.pass,
      graph.report.summary.violation,
      graph.report.summary.na,
      graph.report.summary.not_run,
    ].map(String),
  )
  await page
    .locator('.results-table')
    .getByRole('button', { name: '对象详情', exact: true })
    .first()
    .click()
  await expect(page.locator('.report-inspector > code')).toContainText('I0')

  await page
    .locator('.validation-controls')
    .getByRole('radio', { name: '本体库', exact: true })
    .click()
  await page.getByRole('combobox', { name: '选择本体', exact: true }).click()
  await page.getByRole('option', { name: catalog.ontology.name, exact: true }).click()
  const working = await run(`/validation/ontologies/${catalog.ontology.id}`, '校验')
  expect(new URL(working.response.url()).searchParams.get('target')).toBe('WORKING')
  expect(working.report.binding.target).toBe('WORKING')
  await settleApi(page, evidence)
  const a08 = page.locator('.results-table tbody tr').filter({ hasText: 'A08' })
  const workingResults = await getData(
    identity.api,
    `/validation/reports/${working.report.report_id}/results`,
  )
  const actualA08 = workingResults.find((item) => item.check_code === 'A08')
  expect(actualA08).toBeDefined()
  await expect(a08).toContainText(actualA08.state)

  await page.getByRole('combobox', { name: '查看工作内容或冻结版本', exact: true }).click()
  await page.getByRole('option', { name: '冻结快照', exact: true }).click()
  const frozen = await run(`/validation/ontologies/${catalog.ontology.id}`, '校验')
  expect(new URL(frozen.response.url()).searchParams.get('target')).toBe('PUBLISHED')
  expect(new URL(frozen.response.url()).searchParams.get('revision')).toBe(
    String(frozen.report.target_revision),
  )
  expect(frozen.report.binding.target).toBe('PUBLISHED')
  await settleApi(page, evidence)
  await capture(
    page,
    info,
    evidence,
    'validation-pinned-frozen',
    'real API reports, explicit working/frozen bindings and NOT_RUN',
  )
})

test('report ledger remains inside page across four viewports and both themes', async ({
  signedIn: page,
  routeCatalog: catalog,
  evidence,
}, info) => {
  for (const width of [1440, 1024, 768, 375]) {
    await page.setViewportSize({ width, height: 900 })
    for (const theme of ['dark', 'light']) {
      await page.evaluate((value) => localStorage.setItem('kg-theme-mode', value), theme)
      await page.goto(`/graph/reports?graph=${catalog.graphId}`)
      await expect(page.locator('.reports-page')).toBeVisible()
      await page.getByRole('button', { name: '运行实例校验', exact: true }).click()
      await expect(page.locator('.results-table tbody tr').first()).toBeVisible()
      const overflow = await page.evaluate(() => ({
        page: document.documentElement.scrollWidth - innerWidth,
        report: document.querySelector('.reports-page').getBoundingClientRect().right - innerWidth,
      }))
      expect(overflow.page).toBeLessThanOrEqual(1)
      expect(overflow.report).toBeLessThanOrEqual(1)
      await capture(
        page,
        info,
        evidence,
        `validation-${theme}-${width}`,
        'real report responsive table scroll and four-state readouts',
      )
    }
  }
})
