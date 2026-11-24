import type { Locator, Page } from '@playwright/test'

import {
  capture,
  expect,
  expectNoPageOverflow,
  getData,
  responseData,
  settleApi,
  test as fixtureTest,
  uniqueName,
  waitForApi,
} from './ui-redesign-fixtures'

type NavigationBase = { id: number; name: string; documentId: string }
const test = fixtureTest.extend<object, { navigationBase: NavigationBase }>({
  navigationBase: [
    async ({ identity }, use) => {
      const base = await responseData<{ id: number; name: string }>(
        await identity.api.post('/api/v1/knowledge-bases', {
          data: { name: uniqueName('NavigationBase'), description: 'Isolated navigation evidence' },
        }),
      )
      const document = await responseData<{ id: string }>(
        await identity.api.post(`/api/v1/knowledge-bases/${base.id}/documents`, {
          params: { filename: 'navigation-evidence.txt', content_type: 'text/plain' },
          headers: { 'Content-Type': 'application/octet-stream' },
          data: Buffer.from('Navigation evidence from example.org. No external services required.'),
        }),
      )
      // Wait on the isolated real processor, rather than replacing a document response.
      await expect
        .poll(
          async () => {
            const state = await getData<{ searchable: boolean }>(
              identity.api,
              `/knowledge-bases/${base.id}/documents/${document.id}`,
            )
            return state.searchable
          },
          { timeout: 30_000 },
        )
        .toBe(true)
      await use({ ...base, documentId: document.id })
    },
    { scope: 'worker' },
  ],
})

test.use({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' })

const SEARCH = '搜索页面 · ⌘/Ctrl K'
const SEARCH_EN = 'Find a page · ⌘/Ctrl K'
const ROOT_MENU = [
  '工作台',
  '标准语义资产',
  '本体装配与校验',
  '数据接入与抽取',
  '图谱与证据',
  '治理与版本',
  '知识库',
  '系统管理',
]
const SYSTEM_PAGES = [
  { path: '/system/users', route: 'system-users', label: '用户管理' },
  { path: '/system/roles', route: 'system-roles', label: '角色与能力' },
  { path: '/system/audit-logs', route: 'system-audit-logs', label: '操作与资产审计' },
  { path: '/system/ai-models', route: 'system-ai-models', label: 'AI 模型配置' },
]

function sider(page: Page): Locator {
  return page.locator('.app-sider')
}

function crumbs(page: Page): Locator {
  return page.locator(
    '.app-header .breadcrumbs li > a, .app-header .breadcrumbs li > .crumb-current',
  )
}

async function usePreviewSource(page: Page, datasourceId: number) {
  await page.route('**/api/v1/datasources?*', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    body.data = body.data.filter((source: { id: number }) => source.id === datasourceId)
    await route.fulfill({ response, json: body })
  })
}

function selectedMenu(page: Page): Locator {
  return sider(page).getByRole('button').and(page.locator('[aria-current="page"]'))
}

function commandOption(page: Page, route: string): Locator {
  return page.getByRole('option').filter({
    has: page.locator('.command-route').filter({ hasText: new RegExp(`^${route}$`) }),
  })
}

async function openSearch(page: Page, keyboard = false, label = SEARCH): Promise<Locator> {
  if (keyboard)
    await page.evaluate(() =>
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true })),
    )
  else await page.getByRole('button', { name: label, exact: true }).click()
  const input = page.getByPlaceholder(label, { exact: true })
  await expect(page.locator('.command-palette')).toBeVisible()
  await expect(input).toBeFocused()
  await expect(input).toHaveValue('')
  // The command list remains visible while the palette is open.
  await expect(page.locator('#command-results')).toBeVisible()
  return input
}

async function expectLocation(page: Page, path: string): Promise<void> {
  await expect
    .poll(() => {
      const current = new URL(page.url())
      return current.pathname + current.search + current.hash
    })
    .toBe(path)
}

async function openGraphDetail(page: Page, path: string, iri: string): Promise<string> {
  const loaded = waitForApi(page, { path: '/extraction/entity-detail' })
  await page.goto(path)
  const detail = await responseData<{ entity: { iri: string; attrs: { name: string } } }>(
    await loaded,
  )
  expect(detail.entity.iri).toBe(iri)
  expect(typeof detail.entity.attrs.name).toBe('string')
  expect(detail.entity.attrs.name).not.toBe('')
  await expect(page.locator('.page-header .identity')).toHaveText(iri)
  await expect(
    page.getByRole('heading', { name: detail.entity.attrs.name, exact: true }),
  ).toBeVisible()
  return detail.entity.attrs.name
}

test('test_root_order_three_level_expansion_selection_and_hidden_tools @navigation @real-api', async ({
  signedIn: page,
  evidence,
}, info) => {
  await expect(sider(page).locator('.sider-scroll > ul > .nav-branch > button')).toHaveText(
    ROOT_MENU,
  )
  const before = page.url()
  await sider(page).getByText('标准语义资产', { exact: true }).click()
  await expect(page).toHaveURL(before)
  const configuration = sider(page).getByText('资产配置与模板', { exact: true })
  await expect(configuration).toBeVisible()
  await expect(sider(page).getByText('枚举词典', { exact: true })).not.toBeVisible()
  await configuration.click()
  await expect(page).toHaveURL(before)
  const dictionary = sider(page).getByText('枚举词典', { exact: true })
  await expect(dictionary).toBeVisible()
  await dictionary.click()
  await expectLocation(page, '/governance/enum-dictionaries')
  await expect(selectedMenu(page)).toHaveCount(1)
  await expect(selectedMenu(page)).toHaveText('枚举词典')
  await expect(crumbs(page)).toHaveText(['标准语义资产', '资产配置与模板', '枚举词典'])
  await page.reload()
  await expect(selectedMenu(page)).toHaveText('枚举词典')
  await expect(sider(page).getByText('装配模板', { exact: true })).toBeVisible()
  await sider(page).getByText('装配模板', { exact: true }).click()
  await expectLocation(page, '/governance/templates')
  await expect(crumbs(page)).toHaveText(['标准语义资产', '资产配置与模板', '装配模板'])
  await expect(selectedMenu(page)).toHaveText('装配模板')
  await sider(page).getByText('数据接入与抽取', { exact: true }).click()
  await expect(sider(page).getByText('AI 抽取', { exact: true })).toHaveCount(0)
  await expect(sider(page).getByText('样例预览', { exact: true })).toHaveCount(0)
  // Knowledge bases is a root destination, not a group requiring a second click.
  await sider(page).getByText('知识库', { exact: true }).click()
  await expectLocation(page, '/knowledge-bases')
  await expect(selectedMenu(page)).toHaveText('知识库')
  await expect(crumbs(page)).toHaveText(['知识库'])
  // Graph recommendations/fields are independent requests. The route and
  // selected object are already asserted; wait for visible loading to settle.
  await expect(page.locator('[aria-busy="true"]:visible')).toHaveCount(0)
  await capture(page, info, evidence, 'navigation-root-and-three-level', 'real recursive menu')
})

test('test_object_breadcrumbs_use_loaded_identity_and_link_to_owner @navigation @real-api', async ({
  signedIn: page,
  routeCatalog: data,
  navigationBase: base,
  evidence,
}, info) => {
  for (const detail of [
    {
      path: `/ontology/entity-types/${data.published.id}`,
      parent: '实体类型库',
      object: data.published,
    },
    {
      path: `/ontology/relation-types/${data.relation.id}`,
      parent: '关系类型库',
      object: data.relation,
    },
  ]) {
    await page.goto(detail.path)
    await expect(
      page.getByRole('heading', {
        level: 1,
        name: detail.parent === '实体类型库' ? '实体类型详情' : '关系类型详情',
        exact: true,
      }),
    ).toBeVisible()
    await expect(page.locator('.page-header .identity')).toHaveText(detail.object.name)
    await expect(crumbs(page)).toHaveText(['标准语义资产', detail.parent, detail.object.name])
    await expect(selectedMenu(page)).toHaveText(detail.parent)
    await expect(page.getByText(detail.object.iri, { exact: true }).first()).toBeVisible()
    await page
      .locator('.app-header')
      .getByRole('link', { name: detail.parent, exact: true })
      .click()
    await expectLocation(page, detail.path.replace(/\/\d+$/, ''))
  }
  const objectName = await openGraphDetail(
    page,
    `/graph/entities/${encodeURIComponent(data.entityIri)}?graph=${data.graphId}`,
    data.entityIri,
  )
  await expect(crumbs(page)).toHaveText(['图谱与证据', '实体实例', objectName])
  await expect(selectedMenu(page)).toHaveText('实体实例')
  await page.goto(`/knowledge-bases/${base.id}?doc=${base.documentId}`)
  // The modal document drawer makes the correctly rendered background inert.
  await expect(
    page.getByRole('heading', { name: base.name, exact: true, includeHidden: true }),
  ).toBeVisible()
  await expect(crumbs(page)).toHaveText(['知识库', base.name, `文档 ${base.documentId}`])
  await expect(page.getByRole('dialog').and(page.locator('.ui-sheet'))).toBeVisible()
  await page.keyboard.press('Escape')
  await page.goto(`/knowledge-bases/${base.id}/search`)
  await expect(crumbs(page)).toHaveText(['知识库', base.name, '知识检索与证据'])
  await expect(selectedMenu(page)).toHaveText('知识库')
  await page.locator('.app-header').getByRole('link', { name: base.name, exact: true }).click()
  await expectLocation(page, `/knowledge-bases/${base.id}`)
  await expect(crumbs(page)).toHaveText(['知识库', base.name])
  // The knowledge drawer may remain in a bounded 2s polling window while the
  // document is still being indexed; the navigation assertions above do not
  // require that background job to stop.
  await expect(page.locator('[aria-busy="true"]:visible')).toHaveCount(0)
  await capture(page, info, evidence, 'navigation-object-identity', 'loaded object breadcrumbs')
})

for (const role of ['EDITOR', 'VIEWER'] as const) {
  test.describe(`${role} navigation permissions`, () => {
    test.use({ role })
    test(`test_${role.toLowerCase()}_can_search_tools_and_own_account @navigation @real-api`, async ({
      signedIn: page,
      routeCatalog: data,
      evidence,
    }) => {
      await usePreviewSource(page, data.datasourceId)
      for (const entry of [
        { route: 'ai-assist', path: '/extraction/ai-assist' },
        { route: 'sample-preview', path: '/datasources/preview' },
        { route: 'account-profile', path: '/account/profile' },
        { route: 'account-security', path: '/account/security' },
      ]) {
        const search = await openSearch(page, true)
        await search.fill(entry.route)
        await expect(commandOption(page, entry.route)).toHaveCount(1)
        await search.press('Enter')
        await expectLocation(page, entry.path)
      }
      await settleApi(page, evidence)
    })
    for (const destination of SYSTEM_PAGES) {
      test(`test_${role.toLowerCase()}_rejects_${destination.route.replaceAll('-', '_')}_url_and_search @navigation @real-api`, async ({
        signedIn: page,
        evidence,
      }) => {
        await expect(sider(page).getByText('系统管理', { exact: true })).toHaveCount(0)
        const search = await openSearch(page, true)
        // Check both the unfiltered command list and localized/name-key queries.
        for (const entry of SYSTEM_PAGES)
          await expect(commandOption(page, entry.route)).toHaveCount(0)
        for (const query of [destination.label, destination.route]) {
          await search.fill(query)
          await expect(page.getByRole('option')).toHaveCount(0)
          await expect(page.getByText('没有匹配的页面或工具', { exact: true })).toBeVisible()
        }
        await page.keyboard.press('Escape')
        const target = `${destination.path}?from=legacy#saved-panel`
        await page.goto(target)
        await expect.poll(() => new URL(page.url()).pathname).toBe('/forbidden')
        await expect.poll(() => new URL(page.url()).searchParams.get('redirect')).toBe(target)
        await expect(page.getByRole('heading', { name: '无权访问', exact: true })).toBeVisible()
        await page.reload()
        await expect.poll(() => new URL(page.url()).searchParams.get('redirect')).toBe(target)
        await page.getByRole('button', { name: '刷新权限', exact: true }).click()
        await expect.poll(() => new URL(page.url()).pathname).toBe('/forbidden')
        await settleApi(page, evidence)
        expect(
          evidence.responses.filter((entry) =>
            /^\/api\/v1\/(?:users|roles|audit-logs|asset-audit-logs|ai\/model-)/.test(entry.path),
          ),
          'Rejected navigation never requests privileged page data',
        ).toEqual([])
      })
    }
  })
}

test('test_command_palette_tools_accounts_aliases_and_keyboard_navigation @navigation @real-api', async ({
  signedIn: page,
  routeCatalog: data,
  evidence,
}) => {
  await usePreviewSource(page, data.datasourceId)
  for (const entry of SYSTEM_PAGES) {
    const search = await openSearch(page)
    await search.fill(entry.route)
    await expect(commandOption(page, entry.route)).toHaveCount(1)
    await commandOption(page, entry.route).click()
    await expectLocation(page, entry.path)
    await expect(
      page.getByRole('heading', { level: 1, name: entry.label, exact: true }),
    ).toBeVisible()
    await expect(selectedMenu(page)).toHaveText(entry.label)
  }
  for (const entry of [
    {
      query: 'AI 抽取',
      route: 'ai-assist',
      path: '/extraction/ai-assist',
      trail: ['数据接入与抽取', '映射工作台', 'AI 抽取'],
    },
    {
      query: '样例预览',
      route: 'sample-preview',
      path: '/datasources/preview',
      trail: ['数据接入与抽取', '数据目录', '样例预览'],
    },
    { query: '个人中心', route: 'account-profile', path: '/account/profile', trail: ['个人中心'] },
    {
      query: '账号安全',
      route: 'account-security',
      path: '/account/security',
      trail: ['账号安全'],
    },
  ]) {
    const search = await openSearch(page, true)
    await search.fill(entry.query)
    await expect(page.getByRole('option')).toHaveCount(1)
    await expect(commandOption(page, entry.route)).toHaveAttribute('aria-selected', 'true')
    await search.press('Enter')
    await expectLocation(page, entry.path)
    await expect(crumbs(page)).toHaveText(entry.trail)
    await expect(page.locator('.command-palette')).not.toBeVisible()
  }
  const search = await openSearch(page, true)
  await search.fill('知识追溯')
  await expect(commandOption(page, 'graph-evidence')).toHaveCount(1)
  await search.fill('校验报告')
  await expect(commandOption(page, 'graph-reports')).toHaveCount(1)
  await search.fill(data.published.name)
  await expect(page.getByRole('option')).toHaveCount(0)
  await search.fill('account-')
  await expect(page.getByRole('option')).toHaveCount(2)
  await search.press('ArrowDown')
  await expect(commandOption(page, 'account-security')).toHaveAttribute('aria-selected', 'true')
  await search.press('ArrowUp')
  await expect(commandOption(page, 'account-profile')).toHaveAttribute('aria-selected', 'true')
  await search.press('ArrowDown')
  await search.press('Enter')
  await expectLocation(page, '/account/security')
  await settleApi(page, evidence)
})

test('test_detail_search_entries_resolve_to_safe_owner_lists @navigation @real-api', async ({
  signedIn: page,
  evidence,
}) => {
  for (const entry of [
    { query: '实体类型详情', owner: 'entity-types', path: '/ontology/entity-types' },
    { query: '关系类型详情', owner: 'relation-types', path: '/ontology/relation-types' },
    { query: '实体详情', owner: 'graph-entities', path: '/graph/entities' },
    { query: '知识库资料', owner: 'knowledge-bases', path: '/knowledge-bases' },
    { query: '知识检索与证据', owner: 'knowledge-bases', path: '/knowledge-bases' },
  ]) {
    const search = await openSearch(page)
    await search.fill(entry.query)
    await expect(page.getByRole('option')).toHaveCount(1)
    await expect(commandOption(page, entry.owner)).toHaveCount(1)
    await search.press('Enter')
    await expectLocation(page, entry.path)
    await expect(selectedMenu(page)).toHaveCount(1)
    await settleApi(page, evidence)
  }
})

test('test_language_synchronizes_heading_menu_breadcrumb_search_and_document_title @navigation @real-api', async ({
  signedIn: page,
  evidence,
}) => {
  await page.goto('/extraction')
  await expect(page).toHaveTitle('映射工作台 · 知识中台')
  const before = page.url()
  await page.getByRole('button', { name: '切换语言', exact: true }).click()
  await expect(page).toHaveURL(before)
  await expect(page.locator('html')).toHaveAttribute('lang', 'en-US')
  await expect(page).toHaveTitle('Mapping workbench · Knowledge Platform')
  await expect(
    page.getByRole('heading', { level: 1, name: 'Mapping workbench', exact: true }),
  ).toBeVisible()
  await expect(selectedMenu(page)).toHaveText('Mapping workbench')
  await expect(crumbs(page)).toHaveText(['Data integration & extraction', 'Mapping workbench'])
  const search = await openSearch(page, true, SEARCH_EN)
  await search.fill('Sample Preview')
  await expect(commandOption(page, 'sample-preview')).toContainText('Sample Preview')
  await page.keyboard.press('Escape')
  await page.reload()
  await expect(page).toHaveTitle('Mapping workbench · Knowledge Platform')
  await expect(page.locator('html')).toHaveAttribute('lang', 'en-US')
  await page.getByRole('button', { name: 'Switch language', exact: true }).click()
  await expect(page).toHaveTitle('映射工作台 · 知识中台')
  await expect(crumbs(page)).toHaveText(['数据接入与抽取', '映射工作台'])
  await settleApi(page, evidence)
})

test('test_legacy_deep_links_keep_query_hash_iri_reload_back_and_forward @navigation @real-api', async ({
  signedIn: page,
  routeCatalog: data,
  evidence,
}) => {
  await page.goto('/ontology')
  await expectLocation(page, '/ontology/entity-types')
  const listQuery = new URLSearchParams({
    q: data.published.name,
    status: 'PUBLISHED',
    view: 'table',
    page: '1',
  })
  const list = `/ontology/entity-types?${listQuery}#legacy-list`
  const graph = `/graph/entities/${encodeURIComponent(data.entityIri)}?graph=${data.graphId}&q=${encodeURIComponent(data.entityIri)}&page=1&size=25&sort=-iri#legacy-object`
  const listLoaded = waitForApi(page, { path: '/entity-types', query: { q: data.published.name } })
  await page.goto(list)
  await listLoaded
  await expect(page.getByRole('searchbox', { name: '搜索', exact: true })).toHaveValue(
    data.published.name,
  )
  await expect(page.getByRole('row').filter({ hasText: data.published.name })).toBeVisible()
  await expect(page.locator('[aria-busy="true"]:visible')).toHaveCount(0)
  await expectLocation(page, list)
  const reloadedList = waitForApi(page, {
    path: '/entity-types',
    query: { q: data.published.name },
  })
  await page.reload()
  await reloadedList
  await expect(page.getByRole('row').filter({ hasText: data.published.name })).toBeVisible()
  await expect(page.locator('[aria-busy="true"]:visible')).toHaveCount(0)
  await expectLocation(page, list)
  const objectName = await openGraphDetail(page, graph, data.entityIri)
  await expect(selectedMenu(page)).toHaveText('实体实例')
  await expectLocation(page, graph)
  await page.reload()
  await expect(page.locator('.page-header .identity')).toHaveText(data.entityIri)
  await expectLocation(page, graph)
  await page.goBack()
  await expectLocation(page, list)
  await expect(selectedMenu(page)).toHaveText('实体类型库')
  await expect(page.getByRole('searchbox', { name: '搜索', exact: true })).toHaveValue(
    data.published.name,
  )
  await page.goForward()
  await expectLocation(page, graph)
  await expect(crumbs(page)).toHaveText(['图谱与证据', '实体实例', objectName])
  await expect(page.locator('.page-header .identity')).toHaveText(data.entityIri)
  await expect(page.locator('[aria-busy="true"]:visible')).toHaveCount(0)
})

test('test_default_dark_and_both_saved_theme_preferences_survive_reload @navigation @real-api', async ({
  signedIn: page,
  evidence,
}) => {
  await page.evaluate(() => localStorage.removeItem('kg-theme-mode'))
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  for (const theme of ['light', 'dark']) {
    await page.evaluate((value) => localStorage.setItem('kg-theme-mode', value), theme)
    await page.reload()
    if (theme === 'dark') await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    else await expect(page.locator('html')).not.toHaveAttribute('data-theme')
    await expect.poll(() => page.evaluate(() => localStorage.getItem('kg-theme-mode'))).toBe(theme)
    await settleApi(page, evidence)
  }
})

test('test_375_drawer_expands_three_levels_closes_on_destination_and_backdrop @navigation @real-api', async ({
  signedIn: page,
  evidence,
}, info) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await expect(sider(page)).toHaveClass(/is-collapsed/)
  const opener = page.getByRole('button', { name: '展开侧栏', exact: true })
  await opener.click()
  await expect(page.locator('.mobile-backdrop')).toBeVisible()
  await expect(sider(page)).not.toHaveClass(/is-collapsed/)
  await sider(page).getByText('标准语义资产', { exact: true }).click()
  await sider(page).getByText('资产配置与模板', { exact: true }).click()
  await expect(sider(page).getByText('装配模板', { exact: true })).toBeVisible()
  await capture(page, info, evidence, 'navigation-375-menu', 'real three-level mobile drawer')
  await sider(page).getByText('装配模板', { exact: true }).click()
  await expectLocation(page, '/governance/templates')
  await expect(sider(page)).toHaveClass(/is-collapsed/)
  await expect(page.locator('.mobile-backdrop')).toHaveCount(0)
  await expect(crumbs(page)).toHaveText(['标准语义资产', '资产配置与模板', '装配模板'])
  await opener.click()
  await expect(selectedMenu(page)).toHaveText('装配模板')
  const before = page.url()
  await page.locator('.mobile-backdrop').click({ position: { x: 365, y: 100 } })
  await expect(page).toHaveURL(before)
  await expect(sider(page)).toHaveClass(/is-collapsed/)
  await openSearch(page, true)
  await expectNoPageOverflow(page)
  await capture(page, info, evidence, 'navigation-375-command', 'responsive command palette')
  await page.keyboard.press('Escape')
  await settleApi(page, evidence)
})

// Sixteen shell samples supplement the existing 41-page inventory, not a second site matrix.
for (const width of [1440, 1024, 768, 375]) {
  test(`test_graphite_shell_${width}_both_themes_and_languages @navigation @visual @real-api`, async ({
    signedIn: page,
    entityCatalog,
    evidence,
  }, info) => {
    await page.setViewportSize({ width, height: width === 375 ? 812 : 900 })
    for (const theme of ['dark', 'light']) {
      await page.evaluate((value) => {
        localStorage.setItem('kg-theme-mode', value)
        localStorage.setItem('kg-locale', 'zh-CN')
      }, theme)
      await page.goto('/ontology/namespaces')
      for (const locale of ['zh-CN', 'en-US']) {
        if (locale === 'en-US')
          await page.getByRole('button', { name: '切换语言', exact: true }).click()
        const title = locale === 'zh-CN' ? '命名空间' : 'Namespaces'
        const group = locale === 'zh-CN' ? '标准语义资产' : 'Semantic assets'
        await expect(
          page.getByRole('heading', { level: 1, name: title, exact: true }),
        ).toBeVisible()
        await expect(crumbs(page)).toHaveText([group, title])
        await expect(page.locator('html')).toHaveAttribute('lang', locale)
        await expect(page).toHaveTitle(
          `${title} · ${locale === 'zh-CN' ? '知识中台' : 'Knowledge Platform'}`,
        )
        if (theme === 'dark')
          await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
        else await expect(page.locator('html')).not.toHaveAttribute('data-theme')
        await expect(
          page.getByRole('row').filter({ hasText: entityCatalog.namespace.prefix }),
        ).toBeVisible()
        await settleApi(page, evidence)
        await capture(
          page,
          info,
          evidence,
          `graphite-shell-${width}-${theme}-${locale}`,
          'real namespace page and application shell',
        )
        const search = await openSearch(page, false, locale === 'zh-CN' ? SEARCH : SEARCH_EN)
        await search.fill('account-security')
        await expect(commandOption(page, 'account-security')).toHaveCount(1)
        await expectNoPageOverflow(page)
        const box = await page.locator('.command-palette').boundingBox()
        expect(box).not.toBeNull()
        expect(box!.x).toBeGreaterThanOrEqual(0)
        expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1)
        await page.keyboard.press('Escape')
      }
    }
  })
}
