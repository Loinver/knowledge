import type { Page } from '@playwright/test'

import {
  capture,
  expect,
  getData,
  responseData,
  type RouteCatalog,
  settleApi,
  test as base,
  uniqueName,
  waitForApi,
} from './ui-redesign-fixtures'

type StateNames = {
  rule: string
  clause: string
  dictionary: string
  template: string
  taskId: number
}

// Real records in the fixture-owned temporary database, never fabricated success responses.
const test = base.extend<object, { stateNames: StateNames }>({
  stateNames: [
    async ({ identity, routeCatalog }, use) => {
      const api = identity.api
      const names = {
        rule: uniqueName('StateRule'),
        clause: uniqueName('StateClause'),
        dictionary: uniqueName('StateDictionary'),
        template: uniqueName('StateTemplate'),
      }
      async function create(path: string, data: unknown) {
        const response = await api.post(`/api/v1${path}`, { data })
        expect(response.ok(), `${path}: ${await response.text()}`).toBe(true)
        return responseData<{ id: number }>(response)
      }
      await create('/governance/rules', {
        identifier: names.rule,
        name_i18n: { 'zh-CN': names.rule, 'en-US': names.rule },
        category: 'state-regression',
        source_kind: 'ENTERPRISE',
        source_reference: 'Independent UI state regression',
        target_iri: routeCatalog.published.iri,
        severity: 'VIOLATION',
        language: 'SHACL',
        expression: `@prefix sh: <http://www.w3.org/ns/shacl#> .
          <https://example.org/StateShape> a sh:NodeShape ;
            sh:targetClass <${routeCatalog.published.iri}> ;
            sh:property [ sh:path <https://example.org/name> ; sh:minCount 1 ] .`,
        execution: 'MANUAL',
        positive_example: `<https://example.org/Alice> a <${routeCatalog.published.iri}> ; <https://example.org/name> "Alice" .`,
        negative_example: `<https://example.org/Bob> a <${routeCatalog.published.iri}> .`,
      })
      await create('/governance/clauses', {
        standard: names.clause,
        clause_number: '1',
        title_i18n: { 'zh-CN': names.clause, 'en-US': names.clause },
        self_authored_description: {
          'zh-CN': '独立状态测试自编条款',
          'en-US': 'Original test clause',
        },
        appendix_nature: 'INFORMATIVE',
      })
      await create('/governance/enum-dictionaries', {
        name: names.dictionary,
        label_i18n: { 'zh-CN': names.dictionary, 'en-US': names.dictionary },
        definition_i18n: { 'zh-CN': '状态测试词典', 'en-US': 'State test dictionary' },
        entries: [{ value: 'ACTIVE', label_i18n: { 'zh-CN': '有效', 'en-US': 'Active' } }],
      })
      await create('/governance/templates', {
        name: names.template,
        label_i18n: { 'zh-CN': names.template, 'en-US': names.template },
        source: 'Independent state regression',
        basis: 'Original test template',
        resources: [],
      })
      const revision = await getData<{ id: number }>(
        api,
        `/mappings/${routeCatalog.mappingId}/published`,
      )
      expect(revision.id).toBeGreaterThan(0)
      const task = await create('/extraction/tasks', {
        mapping_revision_id: revision.id,
        datasource_id: routeCatalog.datasourceId,
        namespace: routeCatalog.ontology.iri,
        incremental: false,
        run_after: '2099-01-01T00:00:00Z',
      })
      await use({ ...names, taskId: task.id })
    },
    { scope: 'worker' },
  ],
})

type ListCase = {
  id: string
  route: string | ((data: RouteCatalog) => string)
  path: string
  title: string
  empty: string
  witness: (data: RouteCatalog, names: StateNames) => string | RegExp
  create?: string
  readonly?: string | RegExp
  retry?: string
}

const READONLY = '当前角色仅可查看，编辑操作需要编辑者或管理员权限。'
const GOVERNANCE_READONLY =
  '只读模式：可查看内容与冻结版本。新增、修改、删除和实例化需要编辑者或管理员权限。'
const cases: ListCase[] = [
  {
    id: 'ontologies',
    route: '/ontology/ontologies',
    path: '/ontologies',
    title: '本体库',
    empty: '还没有本体。新建一个，或先在「装配模板」里挑一个模板。',
    witness: () => 'UI 验收本体',
    create: '新建本体',
    readonly: READONLY,
  },
  {
    id: 'relations',
    route: '/ontology/relation-types',
    path: '/relations',
    title: '关系类型库',
    empty: '暂无数据',
    witness: () => 'UI 验收关系',
    create: '创建',
    readonly: READONLY,
  },
  {
    id: 'namespaces',
    route: '/ontology/namespaces',
    path: '/namespaces',
    title: '命名空间',
    empty: '还没有登记命名空间。',
    witness: (d) => d.namespace.prefix,
    create: '登记命名空间',
    readonly: READONLY,
  },
  {
    id: 'datasources',
    route: '/datasources',
    path: '/datasources',
    title: '数据源',
    empty: '还没有数据源',
    witness: () => /^UiSource/,
    create: '新建数据源',
    readonly: READONLY,
  },
  {
    id: 'tasks',
    route: '/extraction/tasks',
    path: '/extraction/tasks',
    title: '抽取任务',
    empty: '暂无抽取任务',
    witness: (_, n) => String(n.taskId),
    create: '新建抽取任务',
    readonly: '当前角色仅可查看，配置、生成建议和执行操作需要编辑权限。',
  },
  {
    id: 'runs',
    route: '/extraction/runs',
    path: '/extraction/runs',
    title: '抽取运行',
    empty: '暂无抽取运行记录',
    witness: (d) => `运行 #${d.runId}`,
  },
  {
    id: 'entities',
    route: (d) => `/graph/entities?graph=${d.graphId}`,
    path: '/extraction/entities',
    title: '实体实例',
    empty: '当前视图没有匹配节点，请清除中心实体或调整隐藏类型。',
    witness: (d) => d.entityIri,
  },
  {
    id: 'rules',
    route: '/governance/rules',
    path: '/governance/rules',
    title: '规则库',
    empty: '暂无规则，请新建规则并填写来源依据。',
    witness: (_, n) => n.rule,
    create: '新建规则',
    readonly: '只读模式：可查看规则并测试已保存的版本。新增、修改和删除需要编辑者或管理员权限。',
  },
  {
    id: 'clauses',
    route: '/governance/clauses',
    path: '/governance/clauses',
    title: '标准条款',
    empty: '暂无标准条款',
    witness: (_, n) => n.clause,
    create: '新建条款',
    readonly: GOVERNANCE_READONLY,
  },
  {
    id: 'dictionaries',
    route: '/governance/enum-dictionaries',
    path: '/governance/enum-dictionaries',
    title: '枚举词典',
    empty: '暂无枚举词典',
    witness: (_, n) => n.dictionary,
    create: '新建枚举词典',
    readonly: GOVERNANCE_READONLY,
  },
  {
    id: 'templates',
    route: '/governance/templates',
    path: '/governance/templates',
    title: '装配模板',
    empty: '没有匹配的模板。可调整筛选，或由编辑者创建模板。',
    witness: (_, n) => n.template,
    create: '新建模板',
    readonly: GOVERNANCE_READONLY,
  },
  {
    id: 'users',
    route: '/system/users',
    path: '/users',
    title: '用户管理',
    empty: '暂无数据',
    witness: () => /ui_viewer_/,
  },
  {
    id: 'roles',
    route: '/system/roles',
    path: '/roles',
    title: '角色管理',
    empty: '暂无数据',
    witness: () => 'VIEWER',
  },
  {
    id: 'asset-audit',
    route: '/system/audit-logs',
    path: '/asset-audit-logs',
    title: '操作日志',
    empty: '暂无符合筛选条件的审计记录',
    witness: () => /装配模板 · \d+/,
    retry: '刷新',
  },
  {
    id: 'audit',
    route: '/system/audit-logs',
    path: '/audit-logs',
    title: '操作日志',
    empty: '暂无数据',
    witness: () => '登录',
  },
]

function routeFor(item: ListCase, data: RouteCatalog): string {
  return typeof item.route === 'string' ? item.route : item.route(data)
}

async function openCollection(page: Page, item: ListCase, data: RouteCatalog): Promise<void> {
  await page.goto(routeFor(item, data))
  if (item.id === 'audit') {
    await page.getByText('账号与安全审计', { exact: true }).first().click()
  }
}

function emptyCollection(data: unknown): unknown {
  if (Array.isArray(data)) return []
  expect(data).toEqual(
    expect.objectContaining({ items: expect.any(Array), total: expect.any(Number) }),
  )
  return { ...(data as Record<string, unknown>), items: [], total: 0 }
}

async function expectLoading(page: Page): Promise<void> {
  // Accept an observable spinner or explicit status text; an unfinished HTTP request alone is not feedback.
  await expect(
    page
      .locator('.n-spin-body:visible, .n-base-loading__container:visible, [role="status"]:visible')
      .first(),
  ).toBeVisible()
}

async function expectError(page: Page, retry = '重试'): Promise<void> {
  await expect(
    page
      .locator('.n-alert:visible, [role="alert"]:visible')
      .filter({ hasText: /错误|失败|异常/ })
      .first(),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: retry, exact: true }).first()).toBeEnabled()
}

test.describe('cross-module collection states', () => {
  for (const item of cases) {
    test(`${item.id}: loading releases to real populated content`, async ({
      signedIn: page,
      routeCatalog,
      stateNames,
      network,
      evidence,
    }, info) => {
      const hold = await network.hold({ path: item.path })
      try {
        await openCollection(page, item, routeCatalog)
        await expect(page.getByRole('heading', { name: item.title, exact: true })).toBeVisible()
        await expect.poll(hold.hits).toBeGreaterThan(0)
        await expectLoading(page)
        await capture(page, info, evidence, `${item.id}-loading`, 'loading: real response held')
      } finally {
        hold.release()
      }
      await settleApi(page, evidence)
      await expect(
        page.getByText(item.witness(routeCatalog, stateNames), { exact: true }).first(),
      ).toBeVisible()
      await expect(page.getByRole('button', { name: '重试', exact: true })).toHaveCount(0)
      if (item.create)
        await expect(
          page.getByRole('button', { name: item.create, exact: true }).first(),
        ).toBeEnabled()
      await capture(page, info, evidence, `${item.id}-normal`, 'real-api: populated')
    })

    test(`${item.id}: visible 503 feedback and retry recovers real content`, async ({
      signedIn: page,
      routeCatalog,
      stateNames,
      network,
      evidence,
    }, info) => {
      await network.failOnce({ path: item.path })
      await openCollection(page, item, routeCatalog)
      await expectError(page, item.retry)
      await capture(page, info, evidence, `${item.id}-error`, 'controlled 503: actionable error')
      const response = waitForApi(page, { path: item.path })
      await page
        .getByRole('button', { name: item.retry ?? '重试', exact: true })
        .first()
        .click()
      await responseData(await response)
      await settleApi(page, evidence)
      await expect(
        page.getByText(item.witness(routeCatalog, stateNames), { exact: true }).first(),
      ).toBeVisible()
      await expect(page.getByRole('button', { name: '重试', exact: true })).toHaveCount(0)
      await expect(
        page
          .locator('.n-alert:visible, [role="alert"]:visible')
          // Match the injected failure, not informational copy about failure protection/export scope.
          .filter({ hasText: /服务端内部错误|KG\.INTERNAL_ERROR/ }),
      ).toHaveCount(0)
      await capture(page, info, evidence, `${item.id}-recovered`, 'retry: real-api recovery')
    })

    test(`${item.id}: valid empty response has explicit feedback`, async ({
      signedIn: page,
      identity,
      routeCatalog,
      network,
      evidence,
    }, info) => {
      const query = item.id === 'entities' ? `?graph_revision_id=${routeCatalog.graphId}` : ''
      const baseline = await getData<unknown>(identity.api, item.path + query)
      await network.empty({ path: item.path }, emptyCollection(baseline))
      await openCollection(page, item, routeCatalog)
      await settleApi(page, evidence)
      await expect(page.getByText(item.empty, { exact: true })).toBeVisible()
      expect(evidence.injections[0].hits).toBeGreaterThan(0)
      await expect(page.getByRole('button', { name: '重试', exact: true })).toHaveCount(0)
      await capture(page, info, evidence, `${item.id}-empty`, 'controlled valid empty collection')
    })
  }
})

test.describe('true VIEWER retains reads and cannot edit', () => {
  test.use({ role: 'VIEWER' })
  for (const item of cases.filter((entry) => entry.create)) {
    test(`${item.id}: disabled write and visible explanation`, async ({
      signedIn: page,
      routeCatalog,
      stateNames,
      evidence,
    }, info) => {
      await page.goto(routeFor(item, routeCatalog))
      await settleApi(page, evidence)
      await expect(
        page.getByText(item.witness(routeCatalog, stateNames), { exact: true }).first(),
      ).toBeVisible()
      await expect(
        page.getByRole('button', { name: item.create!, exact: true }).first(),
      ).toBeDisabled()
      await expect(page.getByText(item.readonly!, { exact: true })).toBeVisible()
      await capture(
        page,
        info,
        evidence,
        `${item.id}-viewer`,
        'real VIEWER: reads retained, writes disabled',
      )
    })
  }

  for (const route of ['/system/users', '/system/roles', '/system/audit-logs']) {
    test(`${route}: VIEWER gets access-denied page`, async ({ signedIn: page, evidence }, info) => {
      await page.goto(route)
      await expect(page).toHaveURL(/\/forbidden(?:\?|$)/)
      await expect(page.getByText(/权限/).first()).toBeVisible()
      await expect(page.getByRole('button', { name: /工作台|返回/ }).first()).toBeEnabled()
      await capture(
        page,
        info,
        evidence,
        `${route.split('/').pop()}-forbidden`,
        'real VIEWER: route denied',
      )
    })
  }
})

const catalogRoute = (d: RouteCatalog) => `/datasources/catalog?datasourceId=${d.datasourceId}`
const previewRoute = (d: RouteCatalog) =>
  `/datasources/preview?datasourceId=${d.datasourceId}&schema=main&table=enterprise`
const evidenceRoute = (d: RouteCatalog) =>
  `/graph/evidence?mode=entity&graph=${d.graphId}&iri=${encodeURIComponent(d.entityIri)}`

test('catalog: metadata loading, failure, retry and real table selection', async ({
  signedIn: page,
  routeCatalog: d,
  network,
  evidence,
}, info) => {
  const target = { path: `/datasources/${d.datasourceId}/metadata/latest` }
  await network.failOnce(target)
  const hold = await network.hold(target)
  try {
    await page.goto(catalogRoute(d))
    await expect.poll(hold.hits).toBeGreaterThan(0)
    await expect(page.getByRole('status').filter({ hasText: '正在加载结构快照' })).toBeVisible()
    await expect(page.getByRole('button', { name: '采集结构', exact: true })).toBeDisabled()
    await capture(page, info, evidence, 'catalog-loading', 'metadata loading')
  } finally {
    hold.release()
  }
  await expectError(page)
  await capture(page, info, evidence, 'catalog-error', 'metadata 503')
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await settleApi(page, evidence)
  await page
    .getByRole('button', { name: /enterprise/ })
    .first()
    .click()
  await expect(page.getByRole('heading', { name: 'enterprise', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '采集结构', exact: true })).toBeEnabled()
  await capture(page, info, evidence, 'catalog-recovered', 'real metadata and selected table')
})

for (const screen of ['catalog', 'preview'] as const) {
  test(`${screen}: no datasources explains unavailable actions`, async ({
    signedIn: page,
    network,
    evidence,
  }, info) => {
    await network.empty({ path: '/datasources' }, [])
    await page.goto(screen === 'catalog' ? '/datasources/catalog' : '/datasources/preview')
    await settleApi(page, evidence)
    await expect(
      page.getByText(screen === 'catalog' ? '还没有数据源' : '还没有数据源。', { exact: true }),
    ).toBeVisible()
    await expect(
      page.getByRole('button', { name: screen === 'catalog' ? '采集结构' : '预览', exact: true }),
    ).toBeDisabled()
    await capture(
      page,
      info,
      evidence,
      `${screen}-no-source`,
      'empty source selection: action disabled',
    )
  })
}

test('preview: loading, duplicate prevention, error and retry to real rows', async ({
  signedIn: page,
  routeCatalog: d,
  network,
  evidence,
}, info) => {
  await page.goto(previewRoute(d))
  await settleApi(page, evidence)
  const target = { path: '/datasources/preview', method: 'POST' }
  await network.failOnce(target)
  const hold = await network.hold(target)
  try {
    await page.getByRole('button', { name: '预览', exact: true }).click()
    await expect.poll(hold.hits).toBe(1)
    await expectLoading(page)
    await expect(page.getByRole('button', { name: /^(?:loading )?预览$/ })).toBeDisabled()
    await capture(page, info, evidence, 'preview-loading', 'read-only preview pending')
  } finally {
    hold.release()
  }
  await expectError(page)
  await expect(page.getByText('预览失败，请重试。', { exact: true })).toBeVisible()
  await capture(page, info, evidence, 'preview-error', 'preview 503, selection retained')
  const next = waitForApi(page, target)
  await page.getByRole('button', { name: '重试', exact: true }).click()
  const data = await responseData<{ total_returned: number; rows: unknown[] }>(await next)
  expect(data.total_returned).toBeGreaterThan(0)
  await settleApi(page, evidence)
  await expect(page.locator('.result-range')).toHaveText(`第 1–${data.total_returned} 行`)
  await expect(page.locator('.result-range')).toBeVisible()
  await expect(page.locator('.n-data-table-tbody tr')).toHaveCount(data.total_returned)
  await expect(page.getByRole('button', { name: '上一页', exact: true })).toBeDisabled()
  await capture(
    page,
    info,
    evidence,
    'preview-recovered',
    'real source rows and first-page boundary',
  )
})

test('preview: valid zero-row result', async ({
  signedIn: page,
  identity,
  routeCatalog: d,
  network,
  evidence,
}, info) => {
  const real = await responseData<Record<string, unknown>>(
    await identity.api.post('/api/v1/datasources/preview', {
      data: {
        datasource_id: d.datasourceId,
        schema: 'main',
        table: 'enterprise',
        limit: 20,
        offset: 0,
      },
    }),
  )
  await network.empty(
    { path: '/datasources/preview', method: 'POST' },
    { ...real, rows: [], total_returned: 0, truncated: false },
  )
  await page.goto(previewRoute(d))
  await settleApi(page, evidence)
  await page.getByRole('button', { name: '预览', exact: true }).click()
  await expect(page.getByText('没有返回样例行。', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '下一页', exact: true })).toBeDisabled()
  await capture(page, info, evidence, 'preview-empty', 'valid zero-row preview')
})

test('evidence: loading, 503 and retry retains provenance context', async ({
  signedIn: page,
  routeCatalog: d,
  network,
  evidence,
}, info) => {
  const target = { path: '/extraction/evidence/trace/entity' }
  await network.failOnce(target)
  const hold = await network.hold(target)
  try {
    await page.goto(evidenceRoute(d))
    await expect.poll(hold.hits).toBeGreaterThan(0)
    await expect(page.getByRole('status').filter({ hasText: '加载中…' }).first()).toBeVisible()
    await capture(page, info, evidence, 'evidence-loading', 'entity trace pending')
  } finally {
    hold.release()
  }
  await expectError(page)
  await capture(page, info, evidence, 'evidence-error', 'entity trace 503')
  const next = waitForApi(page, target)
  await page.getByRole('button', { name: '重试', exact: true }).click()
  const data = await responseData<{ total_count: number }>(await next)
  expect(data.total_count).toBeGreaterThan(0)
  await settleApi(page, evidence)
  await expect(
    page.getByText(`结果集 #${d.graphId} · 共 ${data.total_count} 条证据`, { exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('cell', { name: 'enterprise', exact: true }).first()).toBeVisible()
  await capture(page, info, evidence, 'evidence-recovered', 'real source table evidence')
})

test('evidence: no provenance is explicitly incomplete', async ({
  signedIn: page,
  identity,
  routeCatalog: d,
  network,
  evidence,
}, info) => {
  const real = await getData<Record<string, unknown>>(
    identity.api,
    `/extraction/evidence/trace/entity?graph_revision_id=${d.graphId}&iri=${encodeURIComponent(d.entityIri)}`,
  )
  await network.empty(
    { path: '/extraction/evidence/trace/entity' },
    { ...real, evidences: [], total_count: 0, quarantined_count: 0 },
  )
  await page.goto(evidenceRoute(d))
  await settleApi(page, evidence)
  await expect(
    page.getByText('没有来源证据，不能认定该事实已具备完整追溯链。', { exact: true }),
  ).toBeVisible()
  await capture(page, info, evidence, 'evidence-empty', 'empty evidence is not complete provenance')
})

test('reports: loading, 503 retry, prerequisites and real validation', async ({
  signedIn: page,
  routeCatalog: d,
  network,
  evidence,
}, info) => {
  const target = { path: '/extraction/graph/revisions' }
  await network.failOnce(target)
  const hold = await network.hold(target)
  try {
    await page.goto('/graph/reports')
    await expect.poll(hold.hits).toBeGreaterThan(0)
    await expectLoading(page)
    await expect(page.getByRole('button', { name: '运行实例校验', exact: true })).toBeDisabled()
    await capture(page, info, evidence, 'reports-loading', 'revision selection pending')
  } finally {
    hold.release()
  }
  await expectError(page)
  await capture(page, info, evidence, 'reports-error', 'revision list 503')
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await settleApi(page, evidence)
  await expect(page.getByText('请选择图谱版本后运行校验', { exact: true })).toBeVisible()
  await page.locator('.n-select').first().click()
  await page.getByText(new RegExp(`^#${d.graphId}(?: \\(当前结果集\\))?$`)).click()
  const completed = waitForApi(page, { path: `/validation/graph/${d.graphId}`, method: 'POST' })
  await page.getByRole('button', { name: '运行实例校验', exact: true }).click()
  const report = await responseData<{
    summary: { pass: number; violation: number; na: number; not_run: number }
  }>(await completed)
  await settleApi(page, evidence)
  await expect(page.getByText('请选择图谱版本后运行校验', { exact: true })).toHaveCount(0)
  expect(Object.keys(report.summary).sort()).toEqual(['na', 'not_run', 'pass', 'violation'])
  for (const [label, key] of [
    ['通过', 'pass'],
    ['违反', 'violation'],
    ['不适用', 'na'],
    ['未执行', 'not_run'],
  ] as const) {
    const statistic = page.locator('.n-statistic').filter({ hasText: label })
    await expect(statistic).toBeVisible()
    await expect(statistic.locator('.n-statistic-value')).toHaveText(String(report.summary[key]))
  }
  await capture(page, info, evidence, 'reports-real', 'real validation: four states retained')
})

test('reports: empty result sets keep validation disabled', async ({
  signedIn: page,
  network,
  evidence,
}, info) => {
  await network.empty({ path: '/extraction/graph/revisions' }, [])
  await page.goto('/graph/reports')
  await settleApi(page, evidence)
  await expect(page.getByText('请选择图谱版本后运行校验', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '运行实例校验', exact: true })).toBeDisabled()
  await capture(page, info, evidence, 'reports-empty', 'no result sets: validation unavailable')
})

test.describe('VIEWER special pages and own profile', () => {
  test.use({ role: 'VIEWER' })
  test('catalog, preview, entities, evidence, runs and reports preserve read access', async ({
    signedIn: page,
    routeCatalog: d,
    evidence,
  }, info) => {
    await page.goto(catalogRoute(d))
    await settleApi(page, evidence)
    await expect(page.getByRole('button', { name: '采集结构', exact: true })).toBeDisabled()
    await expect(page.getByRole('button', { name: /enterprise/ }).first()).toBeVisible()
    await capture(page, info, evidence, 'catalog-viewer', 'real VIEWER reads metadata')
    await page.goto(previewRoute(d))
    await settleApi(page, evidence)
    await expect(page.getByRole('button', { name: '重新采集元数据', exact: true })).toBeDisabled()
    await expect(page.getByRole('button', { name: '预览', exact: true })).toBeEnabled()
    await page.getByRole('button', { name: '预览', exact: true }).click()
    await settleApi(page, evidence)
    expect(await page.getByRole('row').count()).toBeGreaterThan(1)
    await capture(page, info, evidence, 'preview-viewer', 'real VIEWER can run read-only preview')
    for (const item of cases.filter((entry) => ['entities', 'runs'].includes(entry.id))) {
      await page.goto(routeFor(item, d))
      await settleApi(page, evidence)
      await expect(
        page.getByText(item.witness(d, {} as StateNames), { exact: true }).first(),
      ).toBeVisible()
      await capture(page, info, evidence, `${item.id}-viewer`, 'real VIEWER read access')
    }
    await page.goto(evidenceRoute(d))
    await settleApi(page, evidence)
    await expect(page.getByRole('cell', { name: 'enterprise', exact: true }).first()).toBeVisible()
    await capture(page, info, evidence, 'evidence-viewer', 'real VIEWER provenance')
    await page.goto('/graph/reports')
    await settleApi(page, evidence)
    await page.locator('.n-select').first().click()
    await page.getByText(new RegExp(`^#${d.graphId}(?: \\(当前结果集\\))?$`)).click()
    await expect(page.getByRole('button', { name: '运行实例校验', exact: true })).toBeDisabled()
    await expect(page.getByText(READONLY, { exact: true })).toBeVisible()
    await capture(
      page,
      info,
      evidence,
      'reports-viewer',
      'selected graph: VIEWER validation disabled',
    )
  })

  test('profile: own edit allowed, cancel, pending, error and real save retry', async ({
    signedIn: page,
    identity,
    network,
    evidence,
  }, info) => {
    await page.goto('/account/profile')
    await settleApi(page, evidence)
    const name = page.getByPlaceholder(identity.credentials.VIEWER.account, { exact: true })
    const original = await name.inputValue()
    await name.fill('Unsaved profile state')
    await page.getByRole('button', { name: '取消', exact: true }).click()
    await expect(name).toHaveValue(original)
    await name.fill('Viewer state verification')
    const target = { path: '/users/me/profile', method: 'PATCH' }
    await network.failOnce(target)
    const hold = await network.hold(target)
    try {
      await page.getByRole('button', { name: '保存', exact: true }).click()
      await expect.poll(hold.hits).toBe(1)
      await expectLoading(page)
      await expect(page.getByRole('button', { name: '取消', exact: true })).toBeDisabled()
      await capture(page, info, evidence, 'profile-saving', 'VIEWER owns profile: save pending')
    } finally {
      hold.release()
    }
    await expect(page.getByRole('alert').filter({ hasText: /错误|失败|异常/ })).toBeVisible()
    await expect(name).toHaveValue('Viewer state verification')
    await capture(page, info, evidence, 'profile-error', 'save failure retains draft')
    const saved = waitForApi(page, target)
    await page.getByRole('button', { name: '保存', exact: true }).click()
    const user = await responseData<{ role: string; display_name: string }>(await saved)
    expect(user).toMatchObject({ role: 'VIEWER', display_name: 'Viewer state verification' })
    await expect(page.getByText('资料已保存', { exact: true })).toBeVisible()
    await page.reload()
    await settleApi(page, evidence)
    await expect(name).toHaveValue('Viewer state verification')
    await capture(page, info, evidence, 'profile-saved', 'real save survives reload')
    await name.fill(original)
    const restored = waitForApi(page, target)
    await page.getByRole('button', { name: '保存', exact: true }).click()
    await responseData(await restored)
  })
})

test('auth login: required input, loading, 503, preserved credentials and real retry', async ({
  page,
  identity,
  network,
  evidence,
}, info) => {
  await page.goto('/login')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByText('请输入账号或邮箱', { exact: true })).toBeVisible()
  await expect(
    page.locator('.n-form-item-feedback').getByText('请输入密码', { exact: true }),
  ).toBeVisible()
  await page
    .getByPlaceholder('用户名或邮箱', { exact: true })
    .fill(identity.credentials.VIEWER.account)
  await page
    .getByPlaceholder('请输入密码', { exact: true })
    .fill(identity.credentials.VIEWER.password)
  const target = { path: '/auth/login', method: 'POST' }
  await network.failOnce(target)
  const hold = await network.hold(target)
  try {
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect.poll(hold.hits).toBe(1)
    await expectLoading(page)
    await capture(page, info, evidence, 'login-loading', 'login pending')
  } finally {
    hold.release()
  }
  await expect(page.getByRole('alert').filter({ hasText: /错误|失败|异常/ })).toBeVisible()
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByPlaceholder('用户名或邮箱', { exact: true })).toHaveValue(
    identity.credentials.VIEWER.account,
  )
  await capture(page, info, evidence, 'login-error', '503 retains credentials for retry')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '工作台', exact: true })).toBeVisible()
  await settleApi(page, evidence)
  await capture(page, info, evidence, 'login-recovered', 'real VIEWER session after retry')
})

for (const screen of ['register', 'forgot-password'] as const) {
  test(`auth ${screen}: config loading, visible failure and retry to real capability`, async ({
    page,
    network,
    evidence,
  }, info) => {
    const target = { path: '/auth/config' }
    await network.failOnce(target)
    const hold = await network.hold(target)
    try {
      await page.goto(`/${screen}`)
      await expect.poll(hold.hits).toBeGreaterThan(0)
      await expect(page.getByRole('status').filter({ hasText: '加载中…' })).toBeVisible()
      await capture(page, info, evidence, `${screen}-loading`, 'auth capability loading')
    } finally {
      hold.release()
    }
    await expectError(page)
    await capture(page, info, evidence, `${screen}-error`, 'auth config 503: actionable retry')
    const recovered = waitForApi(page, target)
    await page.getByRole('button', { name: '重试', exact: true }).click()
    const config = await responseData<{
      registration_enabled: boolean
      password_reset_enabled: boolean
    }>(await recovered)
    await settleApi(page, evidence)
    if (screen === 'register') {
      expect(config.registration_enabled).toBe(true)
      await expect(page.getByRole('button', { name: '注册', exact: true })).toBeEnabled()
      await page.getByRole('button', { name: '注册', exact: true }).click()
      await expect(page.getByText('请输入用户名', { exact: true })).toBeVisible()
      await expect(page.getByText('请输入邮箱', { exact: true })).toBeVisible()
    } else {
      expect(config.password_reset_enabled).toBe(false)
      await expect(
        page.getByRole('alert').filter({
          hasText:
            '本平台未开放自助找回密码。请联系管理员在「系统管理 → 用户管理」中为你生成一次性重置链接。',
        }),
      ).toBeVisible()
      await expect(page.getByRole('button', { name: '发送重置链接', exact: true })).toHaveCount(0)
    }
    await capture(
      page,
      info,
      evidence,
      `${screen}-recovered`,
      'real configured capability after retry',
    )
  })
}

test('auth reset: missing token explains disabled submit without request', async ({
  page,
  evidence,
}, info) => {
  await page.goto('/reset-password')
  await expect(
    page.getByRole('alert').filter({ hasText: '链接缺少重置凭据，请使用收到的完整重置链接进入。' }),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: '确认重置', exact: true })).toBeDisabled()
  expect(
    evidence.responses.filter((entry) => entry.path === '/api/v1/auth/reset-password'),
  ).toEqual([])
  await capture(
    page,
    info,
    evidence,
    'reset-missing-token',
    'no token: explicit warning and disabled submit',
  )
})
