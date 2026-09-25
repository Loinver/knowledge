import { execFileSync } from 'node:child_process'
import { copyFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { expect, test, type APIRequestContext, type APIResponse, type Page } from '@playwright/test'

type ApiEnvelope<T> = { code?: string; data?: T }
type EntityOut = { id: number; iri: string; name: string }
type RelationOut = { id: number; name: string }
type Brief = { id: number; name: string; status: string; current_revision: number }
type RunOut = {
  id: number
  status: string
  fingerprint: string | null
  counts: Record<string, number>
}
type GraphRevision = { id: number; run_id: number; is_current: boolean }
type EntityIdentity = { iri: string; type_iri: string; row_key: string }
type GraphTriple = { subject: string; predicate: string; object_: string }
type Quarantine = { table_name: string; row_key: string; field: string; raw_value: string | null }
type RelationSpec = {
  name: string
  label: string
  domain: string
  range: string
  attributes?: Array<{ name: string; datatype: string; nullable: boolean }>
}

let apiHeaders: Record<string, string> = {}

async function responseData<T>(response: APIResponse): Promise<T> {
  const body = (await response.json()) as ApiEnvelope<T> | T
  const errorDetail =
    typeof body === 'object' && body !== null && 'code' in body
      ? JSON.stringify({ code: body.code, params: 'params' in body ? body.params : undefined })
      : ''
  expect(
    response.ok(),
    'API request returned HTTP ' + response.status() + ' ' + errorDetail,
  ).toBeTruthy()
  if (typeof body === 'object' && body !== null && 'code' in body) {
    const envelope = body as ApiEnvelope<T>
    expect(envelope.code, 'API response must be successful').toBe('KG.OK')
    return envelope.data as T
  }
  return body as T
}

async function getData<T>(request: APIRequestContext, path: string): Promise<T> {
  return responseData<T>(await request.get('/api/v1' + path, { headers: apiHeaders }))
}

async function postData<T>(
  request: APIRequestContext,
  path: string,
  payload?: unknown,
): Promise<T> {
  const response = await request.post(
    '/api/v1' + path,
    payload === undefined ? { headers: apiHeaders } : { data: payload, headers: apiHeaders },
  )
  return responseData<T>(response)
}

async function seedOntology(request: APIRequestContext) {
  const namespace = await postData<{ id: number }>(request, '/namespaces', {
    prefix: 'e2e',
    iri: 'https://example.org/e2e/',
    protected: false,
    label_i18n: { 'zh-CN': '端到端验收', 'en-US': 'E2E acceptance' },
  })

  const entitySpecs = [
    { name: 'E2EEmployee', label: '员工', properties: ['name', 'hireDate'] },
    { name: 'E2EEnterprise', label: '企业', properties: ['name'] },
    { name: 'E2EProject', label: '项目', properties: ['name'] },
    { name: 'E2EContract', label: '合同', properties: ['title'] },
  ]
  const entityTypes: Record<string, EntityOut> = {}
  for (const spec of entitySpecs) {
    const entity = await postData<EntityOut>(request, '/entity-types', {
      name: spec.name,
      namespace_id: namespace.id,
      label_i18n: { 'zh-CN': spec.label, 'en-US': spec.name },
      data_props: spec.properties.map((name) => ({
        name,
        datatype: name === 'hireDate' ? 'date' : 'string',
        nullable: false,
        label_i18n: { 'zh-CN': name, 'en-US': name },
      })),
    })
    await postData(request, '/entity-types/' + entity.id + '/publish')
    entityTypes[spec.name] = entity
  }

  const relationSpecs: RelationSpec[] = [
    { name: 'E2EWorksFor', label: '就职于', domain: 'E2EEmployee', range: 'E2EEnterprise' },
    {
      name: 'E2EContractProject',
      label: '合同关联项目',
      domain: 'E2EContract',
      range: 'E2EProject',
    },
    {
      name: 'E2EProjectParticipation',
      label: '项目参与',
      domain: 'E2EProject',
      range: 'E2EEmployee',
      attributes: [{ name: 'role', datatype: 'string', nullable: false }],
    },
  ]
  const relationTypes: RelationOut[] = []
  for (const spec of relationSpecs) {
    const relation = await postData<RelationOut>(request, '/relations', {
      name: spec.name,
      namespace_id: namespace.id,
      label_i18n: { 'zh-CN': spec.label, 'en-US': spec.name },
      domain_spec: { type_id: entityTypes[spec.domain].id },
      range_spec: { type_id: entityTypes[spec.range].id },
      enable_attributes: Boolean(spec.attributes),
      attribute_defs: spec.attributes ?? [],
    })
    await postData(request, '/relations/' + relation.id + '/publish')
    relationTypes.push(relation)
  }

  const memberIds = [
    ...Object.values(entityTypes).map((item) => item.id),
    ...relationTypes.map((item) => item.id),
  ]
  const domain = await postData<{ id: number }>(request, '/domains', {
    name: 'E2EBusinessDomain',
    iri: 'https://example.org/e2e/domain#operations',
    label_i18n: { 'zh-CN': '端到端业务域', 'en-US': 'E2E business domain' },
    member_ids: memberIds,
  })
  await postData(request, '/domains/' + domain.id + '/publish')

  const ontology = await postData<{ id: number }>(request, '/ontologies', {
    name: 'E2EOntology',
    iri: 'https://example.org/e2e/graph/',
    label_i18n: { 'zh-CN': '端到端本体', 'en-US': 'E2E ontology' },
    ref_resource_ids: memberIds,
  })
  await postData(request, '/ontologies/' + ontology.id + '/publish')
  return { ontologyId: ontology.id, entityTypes }
}

function field(target_attr: string, source_field: string, transform = 'IDENTITY') {
  return {
    target_attr,
    source_field,
    transform,
    transform_params: null,
    null_policy: 'REQUIRED',
    default_value: null,
  }
}

async function seedMapping(request: APIRequestContext, ontologyId: number): Promise<Brief> {
  return postData<Brief>(request, '/mappings', {
    name: 'E2EMainFlowMapping',
    ontology_id: ontologyId,
    draft: {
      entity_maps: [
        {
          entity_type: 'E2EEmployee',
          table: 'hr_employee',
          schema: 'main',
          field_maps: [field('name', 'name'), field('hireDate', 'hire_date', 'DATE')],
          key_fields: ['id'],
        },
        {
          entity_type: 'E2EEnterprise',
          table: 'enterprise',
          schema: 'main',
          field_maps: [field('name', 'name')],
          key_fields: ['id'],
        },
        {
          entity_type: 'E2EProject',
          table: 'pm_project',
          schema: 'main',
          field_maps: [field('name', 'name')],
          key_fields: ['id'],
        },
        {
          entity_type: 'E2EContract',
          table: 'ct_contract',
          schema: 'main',
          field_maps: [field('title', 'title')],
          key_fields: ['id'],
        },
      ],
      rel_maps: [
        {
          relation_type: 'E2EWorksFor',
          mode: 'FK',
          table: 'hr_employee',
          schema: 'main',
          fk_field: 'enterprise_id',
          source: null,
          target: null,
          attributes: [],
        },
        {
          relation_type: 'E2EContractProject',
          mode: 'JUNCTION',
          table: 'ct_contract_project',
          schema: 'main',
          fk_field: null,
          source: { field: 'contract_id', ref_table: 'ct_contract', ref_field: 'id' },
          target: { field: 'project_id', ref_table: 'pm_project', ref_field: 'id' },
          attributes: [],
        },
        {
          relation_type: 'E2EProjectParticipation',
          mode: 'ASSOCIATIVE',
          table: 'pm_project_member',
          schema: 'main',
          fk_field: null,
          source: { field: 'project_id', ref_table: 'pm_project', ref_field: 'id' },
          target: { field: 'member_id', ref_table: 'hr_employee', ref_field: 'id' },
          attributes: [{ attr: 'role', field: 'role' }],
        },
      ],
    },
  })
}

async function createSourceThroughUI(page: Page, sourcePath: string): Promise<number> {
  await page.goto('/datasources')
  await page.getByRole('button', { name: '新建数据源' }).click()
  const modal = page.locator('.source-modal')
  await modal.getByLabel('名称').fill('E2E 样例源')
  await modal.getByLabel('数据库').fill(sourcePath)
  await modal.getByRole('button', { name: '测试连接' }).click()
  await expect(modal.getByText(/发现 6 张表/)).toBeVisible()
  await modal.getByRole('button', { name: '保存' }).click()
  await expect(modal).not.toBeVisible()
  await expect(page.getByText('E2E 样例源', { exact: true })).toBeVisible()

  const sources = await getData<Array<{ id: number; name: string }>>(page.request, '/datasources')
  const source = sources.find((item) => item.name === 'E2E 样例源')
  expect(source, 'source created through the UI').toBeTruthy()
  return source!.id
}

async function captureCatalogThroughUI(page: Page, datasourceId: number): Promise<void> {
  await page.goto('/datasources/catalog?datasourceId=' + datasourceId)
  await expect(page.getByRole('heading', { name: '数据目录' })).toBeVisible()
  await page.getByRole('button', { name: '采集结构' }).first().click()
  for (const table of [
    'enterprise',
    'hr_employee',
    'ct_contract',
    'ct_contract_project',
    'pm_project',
    'pm_project_member',
  ]) {
    await expect(page.locator('.table-name').filter({ hasText: table }).first()).toBeVisible()
  }
}

async function chooseMappingAndRunThroughUI(page: Page, mappingName: string): Promise<void> {
  await page.goto('/extraction')
  await expect(page.getByRole('heading', { name: '映射向导' })).toBeVisible()

  const stepOne = page.locator('.step-content')
  await stepOne.locator('input').first().fill('E2E browser mapping')
  await stepOne.locator('.n-base-selection').first().click()
  await page.getByText('端到端本体 · E2EOntology', { exact: true }).click()
  await page.locator('.wizard-footer').getByRole('button', { name: '下一步' }).click()

  const sourceSelect = page.locator('.datasource-form .n-base-selection').first()
  await sourceSelect.click()
  await page.getByText('E2E 样例源 · sqlite', { exact: true }).click()
  await expect(page.locator('.catalog-summary')).toContainText('6')

  await page.locator('.mapping-picker .n-base-selection').click()
  await page.getByText(mappingName + ' · 草稿', { exact: true }).click()
  await expect(page.locator('.wizard-step.active')).toContainText('映射设计')
  await page.locator('.wizard-footer').getByRole('button', { name: '保存并预览' }).click()
  await expect(page.getByText('当前样例没有发现字段错误。')).toBeVisible()

  await page.locator('.wizard-footer').getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '发布映射' }).click()
  await expect(page.getByText(/映射 rev\./)).toBeVisible()
  await page.getByRole('button', { name: '启动抽取' }).click()
  await expect(page.getByText(/运行编号 #/)).toBeVisible()
}

function mutateCopiedSource(sourcePath: string, sql: string, ...values: string[]): void {
  const python = resolve('server/.venv/bin/python')
  const script =
    'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); sql=sys.argv[2]; args=sys.argv[3:]; c.executescript(sql) if not args else c.execute(sql,args); c.commit(); c.close()'
  execFileSync(python, ['-c', script, sourcePath, sql, ...values], { stdio: 'pipe' })
}

test('M3 browser flow, failure protection and responsive route smoke', async ({
  page,
  request,
}) => {
  const tempDir = process.env.KG_E2E_TEMP_DIR
  expect(tempDir, 'Playwright config provides an isolated temp directory').toBeTruthy()
  const sourcePath = join(tempDir!, 'enterprise-demo-copy.sqlite')
  copyFileSync(resolve('samples/enterprise_demo.sqlite'), sourcePath)
  execFileSync(
    resolve('server/.venv/bin/python'),
    [
      resolve('scripts/seed_admin.py'),
      '--username',
      'e2e_admin',
      '--email',
      'e2e_admin@example.org',
      '--password',
      'E2E-Admin-Password-2026!',
    ],
    {
      cwd: resolve('server'),
      env: {
        ...process.env,
        KG_ENVIRONMENT: 'development',
        KG_DATABASE_URL: 'sqlite:///' + join(tempDir!, 'metadata.sqlite'),
        KG_PASSWORD_ITERATIONS: '1000',
      },
      stdio: 'pipe',
      timeout: 30_000,
    },
  )
  const pageErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))

  await page.goto('/register')
  await page.getByLabel('用户名').fill('e2e_' + Date.now())
  await page.getByLabel('邮箱').fill('e2e_' + Date.now() + '@example.org')
  await page.getByLabel('密码', { exact: true }).fill('E2E-Password-2026!')
  await page.getByLabel('确认密码').fill('E2E-Password-2026!')
  await page.getByRole('button', { name: '注册', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)

  const accessToken = await page.evaluate(() => localStorage.getItem('kg-access-token'))
  expect(accessToken, 'registration created an authenticated API session').toBeTruthy()
  apiHeaders = { Authorization: 'Bearer ' + accessToken }
  const registeredUser = await getData<{ id: string; role: string }>(request, '/auth/me')
  expect(registeredUser.role).toBe('VIEWER')
  const denied = await request.post('/api/v1/namespaces', {
    headers: apiHeaders,
    data: { prefix: 'forbidden', iri: 'https://example.org/forbidden/' },
  })
  expect(denied.status()).toBe(403)
  const administrator = await responseData<{ access_token: string }>(
    await request.post('/api/v1/auth/login', {
      data: { account: 'e2e_admin', password: 'E2E-Admin-Password-2026!' },
    }),
  )
  await responseData(
    await request.patch('/api/v1/users/' + registeredUser.id, {
      headers: { Authorization: 'Bearer ' + administrator.access_token },
      data: { role: 'EDITOR' },
    }),
  )
  await page.reload()

  const ontology = await seedOntology(request)
  const datasourceId = await createSourceThroughUI(page, sourcePath)
  await captureCatalogThroughUI(page, datasourceId)
  const mapping = await seedMapping(request, ontology.ontologyId)
  await chooseMappingAndRunThroughUI(page, mapping.name)

  const runs = await getData<RunOut[]>(request, '/extraction/runs?page=1&page_size=20')
  const firstRun = runs[0]
  expect(firstRun?.status).toBe('SUCCESS')
  expect(firstRun?.counts.entity_count).toBeGreaterThan(0)
  expect(firstRun?.counts.triple_count).toBeGreaterThan(0)

  const firstGraph = await getData<GraphRevision | null>(request, '/extraction/graph/current')
  expect(firstGraph).toBeTruthy()
  const firstEntities = await getData<EntityIdentity[]>(
    request,
    '/extraction/graph/' + firstGraph!.id + '/entities?page=1&page_size=200',
  )
  const firstTriples = await getData<GraphTriple[]>(
    request,
    '/extraction/graph/' + firstGraph!.id + '/triples?page=1&page_size=200',
  )
  const firstIris = firstEntities.map((entity) => entity.iri).sort()
  const firstFacts = firstTriples
    .map((fact) => fact.subject + '\u0000' + fact.predicate + '\u0000' + fact.object_)
    .sort()

  const published = await getData<{ id: number }>(request, '/mappings/' + mapping.id + '/published')
  const repeated = await postData<{ run: RunOut; graph_revision: GraphRevision }>(
    request,
    '/extraction/runs',
    {
      mapping_revision_id: published.id,
      datasource_id: datasourceId,
      namespace: 'https://example.org/e2e/graph/',
    },
  )
  expect(repeated.run.status).toBe('SUCCESS')
  expect(repeated.run.fingerprint).toBe(firstRun.fingerprint)
  const repeatedEntities = await getData<EntityIdentity[]>(
    request,
    '/extraction/graph/' + repeated.graph_revision.id + '/entities?page=1&page_size=200',
  )
  const repeatedTriples = await getData<GraphTriple[]>(
    request,
    '/extraction/graph/' + repeated.graph_revision.id + '/triples?page=1&page_size=200',
  )
  expect(repeatedEntities.map((entity) => entity.iri).sort()).toEqual(firstIris)
  expect(
    repeatedTriples
      .map((fact) => fact.subject + '\u0000' + fact.predicate + '\u0000' + fact.object_)
      .sort(),
  ).toEqual(firstFacts)

  mutateCopiedSource(
    sourcePath,
    'UPDATE hr_employee SET hire_date = ? WHERE id = ?',
    'invalid-date',
    '8001',
  )
  const partial = await postData<{ run: RunOut; graph_revision: GraphRevision }>(
    request,
    '/extraction/runs',
    {
      mapping_revision_id: published.id,
      datasource_id: datasourceId,
      namespace: 'https://example.org/e2e/graph/',
    },
  )
  expect(partial.run.status).toBe('PARTIAL')
  expect(partial.run.counts.quarantine_count).toBeGreaterThan(0)
  const quarantine = await getData<Quarantine[]>(
    request,
    '/extraction/runs/' + partial.run.id + '/quarantine',
  )
  expect(
    quarantine.some((item) => item.table_name === 'hr_employee' && item.field === 'hire_date'),
  ).toBe(true)

  const employee = firstEntities.find((entity) => entity.type_iri.endsWith('/E2EEmployee'))
  expect(employee).toBeTruthy()
  const evidence = await getData<{ evidences: Array<{ table_name: string; run_id: number }> }>(
    request,
    '/extraction/evidence/trace/entity?iri=' +
      encodeURIComponent(employee!.iri) +
      '&graph_revision_id=' +
      firstGraph!.id,
  )
  expect(evidence.evidences.some((item) => item.table_name === 'hr_employee')).toBe(true)

  const partialCurrent = await getData<GraphRevision | null>(request, '/extraction/graph/current')
  expect(partialCurrent?.id).toBe(partial.graph_revision.id)
  mutateCopiedSource(
    sourcePath,
    'DELETE FROM pm_project_member; DELETE FROM ct_contract_project; DELETE FROM hr_employee; DELETE FROM enterprise; DELETE FROM ct_contract; DELETE FROM pm_project',
  )
  const failed = await postData<{ run: RunOut }>(request, '/extraction/runs', {
    mapping_revision_id: published.id,
    datasource_id: datasourceId,
    namespace: 'https://example.org/e2e/graph/',
  })
  expect(failed.run.status).toBe('FAILED')
  const currentAfterFailure = await getData<GraphRevision | null>(
    request,
    '/extraction/graph/current',
  )
  expect(currentAfterFailure?.id).toBe(partialCurrent?.id)

  await page.goto('/graph/entities?graph=' + partial.graph_revision.id)
  await expect(page.getByText('E2EEmployee', { exact: false }).first()).toBeVisible()
  await page.goto(
    '/graph/evidence?mode=entity&graph=' +
      firstGraph!.id +
      '&iri=' +
      encodeURIComponent(employee!.iri),
  )
  await expect(page.getByRole('cell', { name: 'hr_employee' }).first()).toBeVisible()

  const routes = [
    { path: '/', pageHeader: true },
    { path: '/ontology/entity-types', pageHeader: true },
    { path: '/ontology/entity-types/' + ontology.entityTypes.E2EEmployee.id, pageHeader: true },
    { path: '/ontology/relation-types', pageHeader: true },
    { path: '/ontology/domains', pageHeader: true },
    { path: '/ontology/designer', pageHeader: false },
    { path: '/datasources', pageHeader: true },
    { path: '/datasources/catalog?datasourceId=' + datasourceId, pageHeader: true },
    {
      path: '/datasources/preview?datasourceId=' + datasourceId + '&schema=main&table=hr_employee',
      pageHeader: true,
    },
    { path: '/extraction', pageHeader: true },
    { path: '/extraction/runs', pageHeader: true },
    { path: '/graph?graph=' + partial.graph_revision.id, pageHeader: true },
    { path: '/graph/entities?graph=' + partial.graph_revision.id, pageHeader: true },
    {
      path: '/graph/entities/' + encodeURIComponent(employee!.iri) + '?graph=' + firstGraph!.id,
      pageHeader: true,
    },
    {
      path:
        '/graph/evidence?mode=entity&graph=' +
        firstGraph!.id +
        '&iri=' +
        encodeURIComponent(employee!.iri),
      pageHeader: true,
    },
    { path: '/graph/reports', pageHeader: true },
    { path: '/governance/rules', pageHeader: true },
    { path: '/governance/templates', pageHeader: true },
    { path: '/governance/export', pageHeader: true },
    { path: '/governance/clauses', pageHeader: true },
    { path: '/governance/enum-dictionaries', pageHeader: true },
  ]
  for (const theme of ['dark', 'light']) {
    await page.evaluate((value) => localStorage.setItem('kg-theme-mode', value), theme)
    await page.reload()
    if (theme === 'dark') await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    else await expect(page.locator('html')).not.toHaveAttribute('data-theme')
    const contrast = await page.evaluate(() => {
      const root = getComputedStyle(document.documentElement)
      const canvas = document.createElement('canvas')
      const context = canvas.getContext('2d')
      if (!context) throw new Error('Canvas 2D color parsing unavailable')
      const rgb = (value: string): number[] => {
        context.fillStyle = value
        context.fillRect(0, 0, 1, 1)
        return Array.from(context.getImageData(0, 0, 1, 1).data).slice(0, 3)
      }
      const luminance = (value: string) =>
        rgb(value)
          .map((channel) => channel / 255)
          .map((channel) =>
            channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4,
          )
          .reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0)
      const background = luminance(root.getPropertyValue('--bg-base'))
      return ['--text', '--text-secondary'].map((token) => {
        const foreground = luminance(root.getPropertyValue(token))
        return (Math.max(background, foreground) + 0.05) / (Math.min(background, foreground) + 0.05)
      })
    })
    expect(
      contrast.every((ratio) => ratio >= 4.5),
      theme + ' text token contrast',
    ).toBe(true)

    for (const viewport of [
      { width: 1440, height: 960 },
      { width: 375, height: 812 },
    ]) {
      await page.setViewportSize(viewport)
      for (const route of routes) {
        await page.goto(route.path)
        await expect(page.locator('#app')).toBeVisible()
        await expect(page.locator('body')).not.toContainText('页面不存在')
        if (route.pageHeader) await expect(page.locator('.page-header')).toBeVisible()
        const width = await page.evaluate(() => ({
          viewport: window.innerWidth,
          document: document.documentElement.scrollWidth,
          body: document.body.scrollWidth,
        }))
        expect(
          Math.max(width.document, width.body),
          route.path + ' at ' + viewport.width + 'px in ' + theme,
        ).toBeLessThanOrEqual(width.viewport + 1)
      }
    }
  }
  expect(pageErrors).toEqual([])
})
