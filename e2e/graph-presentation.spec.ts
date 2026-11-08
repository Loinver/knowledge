import type { GraphView, SemanticViewFields } from '../web/src/api/graph'
import {
  capture,
  expect,
  getData,
  responseData,
  settleApi,
  test,
  uniqueName,
} from './ui-redesign-fixtures'

// Real, version-pinned labels with a controlled enterprise graph for repeatable visual QA.
const kinds = [
  ['Employee', '员工'],
  ['Department', '部门'],
  ['Enterprise', '企业'],
  ['Project', '项目'],
  ['Contract', '合同'],
] as const
const relations = [
  ['WorksIn', '任职于', 0, 1],
  ['BelongsToCompany', '隶属于', 1, 2],
  ['ProjectParticipation', '参与项目', 0, 3],
  ['ProjectFor', '服务于', 3, 2],
  ['ContractWith', '签约方', 4, 2],
  ['CoversProject', '覆盖项目', 4, 3],
] as const

test('Chinese frozen relationship labels, real evidence and refined nodes across viewports', async ({
  signedIn: page,
  identity,
  routeCatalog,
  network,
  evidence,
}, info) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  const post = async <T>(path: string, data?: unknown): Promise<T> =>
    responseData<T>(await identity.api.post('/api/v1' + path, { data }))
  const namespace = await post<{ id: number }>('/namespaces', {
    prefix: uniqueName('visual'),
    iri: 'https://example.org/' + uniqueName('visual') + '/',
    label_i18n: { 'zh-CN': '图谱视觉验收' },
  })
  const types = []
  for (const [name, zh] of kinds) {
    const type = await post<{ id: number; iri: string }>('/entity-types', {
      namespace_id: namespace.id,
      name,
      label_i18n: { 'zh-CN': zh, 'en-US': name },
      data_props:
        name === 'Department' ? [{ name: 'size', datatype: 'integer', nullable: true }] : [],
    })
    await post('/entity-types/' + type.id + '/publish')
    types.push(type)
  }
  const relationIds = []
  for (const [name, zh, from, to] of relations) {
    const relation = await post<{ id: number }>('/relations', {
      namespace_id: namespace.id,
      name,
      label_i18n: { 'zh-CN': zh, 'en-US': name },
      domain_spec: { type_id: types[from].id },
      range_spec: { type_id: types[to].id },
    })
    await post('/relations/' + relation.id + '/publish')
    relationIds.push(relation.id)
  }
  const ontology = await post<{ id: number }>('/ontologies', {
    name: uniqueName('VisualOntology'),
    iri: 'https://example.org/' + uniqueName('visual-ontology') + '/',
    label_i18n: { 'zh-CN': '图谱视觉验收' },
    ref_resource_ids: [...types.map((t) => t.id), ...relationIds],
  })
  await post('/ontologies/' + ontology.id + '/publish')
  {
    // Exercise predicates written by the real extraction engine, including evidence lookup.
    const mapping = await post<{ id: number; current_revision: number }>('/mappings', {
      name: uniqueName('ChineseGraph'),
      ontology_id: ontology.id,
      draft: {
        entity_maps: [
          ['Department', 'org_department'],
          ['Enterprise', 'enterprise'],
        ].map(([entity_type, table]) => ({
          entity_type,
          table,
          schema: 'main',
          key_fields: ['id'],
          field_maps: [{ target_attr: 'name', source_field: 'name', null_policy: 'REQUIRED' }],
        })),
        rel_maps: [
          {
            relation_type: 'BelongsToCompany',
            mode: 'FK',
            table: 'org_department',
            schema: 'main',
            fk_field: 'enterprise_id',
            source: null,
            target: null,
            attributes: [],
          },
        ],
      },
    })
    const revision = await post<{ id: number }>('/mappings/' + mapping.id + '/publish', {
      if_match: mapping.current_revision,
    })
    const result = await post<{ run: { status: string }; graph_revision: { id: number } }>(
      '/extraction/runs',
      {
        mapping_revision_id: revision.id,
        datasource_id: routeCatalog.datasourceId,
        namespace: 'https://example.org/real-graph-visual/',
      },
    )
    expect(result.run.status).toBe('SUCCESS')
    const extracted = await getData<GraphView>(
      identity.api,
      '/extraction/graph-view?graph_revision_id=' + result.graph_revision.id,
    )
    expect(extracted.edges.length).toBeGreaterThan(0)
    expect(extracted.edges[0].predicate).toBe('BelongsToCompany')
    await page.goto('/graph?graph=' + result.graph_revision.id)
    await settleApi(page, evidence)
    const fact = extracted.edges[0]
    const realEdge = page.locator(`.edge-group[data-edge-key="DIRECT:${fact.id}"]`)
    await realEdge.focus()
    await realEdge.press('Enter')
    await expect(realEdge.locator('.edge-label')).toHaveText('隶属于')
    await expect(page.locator('.graph-inspector h2')).toHaveText('隶属于')
    const trace = page.waitForResponse((response) =>
      new URL(response.url()).pathname.endsWith('/evidence/trace'),
    )
    await page
      .locator('.graph-inspector')
      .getByRole('button', { name: '追溯证据', exact: true })
      .click()
    const traced = await trace
    expect(new URL(traced.url()).searchParams.get('predicate')).toBe(fact.predicate)
    const traceData = await responseData<{ evidences: unknown[] }>(traced)
    expect(traceData.evidences.length).toBeGreaterThan(0)
    await capture(
      page,
      info,
      evidence,
      'graph-real-extraction-evidence',
      'real extraction, frozen Chinese label, unchanged bare predicate evidence lookup',
    )
  }
  const graph = await getData<GraphView>(
    identity.api,
    '/extraction/graph-view?graph_revision_id=' + routeCatalog.graphId,
  )
  const instance = 'https://example.org/graph-visual/'
  const names = [
    ['江云舟', '叶思齐', '程星然', '邵予清', '苏锦宁', '何向晚'],
    ['技术中心', '项目管理部', '客户服务部'],
    ['云岚科技有限公司', '望舒新能源有限公司', '锦辰物流服务有限公司'],
    ['望舒能源巡检平台', '设备关系图谱', '供应链数据治理', '城市资产管理'],
    ['巡检一期合同', '图谱实施合同', '数据治理合同', '运维服务合同'],
  ]
  const byKind: string[][] = []
  graph.nodes = names.flatMap((group, kind) => {
    byKind[kind] = group.map((_, index) => `${instance}${kinds[kind][0]}/${index}`)
    return group.map((name, index) => ({
      ...graph.nodes[0],
      id: kind * 10 + index + 1,
      iri: byKind[kind][index],
      type_iri: `${instance}${kinds[kind][0]}`,
      attrs: { name, ...(kind === 1 ? { size: 1 } : {}) },
      row_key: String(index),
    }))
  })
  graph.edges = []
  relations.forEach(([name, , from, to], relationIndex) => {
    byKind[from].forEach((subject, index) =>
      graph.edges.push({
        id: graph.edges.length + 1,
        graph_revision_id: graph.graph_revision_id,
        subject,
        object_: byKind[to][index % byKind[to].length],
        predicate: relationIndex === 1 ? name : instance + name,
        kind: relationIndex === 3 && index === 0 ? 'DERIVED' : 'DIRECT',
        props: {},
      }),
    )
  })
  graph.ontology_id = ontology.id
  graph.ontology_revision = 1
  graph.instance_namespace = instance
  graph.entity_total = graph.nodes.length
  graph.type_counts = kinds.map(([name], i) => ({
    type_iri: instance + name,
    count: names[i].length,
  }))
  graph.truncated = false
  await network.empty({ path: '/extraction/graph-view' }, graph)
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 },
    { width: 1024, height: 768 },
  ]) {
    await page.setViewportSize(viewport)
    await page.goto('/graph?graph=' + graph.graph_revision_id)
    await settleApi(page, evidence)
    await expect(page.locator('.node')).toHaveCount(20)
    await expect(page.locator('.graph-footer')).toContainText('当前显示 20 节点 / 27 关系')
    await capture(
      page,
      info,
      evidence,
      `graph-chinese-${viewport.width}`,
      'controlled 20-node/27-edge graph; real frozen bilingual relation catalog',
    )
    if (viewport.width > 1024)
      await expect(page.locator('.edge-label').filter({ hasText: '任职于' }).first()).toBeVisible()
    const edge = page.locator('.edge-group[data-edge-key="DIRECT:1"]')
    await edge.focus()
    await edge.press('Enter')
    await expect(edge.locator('.edge-label')).toHaveText('任职于')
    await expect(page.locator('.graph-inspector h2')).toHaveText('任职于')
    await expect(page.locator('.graph-inspector .n-tag')).toHaveText('直接关系事实')
    await expect(page.locator('.graph-inspector')).toContainText(instance + 'WorksIn')
    await page.getByRole('button', { name: '筛选与视图', exact: true }).click()
    // Naive UI exposes the select root as a labelled element, not always a combobox.
    const select = page.locator('[aria-label="显示关系"]').first()
    await select.click()
    await expect(
      page.locator('.n-base-select-option:visible').filter({ hasText: '任职于' }),
    ).toBeVisible()
    await page.keyboard.press('Escape')
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: '切换语言', exact: true }).click()
    await expect(page.locator('.graph-inspector h2')).toHaveText('WorksIn')
    await page.getByRole('button', { name: 'Switch language', exact: true }).click()
    await expect(page.locator('.graph-inspector h2')).toHaveText('任职于')
    await capture(
      page,
      info,
      evidence,
      `graph-selected-${viewport.width}`,
      'Chinese relation details retain original predicate and selected context',
    )
    await page
      .locator('.graph-inspector')
      .getByRole('button', { name: '关闭', exact: true })
      .click()
    await page.getByRole('button', { name: '事实表', exact: true }).click()
    const factRow = page.locator('.n-data-table-tr').filter({ hasText: '任职于' }).first()
    await expect(factRow).toBeVisible()
    const traceHref = await factRow
      .getByRole('link', { name: '追溯证据', exact: true })
      .getAttribute('href')
    expect(new URL(traceHref!, 'http://localhost').searchParams.get('predicate')).toBe(
      instance + 'WorksIn',
    )
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: '切换到暗色模式', exact: true }).click()
    await capture(
      page,
      info,
      evidence,
      `graph-chinese-dark-${viewport.width}`,
      'same graph and frozen labels in dark theme',
    )
    await page.getByRole('button', { name: '切换到浅色模式', exact: true }).click()
  }
  await page.setViewportSize({ width: 1440, height: 900 })
  const fields = await getData<SemanticViewFields>(
    identity.api,
    `/view-templates/semantic-fields?ontology_id=${ontology.id}&ontology_revision=1`,
  )
  const measure = fields.fields.find((field) => field.name === 'size' && field.kind === 'PROPERTY')
  expect(measure).toBeDefined()
  for (const layout of ['sunburst', 'treemap', 'pack']) {
    const template = await post<{ id: number }>('/view-templates', {
      name_i18n: { 'zh-CN': '图例验收', 'en-US': 'Legend verification' },
      ontology_id: ontology.id,
      ontology_revision: 1,
      layout_id: layout,
      config: { semantic_version: 1, measure_property_iri: measure!.iri },
    })
    await page.goto(`/graph?graph=${graph.graph_revision_id}&template=${template.id}`)
    await settleApi(page, evidence)
    await page.getByRole('button', { name: '图例', exact: true }).click()
    const legendIcon = page
      .locator('.legend-type')
      .filter({ hasText: 'Department' })
      .locator('.type-icon')
    const mark = page.locator('.mark-group[aria-label="Department"] .mark')
    await expect(mark).toBeVisible()
    await expect(page.locator('.graph-footer')).toContainText('当前显示 3 节点 / 0 关系')
    for (const theme of ['light', 'dark']) {
      if (theme === 'dark')
        await page.getByRole('button', { name: '切换到暗色模式', exact: true }).click()
      const color = await legendIcon.evaluate((el) => getComputedStyle(el).color)
      expect(await mark.evaluate((el) => getComputedStyle(el).fill)).toBe(color)
    }
    await capture(
      page,
      info,
      evidence,
      `graph-${layout}-legend`,
      'partition marks and legend share actual layout colors in both themes',
    )
    await page.getByRole('button', { name: '切换到浅色模式', exact: true }).click()
  }
})
