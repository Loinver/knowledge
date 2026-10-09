import { execFileSync } from 'node:child_process'
import { copyFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { expect, test, type APIRequestContext, type APIResponse, type Page } from '@playwright/test'

import { ensureAdmin } from './admin'

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
  return { ontologyId: ontology.id, entityTypes, relationTypes }
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
  await expect(modal.getByText(/发现 17 张表/)).toBeVisible()
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

async function deleteMappingThroughUI(page: Page, mappingName: string): Promise<void> {
  await page.goto('/extraction')
  await page.locator('.mapping-picker .n-base-selection').click()
  await page.getByText(mappingName + ' · 草稿', { exact: true }).click()
  await page.getByRole('button', { name: '删除', exact: true }).click()
  await page.getByRole('button', { name: '确认', exact: true }).click()
  await expect(page.getByText(`映射 ${mappingName} 已删除。`)).toBeVisible()
}

async function createTaskThroughUI(
  page: Page,
  mappingName: string,
  datasourceLabel: string,
): Promise<number> {
  await page.goto('/extraction/tasks')
  await expect(page.getByRole('heading', { name: '抽取任务', exact: true })).toBeVisible()
  await page.locator('.task-form .n-base-selection').nth(0).click()
  await page.getByText(mappingName, { exact: true }).click()
  await page.locator('.task-form .n-base-selection').nth(1).click()
  await page.getByText(datasourceLabel, { exact: true }).click()
  await page
    .locator('.task-form .n-form-item')
    .filter({ hasText: '运行命名空间' })
    .first()
    .locator('input')
    .fill('https://example.org/e2e/graph/')
  await expect(page.getByRole('button', { name: '创建任务' })).toBeEnabled()
  await page.getByRole('button', { name: '创建任务' }).click()
  const notice = page.getByText(/任务 #\d+ 已创建。/)
  await expect(notice).toBeVisible()
  const taskId = Number(/#(\d+)/.exec(await notice.innerText())![1])
  await expect(
    page
      .locator('tr')
      .filter({ hasText: String(taskId) })
      .getByText('成功'),
  ).toBeVisible({ timeout: 20000 })
  return taskId
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
  await expect(page.locator('.catalog-summary')).toContainText('17')

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
  test.setTimeout(300_000)
  const tempDir = process.env.KG_E2E_TEMP_DIR
  expect(tempDir, 'Playwright config provides an isolated temp directory').toBeTruthy()
  const sourcePath = join(tempDir!, 'enterprise-demo-copy.sqlite')
  copyFileSync(resolve('samples/enterprise_demo.sqlite'), sourcePath)
  await ensureAdmin(page)
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
  const administrator = await responseData<{ access_token: string; refresh_token: string }>(
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

  const workflowLabels = [
    '实体类型',
    '关系类型',
    '业务域',
    '本体',
    '本体建模',
    '规则',
    '知识抽取',
    '知识图谱',
    '知识追溯',
  ]
  await expect(page.locator('.pipe-name')).toHaveText(workflowLabels)
  await expect(page.locator('.pipe-action')).toHaveCount(3)
  const sider = page.locator('.app-sider')
  const menuLabels = await sider.locator('.n-menu-item-content-header').allTextContents()
  expect(menuLabels.filter((label) => workflowLabels.includes(label))).toEqual(workflowLabels)
  await expect(sider.getByText('系统管理', { exact: true })).toHaveCount(0)

  await sider.getByText('知识抽取', { exact: true }).click()
  await sider.getByText('数据源', { exact: true }).click()
  await expect(page).toHaveURL(/\/datasources$/)
  await expect(page.locator('.n-breadcrumb-item__link')).toHaveText(['知识抽取', '数据源'])
  await sider.getByText('知识追溯', { exact: true }).click()
  await expect(page).toHaveURL(/\/graph\/evidence$/)
  await expect(page.locator('.n-breadcrumb-item__link')).toHaveText(['知识追溯'])
  await page.goBack()
  await expect(page).toHaveURL(/\/datasources$/)
  await expect(sider.locator('.n-menu-item-content--selected')).toHaveText('数据源')
  await page.locator('.brand').click()
  await page.getByRole('button', { name: '切换语言', exact: true }).click()
  await expect(page.locator('.pipe-name')).toHaveText([
    'Entity Types',
    'Relation Types',
    'Business Domains',
    'Ontology',
    'Ontology Modeling',
    'Rules',
    'Knowledge Extraction',
    'Knowledge Graph',
    'Knowledge Tracing',
  ])
  await page.getByRole('button', { name: 'Switch language', exact: true }).click()
  await expect(page.locator('.pipe-name')).toHaveText(workflowLabels)

  const ontology = await seedOntology(request)
  const datasourceId = await createSourceThroughUI(page, sourcePath)
  await captureCatalogThroughUI(page, datasourceId)
  const mapping = await seedMapping(request, ontology.ontologyId)
  const disposableMapping = await postData<Brief>(request, '/mappings', {
    name: 'E2EDeleteMapping',
    ontology_id: ontology.ontologyId,
  })
  await deleteMappingThroughUI(page, disposableMapping.name)
  await chooseMappingAndRunThroughUI(page, mapping.name)

  const runs = await getData<RunOut[]>(request, '/extraction/runs?page=1&page_size=20')
  const firstRun = runs[0]
  expect(firstRun?.status).toBe('SUCCESS')
  expect(firstRun?.counts.entity_count).toBeGreaterThan(0)
  expect(firstRun?.counts.triple_count).toBeGreaterThan(0)

  const immediateTaskId = await createTaskThroughUI(page, mapping.name, 'E2E 样例源 · sqlite')
  expect(immediateTaskId).toBeGreaterThan(0)
  const publishedRevision = await getData<{ id: number }>(
    request,
    '/mappings/' + mapping.id + '/published',
  )
  const scheduledTask = await postData<{ id: number }>(request, '/extraction/tasks', {
    mapping_revision_id: publishedRevision.id,
    datasource_id: datasourceId,
    namespace: 'https://example.org/kg/',
    incremental: false,
    run_after: new Date(Date.now() + 3_600_000).toISOString(),
  })
  await page.goto('/extraction/tasks')
  const scheduledRow = page.locator('tr').filter({ hasText: String(scheduledTask.id) })
  await scheduledRow.getByRole('button', { name: '取消任务' }).click()
  await expect(page.getByText(`任务 #${scheduledTask.id} 已取消。`)).toBeVisible()

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

  // ===== 第二批验收：命名空间登记 UI / 数据规则 UI / 图谱形态 / 证据链与反查 =====

  // 全程界面第 1 步：命名空间管理页登记（空库也能在界面建模的第一入口）
  await page.goto('/ontology/namespaces')
  await page.getByRole('button', { name: '登记命名空间' }).first().click()
  const nsDialog = page.getByRole('dialog')
  await nsDialog.getByPlaceholder('kg', { exact: true }).fill('e2eforms')
  await nsDialog
    .getByPlaceholder('https://example.org/kg#', { exact: true })
    .fill('https://example.org/e2eforms/')
  await nsDialog.getByPlaceholder('请输入').nth(0).fill('端到端形态')
  await nsDialog.getByPlaceholder('请输入').nth(1).fill('E2E forms')
  await nsDialog.getByRole('button', { name: '保存' }).click()
  await expect(page.getByRole('cell', { name: 'e2eforms', exact: true })).toBeVisible()

  // 规则页 UI：新建数据规则（DATA 语言 + JSON 表达式，正反例可空）
  await page.goto('/governance/rules')
  await page.getByRole('button', { name: '新建规则' }).click()
  const ruleDrawer = page.locator('.n-drawer').filter({ hasText: '新建规则' })
  await ruleDrawer.getByLabel('规则标识').fill('E2E_UNIQUE_CREDIT')
  await ruleDrawer.getByLabel('分类').fill('scene')
  await ruleDrawer.getByLabel('中文标签').fill('信用代码唯一')
  await ruleDrawer.getByLabel('英文标签').fill('Unique credit code')
  await ruleDrawer.getByLabel('来源依据').fill('E2E-POLICY-01')
  await ruleDrawer.getByLabel('作用类型 IRI').fill('https://example.org/e2e/E2EEnterprise')
  await ruleDrawer.locator('.n-tabs-tab').filter({ hasText: '表达式' }).click()
  const languageSelect = ruleDrawer
    .locator('.n-form-item')
    .filter({ hasText: '表达语言' })
    .locator('.n-select')
  await languageSelect.click()
  await page.locator('.n-base-select-option').filter({ hasText: '数据规则' }).click()
  await ruleDrawer
    .locator('.code-input textarea')
    .first()
    .fill('{"op": "unique_attr", "type": "E2EEnterprise", "attr": "name"}')
  await ruleDrawer.getByRole('button', { name: '保存' }).click()
  await expect(page.getByText('规则已保存')).toBeVisible()
  await page.locator('.n-drawer-header__close').click()
  await expect(page.getByRole('cell', { name: 'E2E_UNIQUE_CREDIT' })).toBeVisible()

  // 图谱形态选择器 + 推荐条
  const linkedFact = firstTriples.find((fact) => fact.subject !== fact.object_)
  expect(linkedFact, 'sample data contains at least one cross-entity fact').toBeTruthy()
  await page.goto('/graph?graph=' + firstGraph!.id + '&layout=org_tree')
  await expect(page.locator('svg .node').first()).toBeVisible()
  await expect(page.getByText('形态', { exact: true })).toBeVisible()
  await expect(page.getByText('推荐形态：')).toBeVisible()
  await page.goto('/graph?graph=' + firstGraph!.id + '&layout=force')
  await expect(page.locator('svg .node').first()).toBeVisible()

  // 关系路径抽屉（G-12）：沿样例事实的端点找最短路径
  await page.getByRole('button', { name: '关系路径' }).click()
  const pathDrawer = page.locator('.n-drawer').filter({ hasText: '起点 IRI' })
  await pathDrawer.getByLabel('起点 IRI').fill(linkedFact!.subject)
  await pathDrawer.getByLabel('终点 IRI').fill(linkedFact!.object_)
  await pathDrawer.getByRole('button', { name: '查找路径' }).click()
  await expect(pathDrawer.getByText(/找到最短路径|未在最大跳数内找到路径/)).toBeVisible()
  await pathDrawer.locator('.n-drawer-header__close').click()

  // 版本差异抽屉（G-24）：firstGraph vs partial
  await page.getByRole('button', { name: '版本差异' }).click()
  const diffDrawer = page.locator('.n-drawer').filter({ hasText: '基准结果集' })
  await diffDrawer.getByRole('textbox', { name: '基准结果集' }).fill(String(firstGraph!.id))
  await diffDrawer
    .getByRole('textbox', { name: '目标结果集' })
    .fill(String(partial.graph_revision.id))
  await diffDrawer.getByRole('button', { name: '计算差异' }).click()
  await expect(diffDrawer.getByText(/实体 \+\d+\/−\d+，事实 \+\d+\/−\d+/)).toBeVisible()
  await diffDrawer.locator('.n-drawer-header__close').click()

  // 质量叠加（G-28）：PARTIAL 结果集的隔离命中节点带标记
  await page.goto('/graph?graph=' + partial.graph_revision.id)
  await page.getByText('质量叠加').click()
  await expect(page.locator('svg .quality-flag').first()).toBeVisible()

  // 导出菜单存在且可选
  await page.getByRole('button', { name: '导出' }).click()
  await expect(page.getByText('导出节点 CSV')).toBeVisible()
  await page.keyboard.press('Escape')

  // 证据冻结链（G-26）：事实 → 来源行 → 运行 → 冻结版本
  await page.goto(
    '/graph/evidence?mode=entity&graph=' +
      firstGraph!.id +
      '&iri=' +
      encodeURIComponent(employee!.iri),
  )
  await page.getByRole('button', { name: '查看链' }).first().click()
  await expect(page.getByText('冻结本体版本')).toBeVisible()

  // 反向追溯（V-TR-05）：来源行 → 产出实体
  await page.goto('/graph/evidence?graph=' + firstGraph!.id)
  await page.getByText('按来源行反查').click()
  await page.getByLabel('数据源 ID').fill(String(datasourceId))
  await page.getByLabel('来源表').fill('hr_employee')
  await page.getByLabel('来源行键').fill('8001')
  await page.getByRole('button', { name: '追溯证据' }).click()
  await expect(page.getByText(/参与 \d+ 条事实、产出 \d+ 个实体/)).toBeVisible()
  await page.evaluate(
    (tokens) => {
      localStorage.setItem('kg-access-token', tokens.access)
      localStorage.setItem('kg-refresh-token', tokens.refresh)
    },
    { access: administrator.access_token, refresh: administrator.refresh_token },
  )
  await page.reload()

  const routes = [
    { path: '/', pageHeader: true },
    { path: '/ontology/ontologies', pageHeader: true },
    { path: '/ontology/entity-types', pageHeader: true },
    { path: '/ontology/namespaces', pageHeader: true },
    { path: '/ontology/entity-types/' + ontology.entityTypes.E2EEmployee.id, pageHeader: true },
    { path: '/ontology/relation-types', pageHeader: true },
    {
      path: '/ontology/relation-types/' + ontology.relationTypes[0].id,
      pageHeader: true,
    },
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
    { path: '/extraction/tasks', pageHeader: true },
    { path: '/extraction/ai-assist', pageHeader: true },
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
    { path: '/account/profile', pageHeader: true },
    { path: '/account/security', pageHeader: true },
    { path: '/system/users', pageHeader: true },
    { path: '/system/roles', pageHeader: true },
    { path: '/system/audit-logs', pageHeader: true },
    { path: '/forbidden', pageHeader: false },
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
        const visibleText = await page.locator('body').innerText()
        expect(visibleText, route.path).not.toContain('[object Object]')
        expect(visibleText, route.path).not.toMatch(/\bKG\.[A-Z0-9_]+\b/)
        expect(visibleText, route.path).not.toMatch(
          /\b(?:errors|dataAccess|ontology|graph|system|account|runs|tasks)\.[A-Za-z0-9_.]+\b/,
        )
        if (route.pageHeader) await expect(page.locator('.page-header')).toBeVisible()
        if (route.path === '/') {
          await expect(page.locator('.pipe-step')).toHaveCount(9)
          const backdrop = page.locator('.mobile-backdrop')
          if (viewport.width < 767 && (await backdrop.isVisible())) {
            await page.screenshot({
              path: test.info().outputPath(`workflow-menu-${theme}-${viewport.width}.png`),
              animations: 'disabled',
            })
            await backdrop.click({ position: { x: viewport.width - 10, y: 100 } })
            await expect(backdrop).toBeHidden()
          }
          if (
            viewport.width >= 767 &&
            (await sider.evaluate((element) =>
              element.classList.contains('n-layout-sider--collapsed'),
            ))
          ) {
            await page.getByRole('button', { name: '展开侧栏', exact: true }).click()
          }
          await page.screenshot({
            path: test.info().outputPath(`workflow-${theme}-${viewport.width}.png`),
            fullPage: true,
            animations: 'disabled',
          })
        }
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

  await page.goto('/missing-page-for-audit')
  await expect(page.getByText('页面不存在').first()).toBeVisible()

  await page.goto('/')
  await page.getByRole('button', { name: '用户菜单' }).click()
  await page.getByText('退出登录').click()
  await page.getByRole('button', { name: '确认', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)

  const publicRoutes = [
    { path: '/login', heading: '登录' },
    { path: '/register', heading: '注册账号' },
    { path: '/forgot-password', heading: '找回密码' },
    { path: '/reset-password', heading: '重置密码' },
  ]
  for (const viewport of [
    { width: 1440, height: 960 },
    { width: 375, height: 812 },
  ]) {
    await page.setViewportSize(viewport)
    for (const route of publicRoutes) {
      await page.goto(route.path)
      await expect(page.getByRole('heading', { name: route.heading })).toBeVisible()
      const visibleText = await page.locator('body').innerText()
      expect(visibleText, route.path).not.toContain('[object Object]')
      expect(visibleText, route.path).not.toMatch(/\bKG\.[A-Z0-9_]+\b/)
      const width = await page.evaluate(() => ({
        viewport: window.innerWidth,
        document: document.documentElement.scrollWidth,
        body: document.body.scrollWidth,
      }))
      expect(
        Math.max(width.document, width.body),
        route.path + ' at ' + viewport.width + 'px',
      ).toBeLessThanOrEqual(width.viewport + 1)
    }
  }
  expect(pageErrors).toEqual([])
})
