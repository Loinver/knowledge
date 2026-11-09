import { expect, test, type Page } from '@playwright/test'

import { ensureAdmin, loginAsAdmin } from './admin'

const drawer = (page: Page) => page.locator('.n-drawer-content:visible').last()

async function createBase(page: Page, name: string): Promise<number> {
  await page.goto('/knowledge-bases')
  await page.getByRole('button', { name: '创建知识库', exact: true }).click()
  await page.getByLabel('知识库名称', { exact: true }).fill(name)
  await page.getByLabel('描述', { exact: true }).fill('用于真实文档检索与原文证据验证。')
  await drawer(page).getByRole('button', { name: '保存', exact: true }).click()
  await expect(page).toHaveURL(/\/knowledge-bases\/\d+$/)
  return Number(new URL(page.url()).pathname.split('/').pop())
}

async function upload(page: Page, filename: string, text: string, mimeType = 'text/plain') {
  const request = page.waitForRequest(
    (req) => req.method() === 'POST' && /\/knowledge-bases\/\d+\/documents\?/.test(req.url()),
  )
  await page
    .getByLabel('上传文档', { exact: true })
    .setInputFiles({ name: filename, mimeType, buffer: Buffer.from(text) })
  const sent = await request
  expect(sent.headers()['content-type']).toBe('application/octet-stream')
  // Chromium omits File-backed bodies from the request event. Verify bytes
  // through the stored original instead of relying on that instrumentation.
  const uploaded = await sent.response()
  expect(uploaded?.ok()).toBe(true)
  const document = (await uploaded!.json()).data
  const url = new URL(sent.url())
  const original = await page.request.get(`${url.origin}${url.pathname}/${document.id}/original`, {
    headers: { Authorization: sent.headers().authorization },
  })
  expect(original.ok()).toBe(true)
  expect((await original.body()).equals(Buffer.from(text))).toBe(true)
  await expect(drawer(page)).toBeVisible()
  await expect(drawer(page).getByTestId('kb-latest-task')).toContainText(/成功|部分完成/, {
    timeout: 30000,
  })
}

async function confirmArchive(page: Page) {
  await page
    .locator('.n-popconfirm:visible')
    .getByRole('button', { name: '确认', exact: true })
    .click()
}

async function noHorizontalOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
    true,
  )
}

test('real default-service flow: create, raw upload, keyword evidence, VIEWER and archive/restore', async ({
  page,
  browser,
}, testInfo) => {
  await ensureAdmin(page)
  await loginAsAdmin(page)
  const name = `文档证据验证-${Date.now()}-${'跨部门资料归档与查询'.repeat(10)}`
  const id = await createBase(page, name)
  await page.getByRole('button', { name: '编辑', exact: true }).click()
  await page.getByLabel('描述', { exact: true }).fill('已更新的企业资料说明，保留所有历史证据。')
  await drawer(page).getByRole('button', { name: '保存', exact: true }).click()
  await expect(drawer(page)).not.toBeVisible()
  await expect(page.getByText('已更新的企业资料说明，保留所有历史证据。')).toBeVisible()
  await page.getByRole('button', { name: '编辑', exact: true }).click()
  await page.getByLabel('描述', { exact: true }).fill('未保存草稿')
  const discard = page.waitForEvent('dialog').then((dialog) => dialog.accept())
  await page.keyboard.press('Escape')
  await discard
  await expect(drawer(page)).not.toBeVisible()
  await expect(page.getByText('已更新的企业资料说明，保留所有历史证据。')).toBeVisible()
  const filename = `enterprise-source-${'long-filename-'.repeat(12)}.md`
  const marker = `KBPROOF${Date.now()}`
  const source = `# Evidence record\n\n😀 开场文字。\n\n${marker} Vela 项目于 2026 年完成验收。🧪 原文必须逐字保留。\n\n<script>window.__kbInjected=true</script>\n`
  await upload(page, filename, source, 'text/markdown')
  await expect(drawer(page).getByTestId('kb-document-status')).toContainText('可关键词检索')
  await expect(drawer(page).getByTestId('kb-document-status')).toContainText('未配置')
  await drawer(page).getByRole('button', { name: '重新处理', exact: true }).click()
  await expect(drawer(page).getByTestId('kb-latest-task')).toContainText('处理代次 2', {
    timeout: 30000,
  })
  await expect(drawer(page).getByTestId('kb-latest-task')).toContainText('成功', { timeout: 30000 })
  await page.keyboard.press('Escape')
  await expect(drawer(page)).not.toBeVisible()
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 },
    { width: 1024, height: 900 },
  ]) {
    await page.setViewportSize(viewport)
    await noHorizontalOverflow(page)
    await page.screenshot({
      path: testInfo.outputPath(`documents-${viewport.width}.png`),
      fullPage: true,
    })
  }
  await page.getByRole('button', { name: '检索', exact: true }).click()
  await expect(
    page.getByText('未配置嵌入服务，语义与混合检索不可用。关键词检索可正常使用。'),
  ).toBeVisible()
  await expect(
    page.getByText('未配置问答模型，证据摘录回答不可用。文档与关键词检索仍可使用。'),
  ).toBeVisible()
  await page.getByRole('textbox', { name: '输入关键词或问题' }).fill(marker)
  const response = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' && res.url().endsWith(`/knowledge-bases/${id}/search`),
  )
  await page.getByRole('button', { name: '开始检索', exact: true }).click()
  const result = (await (await response).json()).data
  expect(result.items.length).toBeGreaterThan(0)
  await expect(page.getByTestId('kb-search-hit').first()).toContainText(filename)
  const queryUrl = page.url()
  const opener = page.getByRole('button', { name: '查看证据', exact: true }).first()
  await opener.click()
  await expect(drawer(page).getByTestId('kb-evidence-highlight')).toBeVisible()
  expect(await drawer(page).getByTestId('kb-evidence-highlight').textContent()).toBe(
    result.items[0].text,
  )
  expect(await page.evaluate(() => '__kbInjected' in window)).toBe(false)
  await expect(drawer(page).getByRole('heading', { name: '人工关联文档引用' })).toBeVisible()
  const evidenceUrl = page.url()
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 },
    { width: 1024, height: 900 },
  ]) {
    await page.setViewportSize(viewport)
    await noHorizontalOverflow(page)
    await page.screenshot({
      path: testInfo.outputPath(`evidence-${viewport.width}.png`),
      fullPage: true,
    })
  }
  await page.keyboard.press('Escape')
  await expect(drawer(page)).not.toBeVisible()
  await expect(opener).toBeFocused()
  await expect(page).toHaveURL(queryUrl)
  await expect(page.getByTestId('kb-search-hit').first()).toContainText(marker)
  await page.goto(evidenceUrl)
  await expect(drawer(page).getByTestId('kb-evidence-highlight')).toBeVisible()
  await page.keyboard.press('Escape')

  // Real VIEWER account and session. No role or data responses are mocked.
  const account = `kbviewer${Date.now()}`
  const password = 'Knowledge-Viewer-2026!'
  const registered = await page.request.post('/api/v1/auth/register', {
    data: { username: account, email: `${account}@example.org`, password },
  })
  expect(registered.ok()).toBe(true)
  const tokens = (await registered.json()).data
  const me = await page.request.get('/api/v1/auth/me', {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
  })
  expect((await me.json()).data.role).toBe('VIEWER')
  const forbidden = await page.request.post('/api/v1/knowledge-bases', {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
    data: { name: 'Forbidden write' },
  })
  expect(forbidden.status()).toBe(403)
  const context = await browser.newContext({
    baseURL: testInfo.project.use.baseURL,
    viewport: { width: 1440, height: 900 },
  })
  try {
    const viewer = await context.newPage()
    await viewer.goto('/login')
    await viewer.getByPlaceholder('用户名或邮箱', { exact: true }).fill(account)
    await viewer.getByPlaceholder('请输入密码', { exact: true }).fill(password)
    await viewer.getByRole('button', { name: '登录', exact: true }).click()
    await expect(viewer).toHaveURL(/\/$/)
    await viewer.goto(`/knowledge-bases/${id}`)
    await expect(viewer.getByRole('button', { name: '编辑', exact: true })).toBeDisabled()
    await expect(viewer.getByRole('button', { name: '归档', exact: true })).toBeDisabled()
    await expect(viewer.getByLabel('上传文档', { exact: true })).toBeDisabled()
    await viewer.goto(queryUrl)
    await expect(viewer.getByTestId('kb-search-hit').first()).toContainText(marker)
    await viewer.getByRole('button', { name: '查看证据', exact: true }).first().click()
    await expect(drawer(viewer).getByTestId('kb-evidence-highlight')).toBeVisible()
    await expect(
      drawer(viewer).getByRole('button', { name: '添加人工关联', exact: true }),
    ).toHaveCount(0)
  } finally {
    await context.close()
  }

  await page.goto(`/knowledge-bases/${id}`)
  await page.getByRole('button', { name: '归档', exact: true }).click()
  await confirmArchive(page)
  await expect(page.getByText('已归档，可随时恢复。')).toBeVisible()
  await page.goto(evidenceUrl)
  await expect(
    drawer(page).getByText('这是已归档文档或知识库中的保留证据，不参与当前检索。'),
  ).toBeVisible()
  await page.goto(`/knowledge-bases/${id}`)
  await page.getByRole('button', { name: '恢复', exact: true }).click()
  await confirmArchive(page)
  await expect(page.getByText('已恢复。', { exact: true })).toBeVisible()
  await page.goto(queryUrl)
  await expect(page.getByTestId('kb-search-hit').first()).toContainText(marker)
})

test('CSV partial parsing, duplicate ingestion and document archive/restore preserve honest task state', async ({
  page,
}) => {
  await ensureAdmin(page)
  await loginAsAdmin(page)
  const id = await createBase(page, `CSV partial ${Date.now()}`)
  const source = 'code,description\nCSVPROOF,complete evidence record\nBAD,"unterminated field'
  await upload(page, 'partial.csv', source, 'text/csv')
  await expect(drawer(page).getByTestId('kb-latest-task')).toContainText('部分完成')
  await expect(
    drawer(page).getByText('CSV 格式错误，请检查分隔符、引号与行内容。').first(),
  ).toBeVisible()
  await expect(drawer(page).getByTestId('kb-document-status')).toContainText('可关键词检索')
  const doc = new URL(page.url()).searchParams.get('doc')
  await page.keyboard.press('Escape')
  await upload(page, 'same-content.csv', source, 'text/csv')
  expect(new URL(page.url()).searchParams.get('doc')).toBe(doc)
  await page.keyboard.press('Escape')
  await expect(page.getByText('检测到相同内容，已打开现有文档，未重复创建。')).toBeVisible()
  await page.getByRole('button', { name: '详情与任务', exact: true }).click()
  await drawer(page).getByRole('button', { name: '归档', exact: true }).click()
  await confirmArchive(page)
  await expect(drawer(page).getByRole('button', { name: '恢复', exact: true })).toBeVisible()
  await expect(drawer(page).getByRole('button', { name: '重新处理', exact: true })).toBeDisabled()
  await drawer(page).getByRole('button', { name: '恢复', exact: true }).click()
  await confirmArchive(page)
  await expect(drawer(page).getByRole('button', { name: '归档', exact: true })).toBeVisible()
  await page.goto(`/knowledge-bases/${id}/search?q=CSVPROOF&mode=KEYWORD`)
  await expect(page.getByTestId('kb-search-hit').first()).toContainText('CSVPROOF')
  await expect(page.getByTestId('kb-search-hit').first()).toContainText('第 2 行记录')
})

test('explicitly injected document-list service failure remains visible and retry recovers real data', async ({
  page,
}) => {
  await ensureAdmin(page)
  await loginAsAdmin(page)
  const id = await createBase(page, `List failure ${Date.now()}`)
  let injected = false
  await page.route(`**/api/v1/knowledge-bases/${id}/documents?*`, async (route) => {
    if (!injected) {
      injected = true
      await route.fulfill({
        status: 503,
        json: {
          code: 'KG.SOURCE_UNREACHABLE',
          message: 'Injected test failure',
          params: {},
          data: null,
        },
      })
    } else await route.continue()
  })
  await page.reload()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(
    page.getByText('暂无文档。上传 UTF-8 文本、Markdown 或 CSV 开始建立索引。'),
  ).toHaveCount(0)
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await expect(
    page.getByText('暂无文档。上传 UTF-8 文本、Markdown 或 CSV 开始建立索引。'),
  ).toBeVisible()
})

test('loading, immutable invalid UTF-8 retry and empty search stay truthful', async ({
  page,
}, info) => {
  await ensureAdmin(page)
  await loginAsAdmin(page)
  const id = await createBase(page, `Failure states ${Date.now()}`)
  let release = () => {}
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route(`**/api/v1/knowledge-bases/${id}/documents?*`, async (route) => {
    await gate
    await route.continue()
  })
  await page.reload()
  await expect(page.getByRole('status')).toContainText('正在加载')
  await expect(page.getByRole('button', { name: '编辑', exact: true })).toBeDisabled()
  await page.screenshot({ path: info.outputPath('knowledge-loading.png'), fullPage: true })
  release()
  await expect(
    page.getByText('暂无文档。上传 UTF-8 文本、Markdown 或 CSV 开始建立索引。'),
  ).toBeVisible()
  await page.unroute(`**/api/v1/knowledge-bases/${id}/documents?*`)

  await page.getByLabel('上传文档', { exact: true }).setInputFiles({
    name: 'invalid-utf8.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from([0xff, 0xfe, 0x41]),
  })
  const task = drawer(page).getByTestId('kb-latest-task')
  await expect(task).toContainText('失败', { timeout: 30000 })
  await expect(drawer(page)).toContainText('文件不是有效的 UTF-8 文本。')
  await expect(drawer(page).getByTestId('kb-document-status')).toContainText('不可检索')
  await drawer(page).getByRole('button', { name: '重新处理', exact: true }).click()
  await expect(task).toContainText('处理代次 2', { timeout: 30000 })
  await expect(task).toContainText('失败', { timeout: 30000 })
  await page.screenshot({ path: info.outputPath('knowledge-failed-retry.png'), fullPage: true })
  await page.keyboard.press('Escape')
  await upload(page, 'valid-replacement.txt', 'REPAIREDUTF8 Valid replacement material.')
  await page.keyboard.press('Escape')
  await page.goto(`/knowledge-bases/${id}/search?q=NO_MATCH_987654321&mode=KEYWORD`)
  await expect(
    page.getByText('没有符合本次查询与阈值的证据。请调整关键词、检索模式或阈值。'),
  ).toBeVisible()
  await expect(page.getByTestId('kb-search-hit')).toHaveCount(0)
  await page.screenshot({ path: info.outputPath('knowledge-no-match.png'), fullPage: true })
})
