import type { Page } from '@playwright/test'

import {
  attachJson,
  capture,
  DESKTOP_VIEWPORTS,
  expect,
  getData,
  responseData,
  settleApi,
  test,
  uniqueName,
  waitForApi,
} from './ui-redesign-fixtures'
import type { Resource, RouteCatalog } from './ui-redesign-fixtures'

type RouteCase = {
  id: string
  path: string | ((data: RouteCatalog) => string)
  title?: string | ((data: RouteCatalog) => string)
  api?: string | ((data: RouteCatalog) => string)
  state?: string
}

// Explicit design-matrix inventory. Test assertions never import application source or locales.
const PUBLIC_ROUTES: RouteCase[] = [
  { id: 'A01', path: '/login', title: '登录' },
  { id: 'A02', path: '/register', title: '注册账号' },
  { id: 'A03', path: '/forgot-password', title: '找回密码', state: 'self-service-unavailable' },
  { id: 'A04', path: '/reset-password', title: '重置密码', state: 'missing-token-disabled' },
]
const AUTHENTICATED_ROUTES: RouteCase[] = [
  { id: 'A05', path: '/account/profile', title: '个人中心', api: '/auth/me' },
  { id: 'A06', path: '/account/security', title: '账号安全' },
  { id: 'W01', path: '/', title: '工作台', api: '/dashboard/stats' },
  { id: 'O01', path: '/ontology/ontologies', title: '本体库', api: '/ontologies' },
  { id: 'O02', path: '/ontology/entity-types', title: '实体类型库', api: '/entity-types' },
  {
    id: 'O03',
    path: (d) => '/ontology/entity-types/' + d.published.id,
    title: (d) => d.published.label_i18n['zh-CN'],
    api: (d) => '/entity-types/' + d.published.id,
  },
  { id: 'O04', path: '/ontology/relation-types', title: '关系类型库', api: '/relations' },
  {
    id: 'O05',
    path: (d) => '/ontology/relation-types/' + d.relation.id,
    title: (d) => d.relation.label_i18n['zh-CN'],
    api: (d) => '/relations/' + d.relation.id,
  },
  { id: 'O06', path: '/ontology/namespaces', title: '命名空间', api: '/namespaces' },
  { id: 'O07', path: '/ontology/domains', title: '业务域', api: '/domains' },
  {
    id: 'O08',
    path: (d) => '/ontology/designer?ontology=' + d.ontology.id,
    api: (d) => '/ontologies/' + d.ontology.id,
  },
  { id: 'D01', path: '/datasources', title: '数据源', api: '/datasources' },
  {
    id: 'D02',
    path: (d) => '/datasources/catalog?datasourceId=' + d.datasourceId,
    title: '数据目录',
    api: (d) => '/datasources/' + d.datasourceId + '/metadata/latest',
  },
  {
    id: 'D03',
    path: (d) =>
      '/datasources/preview?datasourceId=' + d.datasourceId + '&schema=main&table=enterprise',
    title: '样例预览',
    api: (d) => '/datasources/' + d.datasourceId + '/metadata/latest',
    state: 'table-selected-before-preview',
  },
  {
    id: 'M01',
    path: (d) => '/extraction?mapping=' + d.mappingId,
    title: '映射向导',
    api: (d) => '/mappings/' + d.mappingId,
  },
  {
    id: 'M02',
    path: '/extraction/tasks',
    title: '抽取任务',
    api: '/extraction/tasks',
    state: 'no-created-task',
  },
  { id: 'M03', path: '/extraction/runs', title: '抽取运行', api: '/extraction/runs' },
  { id: 'M04', path: '/extraction/ai-assist', title: 'AI 助手', state: 'before-ai-request' },
  {
    id: 'G01',
    path: (d) => '/graph?graph=' + d.graphId,
    title: '图谱浏览',
    api: '/extraction/graph-view',
  },
  {
    id: 'G02',
    path: (d) => '/graph/entities?graph=' + d.graphId,
    title: '实体实例',
    api: '/extraction/entities',
  },
  {
    id: 'G03',
    path: (d) => '/graph/entities/' + encodeURIComponent(d.entityIri) + '?graph=' + d.graphId,
    title: '实体详情',
    api: '/extraction/entity-detail',
  },
  {
    id: 'G04',
    path: (d) =>
      '/graph/evidence?mode=entity&graph=' + d.graphId + '&iri=' + encodeURIComponent(d.entityIri),
    title: '知识追溯',
    api: '/extraction/evidence/trace/entity',
  },
  {
    id: 'G05',
    path: '/graph/reports',
    title: '实例校验报告',
    api: '/extraction/graph/revisions',
    state: 'before-validation',
  },
  {
    id: 'V01',
    path: '/governance/rules',
    title: '规则库',
    api: '/governance/rules',
    state: 'existing-or-empty-rules',
  },
  {
    id: 'V02',
    path: '/governance/clauses',
    title: '标准条款',
    api: '/governance/clauses',
    state: 'existing-or-empty-clauses',
  },
  {
    id: 'V03',
    path: '/governance/enum-dictionaries',
    title: '枚举词典',
    api: '/governance/enum-dictionaries',
    state: 'existing-or-empty-dictionaries',
  },
  { id: 'V04', path: '/governance/templates', title: '装配模板', api: '/governance/templates' },
  { id: 'V05', path: '/governance/export', title: '版本与交换', state: 'before-export-or-import' },
  { id: 'S01', path: '/system/users', title: '用户管理', api: '/users' },
  { id: 'S02', path: '/system/roles', title: '角色管理', api: '/roles' },
  { id: 'S03', path: '/system/audit-logs', title: '操作日志' },
  { id: 'E01', path: '/forbidden', state: 'forbidden' },
  { id: 'E02', path: '/ui-redesign-unknown-route', state: 'not-found' },
]

const LIST = '/ontology/entity-types'
const EMPTY_START = '暂无对象，创建第一个资源开始建模。'
const EMPTY_FILTERED = '没有符合当前筛选的对象'
const READONLY = '当前角色仅可查看，编辑操作需要编辑者或管理员权限。'

function rowFor(page: Page, resource: Resource) {
  return page.getByRole('row').filter({ hasText: resource.name })
}

function drawer(page: Page) {
  return page.locator('.n-drawer:visible').last()
}

function resolveValue(value: string | ((d: RouteCatalog) => string), data: RouteCatalog): string {
  return typeof value === 'string' ? value : value(data)
}

async function openFilteredList(page: Page, resource: Resource): Promise<void> {
  const loaded = waitForApi(page, { path: '/entity-types', query: { q: resource.name } })
  await page.goto(LIST + '?q=' + resource.name)
  const items = await responseData<Resource[]>(await loaded)
  expect(items.map((item) => item.id)).toContain(resource.id)
  await expect(rowFor(page, resource)).toBeVisible()
}

for (const viewport of DESKTOP_VIEWPORTS) {
  test.describe(`desktop_${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport, locale: 'zh-CN', timezoneId: 'Asia/Shanghai', deviceScaleFactor: 1 })

    test.describe('@routes @real-api', () => {
      for (const entry of PUBLIC_ROUTES) {
        test(`test_${entry.id}_public_render`, async ({ page, evidence }, testInfo) => {
          await page.goto(entry.path as string)
          await expect(
            page.getByRole('heading', { name: entry.title as string, exact: true }),
          ).toBeVisible()
          await settleApi(page, evidence)
          await expect(page).toHaveURL(new RegExp((entry.path as string) + '$'))
          if (entry.id === 'A04') {
            await expect(page.getByRole('button', { name: '确认重置', exact: true })).toBeDisabled()
          }
          if (entry.id === 'A03') {
            await expect(
              page.getByText(/自助找回.*未开放|未开放.*自助找回|联系管理员/).first(),
            ).toBeVisible()
          }
          await capture(page, testInfo, evidence, entry.id, entry.state ?? 'public-form')
        })
      }

      for (const entry of AUTHENTICATED_ROUTES) {
        test(`test_${entry.id}_authenticated_render`, async ({
          signedIn: page,
          routeCatalog,
          evidence,
        }, testInfo) => {
          const path = resolveValue(entry.path, routeCatalog)
          const loaded = entry.api
            ? waitForApi(page, { path: resolveValue(entry.api, routeCatalog) })
            : undefined
          await page.goto(path)
          const result = loaded ? await responseData<unknown>(await loaded) : undefined
          await expect
            .poll(() => new URL(page.url()).pathname)
            .toBe(new URL(path, 'http://local').pathname)
          if (entry.title) {
            await expect(
              page.getByRole('heading', {
                name: resolveValue(entry.title, routeCatalog),
                exact: true,
              }),
            ).toBeVisible()
          } else if (entry.id === 'O08') {
            await expect(page.getByRole('button', { name: '自动布局', exact: true })).toBeVisible()
            await expect(page.locator('.designer svg').first()).toBeVisible()
          } else {
            await expect(
              page.getByText(entry.id === 'E01' ? '无权访问' : '页面不存在', { exact: true }),
            ).toBeVisible()
            await expect(
              page.getByRole('button', { name: '返回工作台', exact: true }),
            ).toBeVisible()
          }
          await settleApi(page, evidence)
          await expect(page.locator('.n-alert--error:visible')).toHaveCount(0)
          if (entry.id === 'O03' || entry.id === 'O05') {
            const expected = entry.id === 'O03' ? routeCatalog.published : routeCatalog.relation
            expect((result as Resource).id).toBe(expected.id)
            await expect(page.getByText(expected.iri, { exact: true }).first()).toBeVisible()
          }
          if (entry.id === 'G03') {
            expect((result as { entity: { iri: string } }).entity.iri).toBe(routeCatalog.entityIri)
            await expect(page.locator('p.iri')).toHaveText(routeCatalog.entityIri)
          }
          await capture(page, testInfo, evidence, entry.id, entry.state ?? 'seeded-render')
        })
      }
    })

    test.describe('@entity-types @real-api', () => {
      test('test_normal_preview_detail_and_return_query', async ({
        signedIn: page,
        entityCatalog,
        evidence,
      }, testInfo) => {
        const { published } = entityCatalog
        await openFilteredList(page, published)
        await expect(page.locator('html')).not.toHaveAttribute('data-theme', 'dark')
        const row = rowFor(page, published)
        await expect(row.getByText('已发布', { exact: true })).toBeVisible()
        await expect(row.getByRole('button', { name: '查看', exact: true })).toBeVisible()
        await expect(row.getByRole('button', { name: '编辑', exact: true })).toHaveCount(0)
        await capture(page, testInfo, evidence, 'O02-normal', 'real-published-list')

        await row.getByRole('button', { name: published.label_i18n['zh-CN'], exact: true }).click()
        await expect(drawer(page)).toBeVisible()
        await expect(drawer(page).getByText(published.iri, { exact: true })).toBeVisible()
        await expect(drawer(page).getByText(/已发布.*修订.*冻结版本/)).toBeVisible()
        await expect
          .poll(() => new URL(page.url()).searchParams.get('preview'))
          .toBe(String(published.id))
        const before = new URL(page.url()).search
        await capture(page, testInfo, evidence, 'O02-preview', 'published-preview')

        const loaded = waitForApi(page, { path: '/entity-types/' + published.id })
        await drawer(page).getByRole('button', { name: '查看', exact: true }).click()
        expect((await responseData<Resource>(await loaded)).id).toBe(published.id)
        await expect(
          page.getByRole('heading', { name: published.label_i18n['zh-CN'], exact: true }),
        ).toBeVisible()
        await expect(page.getByRole('button', { name: '修订下一版', exact: true })).toBeEnabled()
        await expect(page.getByRole('button', { name: '编辑', exact: true })).toHaveCount(0)
        await capture(page, testInfo, evidence, 'O03-published', 'frozen-read-only-details')
        await page.getByRole('link', { name: '返回列表位置', exact: true }).click()
        await expect.poll(() => new URL(page.url()).search).toBe(before)
        await expect(page.getByPlaceholder('搜索', { exact: true })).toHaveValue(published.name)
        await expect(drawer(page).getByText(published.iri, { exact: true })).toBeVisible()
        await page.reload()
        await expect(drawer(page).getByText(published.iri, { exact: true })).toBeVisible()
        await expect.poll(() => new URL(page.url()).search).toBe(before)
      })

      test('test_search_no_results_then_clear_filters', async ({
        signedIn: page,
        entityCatalog,
        evidence,
      }, testInfo) => {
        await openFilteredList(page, entityCatalog.draft)
        const query = uniqueName('NoSuchUiType')
        await page.getByPlaceholder('搜索', { exact: true }).fill(query)
        const loaded = waitForApi(page, { path: '/entity-types', query: { q: query } })
        await page.getByPlaceholder('搜索', { exact: true }).press('Enter')
        expect(await responseData<Resource[]>(await loaded)).toEqual([])
        await expect(page.getByText(EMPTY_FILTERED, { exact: true })).toBeVisible()
        await expect(page.getByText(EMPTY_START, { exact: true })).toHaveCount(0)
        await expect.poll(() => new URL(page.url()).searchParams.get('q')).toBe(query)
        await capture(page, testInfo, evidence, 'O02-no-results', 'real-filtered-empty')
        await page.getByRole('button', { name: '清除筛选', exact: true }).click()
        await expect(page.getByPlaceholder('搜索', { exact: true })).toHaveValue('')
        await expect.poll(() => new URL(page.url()).searchParams.has('q')).toBe(false)
        await expect(page.getByText(EMPTY_FILTERED, { exact: true })).toHaveCount(0)
        await expect(
          page
            .getByRole('row')
            .filter({ has: page.getByRole('button', { name: '查看', exact: true }) })
            .first(),
        ).toBeVisible()
      })

      test('test_card_and_status_query_survive_reload', async ({
        signedIn: page,
        entityCatalog,
        evidence,
      }, testInfo) => {
        await openFilteredList(page, entityCatalog.published)
        await page
          .locator('.stats')
          .getByRole('button', { name: /已发布/ })
          .click()
        await page.getByRole('button', { name: '卡片', exact: true }).click()
        await expect.poll(() => new URL(page.url()).searchParams.get('status')).toBe('PUBLISHED')
        await expect.poll(() => new URL(page.url()).searchParams.get('view')).toBe('card')
        await page.reload()
        await expect(
          page.getByRole('button', { name: new RegExp(entityCatalog.published.name) }),
        ).toBeVisible()
        await expect(page.getByPlaceholder('搜索', { exact: true })).toHaveValue(
          entityCatalog.published.name,
        )
        await capture(page, testInfo, evidence, 'O02-card', 'real-card-filter-restored')
      })

      test('test_existing_dark_preference_survives', async ({
        signedIn: page,
        entityCatalog,
        evidence,
      }, testInfo) => {
        await page.evaluate(() => localStorage.setItem('kg-theme-mode', 'dark'))
        await openFilteredList(page, entityCatalog.draft)
        await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
        await page.reload()
        await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
        await capture(page, testInfo, evidence, 'O02-dark-preference', 'existing-dark-preference')
      })

      test('test_all_query_fields_survive_detail_return', async ({
        signedIn: page,
        entityCatalog,
        identity,
        evidence,
      }, testInfo) => {
        const { published } = entityCatalog
        const domain = await responseData<{ id: number }>(
          await identity.api.post('/api/v1/domains', {
            data: {
              name: uniqueName('UiFilterDomain'),
              iri: 'https://example.org/' + uniqueName('filter-domain') + '/',
              label_i18n: { 'zh-CN': 'UI 筛选域', 'en-US': 'UI filter domain' },
              member_ids: [published.id],
            },
          }),
        )
        const query = new URLSearchParams({
          q: published.name,
          status: 'PUBLISHED',
          domain: String(domain.id),
          violation: '0',
          view: 'card',
          page: '1',
          preview: String(published.id),
        })
        await page.goto(LIST + '?' + query.toString())
        await expect(drawer(page).getByText(published.iri, { exact: true })).toBeVisible()
        await drawer(page).getByRole('button', { name: '查看', exact: true }).click()
        await expect(
          page.getByRole('heading', { name: published.label_i18n['zh-CN'], exact: true }),
        ).toBeVisible()
        await page.getByRole('link', { name: '返回列表位置', exact: true }).click()
        await expect
          .poll(() => Object.fromEntries(new URL(page.url()).searchParams))
          .toEqual(Object.fromEntries(query))
        await page.reload()
        await expect(drawer(page).getByText(published.iri, { exact: true })).toBeVisible()
        await expect
          .poll(() => Object.fromEntries(new URL(page.url()).searchParams))
          .toEqual(Object.fromEntries(query))
        await capture(
          page,
          testInfo,
          evidence,
          'O02-query-restored',
          'real-domain-filter-and-complete-query',
        )
      })
    })

    test.describe('@entity-types @injected', () => {
      test('test_empty_dataset', async ({ signedIn: page, network, evidence }, testInfo) => {
        await network.empty({ path: '/entity-types' }, [])
        await network.empty(
          { path: '/entity-types/stats' },
          { total: 0, published: 0, draft: 0, violation: 0 },
        )
        await page.goto(LIST)
        await expect(page.getByText(EMPTY_START, { exact: true })).toBeVisible()
        await expect(page.getByRole('button', { name: '创建', exact: true })).toBeEnabled()
        await expect(page.getByRole('alert')).toHaveCount(0)
        await capture(page, testInfo, evidence, 'O02-empty', 'controlled-empty-list-and-stats')
        expect(evidence.injections.every((entry) => entry.hits > 0)).toBe(true)
      })

      test('test_loading_then_real_data', async ({
        signedIn: page,
        entityCatalog,
        network,
        evidence,
      }, testInfo) => {
        const gate = await network.hold({ path: '/entity-types' })
        try {
          await page.goto(LIST + '?q=' + entityCatalog.draft.name)
          await expect.poll(gate.hits).toBe(1)
          await expect(page.locator('[aria-busy="true"]')).toBeVisible()
          await expect(page.getByText(EMPTY_START, { exact: true })).toHaveCount(0)
          await expect(page.getByText(EMPTY_FILTERED, { exact: true })).toHaveCount(0)
          await capture(page, testInfo, evidence, 'O02-loading', 'real-get-held-before-response')
          const loaded = waitForApi(page, { path: '/entity-types' })
          gate.release()
          expect((await responseData<Resource[]>(await loaded)).map((item) => item.id)).toContain(
            entityCatalog.draft.id,
          )
          await expect(rowFor(page, entityCatalog.draft)).toBeVisible()
          await expect(page.locator('[aria-busy="true"]')).toHaveCount(0)
        } finally {
          gate.release()
        }
      })

      test('test_503_retry_recovers_real_data', async ({
        signedIn: page,
        entityCatalog,
        network,
        evidence,
      }, testInfo) => {
        await network.failOnce({ path: '/entity-types' })
        await page.goto(LIST + '?q=' + entityCatalog.published.name)
        const alert = page.getByRole('alert')
        await expect(alert.getByRole('button', { name: '重试', exact: true })).toBeVisible()
        await expect(alert).toContainText(/错误|失败/)
        await expect(page.getByText(EMPTY_FILTERED, { exact: true })).toHaveCount(0)
        await capture(page, testInfo, evidence, 'O02-error', 'one-injected-list-503')
        const recovered = waitForApi(page, { path: '/entity-types' })
        await alert.getByRole('button', { name: '重试', exact: true }).click()
        expect((await responseData<Resource[]>(await recovered)).map((item) => item.id)).toContain(
          entityCatalog.published.id,
        )
        await expect(alert).toHaveCount(0)
        await expect(rowFor(page, entityCatalog.published)).toBeVisible()
        await expect(page.getByPlaceholder('搜索', { exact: true })).toHaveValue(
          entityCatalog.published.name,
        )
        await capture(page, testInfo, evidence, 'O02-recovered', 'real-get-after-injected-failure')
      })

      test('test_submit_busy_prevents_duplicate_and_persists', async ({
        signedIn: page,
        entityCatalog,
        identity,
        network,
        evidence,
      }, testInfo) => {
        await openFilteredList(page, entityCatalog.draft)
        await page.getByRole('button', { name: '创建', exact: true }).click()
        const form = drawer(page)
        const name = uniqueName('UiCreated')
        await form.getByPlaceholder('Employee', { exact: true }).fill(name)
        await form
          .locator('.n-form-item')
          .filter({ hasText: '中文标签' })
          .locator('input')
          .fill(name)
        await form
          .locator('.n-form-item')
          .filter({ hasText: '命名空间' })
          .locator('.n-base-selection')
          .click()
        await page
          .locator('.n-base-select-option:visible')
          .filter({ hasText: entityCatalog.namespace.prefix })
          .click()
        const gate = await network.hold({ path: '/entity-types', method: 'POST' })
        try {
          // Naive UI's busy spinner adds "loading" to the accessible button name.
          const save = form.getByRole('button', { name: /^(loading\s+)?保存$/ })
          await save.click()
          await expect.poll(gate.hits).toBe(1)
          await expect(save).toHaveClass(/n-button--loading/)
          await page.keyboard.press('Enter')
          expect(gate.hits()).toBe(1)
          await capture(page, testInfo, evidence, 'O02-submit-busy', 'real-post-held-in-flight')
          const createdResponse = waitForApi(page, { path: '/entity-types', method: 'POST' })
          gate.release()
          const created = await responseData<Resource>(await createdResponse)
          await expect(form).not.toBeVisible()
          const persisted = await getData<Resource>(identity.api, '/entity-types/' + created.id)
          expect(persisted.name).toBe(name)
          expect(persisted.iri).toBe(
            'https://example.org/' + entityCatalog.namespace.prefix + '/' + name,
          )
          const matches = await getData<Resource[]>(identity.api, '/entity-types?q=' + name)
          expect(matches.map((item) => item.id)).toEqual([created.id])
          await openFilteredList(page, persisted)
          expect(gate.hits()).toBe(1)
          await capture(
            page,
            testInfo,
            evidence,
            'O02-created',
            'persisted-real-create-after-delay',
          )
        } finally {
          gate.release()
        }
      })
    })

    test.describe('@entity-types @viewer @real-api', () => {
      test.use({ role: 'VIEWER' })
      test('test_viewer_can_read_but_cannot_write', async ({
        signedIn: page,
        entityCatalog,
        identity,
        evidence,
      }, testInfo) => {
        await openFilteredList(page, entityCatalog.draft)
        await expect(page.getByRole('button', { name: '创建', exact: true })).toBeDisabled()
        await expect(page.getByText(READONLY, { exact: true })).toBeVisible()
        await expect(
          rowFor(page, entityCatalog.draft).getByRole('button', { name: '删除', exact: true }),
        ).toHaveCount(0)
        await capture(page, testInfo, evidence, 'O02-viewer', 'real-viewer-list')
        await rowFor(page, entityCatalog.draft)
          .getByRole('button', { name: '查看', exact: true })
          .click()
        await expect(
          page.getByRole('heading', { name: entityCatalog.draft.label_i18n['zh-CN'], exact: true }),
        ).toBeVisible()
        await expect(page.getByText(READONLY, { exact: true })).toBeVisible()
        await expect(
          page.getByRole('button', { name: /^(编辑|改名|发布|添加属性|删除)$/ }),
        ).toHaveCount(0)
        await page.goto(LIST + '/' + entityCatalog.published.id)
        await expect(page.getByRole('button', { name: '修订下一版', exact: true })).toBeDisabled()
        await capture(page, testInfo, evidence, 'O03-viewer', 'real-viewer-published-details')

        // Independent real backend sample; no /auth/me substitution and no role-store patch.
        const tokens = await responseData<{ access_token: string }>(
          await page.request.post('/api/v1/auth/login', { data: identity.credentials.VIEWER }),
        )
        const denied = await page.request.post('/api/v1/entity-types', {
          headers: { Authorization: 'Bearer ' + tokens.access_token },
          data: {
            name: uniqueName('UiDenied'),
            namespace_id: entityCatalog.namespace.id,
            label_i18n: { 'zh-CN': '不可写入' },
          },
        })
        expect(denied.status()).toBe(403)
        await attachJson(testInfo, 'real-viewer-backend-denial', {
          status: denied.status(),
          code: (await denied.json()).code,
        })
      })

      test('test_viewer_system_routes_are_forbidden', async ({
        signedIn: page,
        evidence,
      }, testInfo) => {
        for (const path of ['/system/users', '/system/roles', '/system/audit-logs']) {
          await page.goto(path)
          await expect(page).toHaveURL(/\/forbidden\?redirect=/)
          expect(new URL(page.url()).searchParams.get('redirect')).toBe(path)
          await expect(page.getByText('无权访问', { exact: true })).toBeVisible()
        }
        await capture(page, testInfo, evidence, 'E01-viewer', 'real-viewer-admin-route-denial')
      })
    })

    test.describe('@entity-types @editor @real-api', () => {
      test.use({ role: 'EDITOR' })
      test('test_editor_has_draft_write_controls', async ({
        signedIn: page,
        entityCatalog,
        evidence,
      }, testInfo) => {
        await openFilteredList(page, entityCatalog.draft)
        await expect(page.getByRole('button', { name: '创建', exact: true })).toBeEnabled()
        await rowFor(page, entityCatalog.draft)
          .getByRole('button', { name: '查看', exact: true })
          .click()
        await expect(page.getByRole('button', { name: '编辑', exact: true })).toBeEnabled()
        await expect(page.getByRole('button', { name: '发布', exact: true })).toBeEnabled()
        await expect(page.getByText(READONLY, { exact: true })).toHaveCount(0)
        await capture(page, testInfo, evidence, 'O03-editor', 'real-editor-draft-controls')
      })
    })
  })
}

test('test_design_matrix_has_37_unique_pages @inventory', () => {
  const ids = [...PUBLIC_ROUTES, ...AUTHENTICATED_ROUTES].map((entry) => entry.id)
  expect(ids).toHaveLength(37)
  expect(new Set(ids).size).toBe(37)
})
