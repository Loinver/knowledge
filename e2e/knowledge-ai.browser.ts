import { expect, test, responseData, capture } from './ui-redesign-fixtures'

test('isolated model protocol: semantic hybrid citations error cancellation and graph references', async ({
  signedIn: page,
  identity,
  routeCatalog,
  evidence,
}, info) => {
  const api = identity.api
  const base = await responseData<{ id: number }>(
    await api.post('/api/v1/knowledge-bases', {
      data: { name: '隔离模型协议验收资料库', description: '演示夹具；不代表真实模型效果' },
    }),
  )
  const source = '设备维护周期为三个月，检修负责人是运营部门。\n\n会议每周一召开，由行政人员记录。'
  const doc = await responseData<{ id: string; revision: number }>(
    await api.post(`/api/v1/knowledge-bases/${base.id}/documents`, {
      headers: { 'Content-Type': 'application/octet-stream' },
      params: { filename: 'maintenance.txt', content_type: 'text/plain' },
      data: Buffer.from(source),
    }),
  )
  await expect
    .poll(
      async () => {
        const response = await api.get(`/api/v1/knowledge-bases/${base.id}/documents/${doc.id}`)
        return (await response.json()).data.semantic_status
      },
      { timeout: 30000 },
    )
    .toBe('READY')
  await page.goto(`/knowledge-bases/${base.id}/search?q=保养&mode=SEMANTIC`)
  await expect(page.getByTestId('kb-search-hit')).toHaveCount(1)
  await expect(page.getByTestId('kb-search-hit')).toContainText('设备维护周期')
  await expect(page.getByTestId('kb-search-hit')).toContainText('余弦相似度')
  await capture(
    page,
    info,
    evidence,
    'semantic-results',
    'real SQL index and HTTP test embedding fixture; 2 chunks, 3 dimensions',
  )
  await page.goto(`/knowledge-bases/${base.id}/search?q=维护&mode=HYBRID`)
  await expect(page.getByTestId('kb-search-hit').first()).toContainText('关键词分数')
  await expect(page.getByTestId('kb-search-hit').first()).toContainText('余弦相似度')
  await page.goto(`/knowledge-bases/${base.id}/search?q=维护&mode=HYBRID&kind=answer`)
  await expect(page.locator('.kb-quote')).toHaveCount(1)
  await expect(page.locator('.kb-quote')).toContainText('设备维护周期为三个月')
  await page.locator('.kb-quote button').click()
  await expect(page.getByTestId('kb-evidence-highlight')).toContainText('设备维护周期')
  await capture(
    page,
    info,
    evidence,
    'answer-citation',
    'real HTTP test chat fixture; citation exact-match validation',
  )
  await page.keyboard.press('Escape')
  evidence.allowedFailures.push({
    method: 'POST',
    path: `/api/v1/knowledge-bases/${base.id}/search`,
    status: 502,
  })
  await page.goto(`/knowledge-bases/${base.id}/search?q=LIMIT_TEST维护&mode=SEMANTIC`)
  await expect(page.getByRole('alert')).toContainText('限流')
  await expect(page.getByRole('textbox', { name: '输入关键词或问题' })).toHaveValue(
    'LIMIT_TEST维护',
  )
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('限流')
  await page.goto(`/knowledge-bases/${base.id}/search?q=SLOW_TEST维护&mode=SEMANTIC`)
  await page.getByRole('button', { name: '取消检索', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '输入关键词或问题' })).toHaveValue('SLOW_TEST维护')
  await page.getByRole('textbox', { name: '输入关键词或问题' }).fill('维护')
  await page.getByRole('button', { name: '开始检索', exact: true }).click()
  await expect(page.getByTestId('kb-search-hit')).toHaveCount(1)
  await page.waitForTimeout(3200)
  await expect(page.getByRole('textbox', { name: '输入关键词或问题' })).toHaveValue('维护')

  const results = await responseData<{ items: { chunk_id: string }[] }>(
    await api.post(`/api/v1/knowledge-bases/${base.id}/search`, { data: { q: '维护' } }),
  )
  const chunk = results.items[0].chunk_id
  await responseData(
    await api.post(`/api/v1/knowledge-bases/${base.id}/evidence/${chunk}/links`, {
      headers: { 'If-Match': String(doc.revision) },
      data: { graph_revision_id: routeCatalog.graphId, entity_iri: routeCatalog.entityIri },
    }),
  )
  const searchPath = `/knowledge-bases/${base.id}/search?q=维护&mode=KEYWORD&evidence=${encodeURIComponent(chunk)}`
  await page.goto(
    '/graph?' +
      new URLSearchParams({
        graph: String(routeCatalog.graphId),
        center: routeCatalog.entityIri,
        kbReturn: searchPath,
      }),
  )
  const inspector = page.locator('.graph-inspector')
  await expect(inspector.getByRole('heading', { name: '人工关联文档引用' })).toBeVisible()
  const cameraBefore = await page.locator('.graph-scene').getAttribute('transform')
  expect(cameraBefore).toBeTruthy()
  await inspector.getByRole('button', { name: '查看证据', exact: true }).click()
  await expect(page.locator('.source-context mark')).toContainText('设备维护周期')
  await page.keyboard.press('Escape')
  await expect(page.locator('.n-drawer')).not.toBeVisible()
  await expect(page.locator('.graph-scene')).toHaveAttribute('transform', cameraBefore!)
  await page.getByRole('link', { name: '返回知识库检索' }).click()
  await expect(page.getByTestId('kb-evidence-highlight')).toContainText('设备维护周期')
  await page.keyboard.press('Escape')
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 },
    { width: 1024, height: 900 },
  ]) {
    await page.setViewportSize(viewport)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    )
    await capture(
      page,
      info,
      evidence,
      `hybrid-${viewport.width}`,
      '2-chunk synthetic document, 3-dimensional test embeddings; not model-quality evidence',
    )
  }

  const documentPath = `/api/v1/knowledge-bases/${base.id}/documents/${doc.id}`
  const currentDocument = await responseData<{ revision: number; active_generation: number }>(
    await api.get(documentPath),
  )
  await responseData(
    await api.post(`${documentPath}/reprocess`, {
      headers: { 'If-Match': String(currentDocument.revision) },
    }),
  )
  await expect
    .poll(
      async () => {
        const current = await responseData<{ active_generation: number }>(
          await api.get(documentPath),
        )
        return current.active_generation
      },
      { timeout: 30000 },
    )
    .toBeGreaterThan(currentDocument.active_generation)
  await page.goto(
    '/graph?' +
      new URLSearchParams({
        graph: String(routeCatalog.graphId),
        center: routeCatalog.entityIri,
      }),
  )
  const references = inspector.locator('.document-references')
  await expect(references.getByRole('alert')).toContainText('历史处理代次')
  await expect(references.locator('.reference-metadata')).toContainText(
    `处理代次 ${currentDocument.active_generation}`,
  )
  await references.getByRole('button', { name: '查看证据', exact: true }).click()
  await expect(page.locator('.n-drawer .reference-metadata')).toContainText(
    `处理代次 ${currentDocument.active_generation}`,
  )
  await expect(page.locator('.n-drawer').getByRole('alert')).toContainText('历史处理代次')
  await expect(page.locator('.source-context mark')).toContainText('设备维护周期')
  await capture(
    page,
    info,
    evidence,
    'historical-graph-reference',
    'old graph reference keeps its pinned generation and source location after reprocessing',
  )
  await page.keyboard.press('Escape')

  const reprocessed = await responseData<{ revision: number }>(await api.get(documentPath))
  await responseData(
    await api.post(`${documentPath}/archive`, {
      headers: { 'If-Match': String(reprocessed.revision) },
    }),
  )
  await page.reload()
  await expect(references.getByRole('button', { name: '查看证据', exact: true })).toHaveCount(0)
  await expect(references).toContainText('暂无人工关联的文档引用')
})
