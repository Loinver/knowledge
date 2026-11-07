import { execFileSync } from 'node:child_process'
import { join, resolve } from 'node:path'
import { expect, test, type Page } from '@playwright/test'

import { ensureAdmin, loginAsAdmin } from './admin'

/** Isolated UI workflow: only account preparation and synthetic source setup bypass the UI. */

/**
 * naive-ui 的下拉选项浮层；按文本挑一项。
 *
 * 必须限定 `:visible`：选完一个下拉后，它的浮层仍留在 DOM 里（隐藏），
 * 而同一个浮层里往往有全部选项 —— 不加可见性过滤会挑到上一个浮层的隐藏项，
 * 表现为「元素已解析但 not visible」一直重试到超时。
 */
async function pickOption(page: Page, label: string): Promise<void> {
  // 下拉浮层渲染有延迟，先等目标选项出现再点。
  await page
    .locator('.n-base-select-option:visible')
    .filter({ has: page.getByText(label, { exact: true }) })
    .last()
    .waitFor({ state: 'visible', timeout: 10000 })
  await page
    .locator('.n-base-select-option:visible')
    .filter({ has: page.getByText(label, { exact: true }) })
    .last()
    .click()
}

/**
 * 当前打开的弹窗/抽屉（naive-ui 的 NModal / NDrawer）。
 *
 * 必须把表单控件限定在浮层里：同一页常有多个同名按钮（例如空态与页头各有一个
 * 「登记命名空间」），直接 getByRole 会撞 strict mode；页面上也可能残留上一个抽屉。
 */
function overlay(page: Page) {
  return page.locator('.n-modal:visible, .n-drawer:visible').last()
}

/**
 * naive-ui 的 NFormItem 不会把 label 关联到 input（`getByLabel` 定位不到），
 * 按「表单项」容器定位内部控件才稳。
 */
function formItem(page: Page, label: string) {
  return overlay(page)
    .locator('.n-form-item')
    .filter({ has: page.getByText(label, { exact: true }) })
    .last()
}

async function fillField(page: Page, label: string, value: string): Promise<void> {
  await formItem(page, label).locator('input').fill(value)
}

async function selectField(page: Page, label: string, option: string): Promise<void> {
  await formItem(page, label).locator('.n-base-selection').click()
  await pickOption(page, option)
}

async function saveOverlay(page: Page): Promise<void> {
  await overlay(page).getByRole('button', { name: '保存' }).click()
}

async function checkCompanyAttribute(page: Page, value: string): Promise<string> {
  const entities = page.getByRole('link', { name: '实体实例', exact: true }).first()
  await expect(entities).toHaveAttribute('href', /graph=\d+/)
  const graph = new URL((await entities.getAttribute('href'))!, page.url()).searchParams.get(
    'graph',
  )!
  await entities.click()
  await page
    .getByRole('link', { name: 'https://example.org/audit/ontology#AuditCompany/1', exact: true })
    .click()
  await expect(page.locator('.n-data-table').first()).toContainText(value)
  return graph
}

async function createNamespace(
  page: Page,
  prefix: string,
  iri: string,
  label: string,
): Promise<void> {
  await page.goto('/ontology/namespaces')
  // 空态与页头各有一个同名按钮，取第一个即可。
  await page.getByRole('button', { name: '登记命名空间' }).first().click()
  await overlay(page).getByPlaceholder('kg', { exact: true }).fill(prefix)
  await overlay(page).getByPlaceholder('https://example.org/kg#', { exact: true }).fill(iri)
  await fillField(page, '中文标签', label)
  await saveOverlay(page)
  await expect(page.getByText(`命名空间 ${prefix} 已登记。`)).toBeVisible()
  await expect(page.getByText(iri).first()).toBeVisible()
}

async function createEntityType(
  page: Page,
  name: string,
  label: string,
  namespacePrefix: string,
): Promise<void> {
  await page.goto('/ontology/entity-types')
  // 触发按钮用的是 common.create（"创建"），抽屉标题才是"新建实体类型"。
  await page.getByRole('button', { name: '创建', exact: true }).first().click()
  await overlay(page).getByPlaceholder('Employee', { exact: true }).fill(name)
  // 命名空间下拉的 label 是前缀（nsOptions: label = ns.prefix），不是中文标签。
  await selectField(page, '命名空间', namespacePrefix)
  await fillField(page, '中文标签', label)
  await saveOverlay(page)
  await expect(page.getByText(name, { exact: true }).first()).toBeVisible()
}

/** 数据属性在详情页的属性抽屉里加：机读名 + 中文标签，数据类型保持默认 string。 */
async function addDataProperty(
  page: Page,
  typeId: number,
  propName: string,
  propLabel: string,
): Promise<void> {
  await page.goto(`/ontology/entity-types/${typeId}`)
  // 「添加属性」在「数据属性」页签里，不切页签找不到。
  // naive-ui 的页签是 `.n-tabs-tab`，不是 role="tab"。
  await page.locator('.n-tabs-tab').filter({ hasText: '数据属性' }).first().click()
  await page.getByRole('button', { name: '添加属性', exact: true }).click()
  await fillField(page, '机读名', propName)
  await fillField(page, '中文标签', propLabel)
  await saveOverlay(page)
  await expect(page.getByText(propLabel).first()).toBeVisible()
}

async function createRelationType(
  page: Page,
  name: string,
  label: string,
  namespacePrefix: string,
  domain: string,
  range: string,
): Promise<void> {
  await page.goto('/ontology/relation-types')
  await page.getByRole('button', { name: '创建', exact: true }).first().click()
  await overlay(page).getByPlaceholder('WorksIn', { exact: true }).fill(name)
  // 命名空间按前缀选；定义域/值域的下拉 label 是类型的中文标签。
  await selectField(page, '命名空间', namespacePrefix)
  await fillField(page, '中文标签', label)
  await selectField(page, '定义域', domain)
  await selectField(page, '值域', range)
  await saveOverlay(page)
  await expect(page.getByText(name, { exact: true }).first()).toBeVisible()
}

/** 发布实体类型：详情页点发布按钮，等已发布状态出现。 */
async function publishEntityType(page: Page, name: string): Promise<void> {
  await page.goto('/ontology/entity-types')
  // 卡片视图的卡片可访问名含机读名（cell-sub），按子串匹配。
  await page.getByRole('button', { name: '卡片', exact: true }).click()
  await page.getByRole('button', { name: name }).first().click()
  await expect(page).toHaveURL(/\/ontology\/entity-types\/\d+/)
  const typeId = Number(/entity-types\/(\d+)/.exec(page.url())![1])
  await addDataProperty(page, typeId, 'Name', '名称')
  await page.getByRole('button', { name: '发布', exact: true }).first().click()
  await expect(page.getByText('已发布').first()).toBeVisible({ timeout: 15000 })
}

/** 发布关系类型：列表页行内发布按钮。 */
async function publishRelationType(page: Page, label: string): Promise<void> {
  await page.goto('/ontology/relation-types')
  // 行内发布按钮的父行包含关系类型名；naive-ui 的 NDataTable 行无 role，按文本定位。
  const row = page
    .locator('tr')
    .filter({ has: page.getByText(label, { exact: true }) })
    .last()
  await row.getByRole('button', { name: '发布', exact: true }).click()
  await expect(page.getByText('已发布').first()).toBeVisible({ timeout: 15000 })
}

async function createDomain(page: Page, name: string, iri: string, label: string): Promise<void> {
  await page.goto('/ontology/domains')
  await page.getByRole('button', { name: '创建', exact: true }).first().click()
  await overlay(page).getByPlaceholder('HumanResources', { exact: true }).fill(name)
  await overlay(page).getByPlaceholder('urn:knowledge:domain:hr', { exact: true }).fill(iri)
  await fillField(page, '中文标签', label)
  await saveOverlay(page)
  // 业务域列表显示的是 label（pickLabel），不是机读名 name。
  await expect(page.getByText(label, { exact: true }).first()).toBeVisible()
}

test('UI modeling, frozen evidence, correction and history switch', async ({ page }, testInfo) => {
  const sourcePath = join(process.env.KG_E2E_TEMP_DIR!, 'audit-source.sqlite')
  execFileSync(resolve('server/.venv/bin/python'), [
    '-c',
    `
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
 db.executescript("""
 CREATE TABLE enterprise(id INTEGER PRIMARY KEY, name TEXT, alternate_name TEXT);
 CREATE TABLE hr_employee(id INTEGER PRIMARY KEY, name TEXT, enterprise_id INTEGER REFERENCES enterprise(id));
 INSERT INTO enterprise VALUES (1, 'Audit Company', 'Corrected Company');
 INSERT INTO hr_employee VALUES (1, 'Audit Employee', 1);
 """)
`,
    sourcePath,
  ])
  await ensureAdmin(page)
  await loginAsAdmin(page)
  await createNamespace(page, 'audit', 'https://example.org/audit#', '审计命名空间')
  await createEntityType(page, 'AuditCompany', '审计企业', 'audit')
  await publishEntityType(page, 'AuditCompany')
  await createEntityType(page, 'AuditEmployee', '审计员工', 'audit')
  await publishEntityType(page, 'AuditEmployee')
  await createRelationType(page, 'AuditWorksFor', '审计任职', 'audit', '审计员工', '审计企业')
  await publishRelationType(page, '审计任职')
  await createDomain(page, 'AuditDomain', 'urn:knowledge:audit', '审计业务域')
  await page.goto('/governance/rules')
  await page.getByRole('button', { name: '新建规则' }).click()
  await overlay(page).getByLabel('规则标识', { exact: true }).fill('AuditUniqueName')
  await overlay(page).getByLabel('分类', { exact: true }).fill('audit')
  await overlay(page).getByLabel('中文标签', { exact: true }).fill('审计名称唯一')
  await overlay(page).getByLabel('来源依据', { exact: true }).fill('synthetic audit rule')
  await overlay(page)
    .getByLabel('作用类型 IRI', { exact: true })
    .fill('https://example.org/audit#AuditCompany')
  await overlay(page).locator('.n-tabs-tab').filter({ hasText: '表达式' }).click()
  await selectField(page, '表达语言', '数据规则')
  await overlay(page)
    .getByLabel('规则表达式（Turtle）', { exact: true })
    .fill('{' + '"op":"unique_attr","attr":"Name"' + '}')
  await saveOverlay(page)
  await expect(page.getByText('规则已保存。')).toBeVisible()
  await page.goto('/ontology/ontologies')
  await page.getByRole('button', { name: '新建本体' }).first().click()
  await fillField(page, '机读名', 'AuditOntology')
  await fillField(page, 'IRI', 'https://example.org/audit/ontology#')
  await fillField(page, '中文标签', '审计本体')
  await saveOverlay(page)
  await expect(page).toHaveURL(/designer\?ontology=\d+/)
  const ontologyId = new URL(page.url()).searchParams.get('ontology')!
  for (const label of ['审计企业', '审计员工', '审计任职']) {
    await page.locator('.pool-item.addable').filter({ hasText: label }).click()
    await expect(page.locator('.pool-item.on').filter({ hasText: label })).toBeVisible()
  }
  await page.getByRole('button', { name: '装配规则', exact: true }).click()
  await overlay(page).locator('.n-base-selection').click()
  await pickOption(page, 'AuditUniqueName · r1')
  await page.keyboard.press('Escape')
  await saveOverlay(page)
  await page.getByRole('button', { name: '自动布局' }).click()
  await page.screenshot({ path: testInfo.outputPath('designer.png'), fullPage: true })
  await page.getByRole('button', { name: '发布', exact: true }).click()
  await expect(page.locator('.toolbar')).toContainText('已发布')
  await page.goto('/datasources')
  await page.getByRole('button', { name: '新建数据源' }).click()
  const modal = page.locator('.source-modal')
  await modal.getByLabel('名称').fill('审计样例源')
  await modal.getByLabel('数据库').fill(sourcePath)
  await modal.getByRole('button', { name: '测试连接' }).click()
  await expect(modal.getByText(/发现 2 张表/)).toBeVisible()
  await modal.getByRole('button', { name: '保存' }).click()
  await expect(modal).not.toBeVisible()
  await page.goto('/extraction')
  await page.locator('.step-content input').first().fill('AuditMapping')
  await page.locator('.step-content .n-base-selection').first().click()
  await pickOption(page, '审计本体 · AuditOntology')
  await page.locator('.wizard-footer').getByRole('button', { name: '下一步' }).click()
  await page.locator('.datasource-form .n-base-selection').first().click()
  await pickOption(page, '审计样例源 · sqlite')
  await page.getByRole('button', { name: '采集元数据' }).click()
  await expect(page.locator('.catalog-summary')).toContainText('2')
  await page.locator('.wizard-footer').getByRole('button', { name: '下一步' }).click()
  for (const [entity, table] of [
    ['AuditCompany', 'enterprise'],
    ['AuditEmployee', 'hr_employee'],
  ]) {
    await page.getByRole('button', { name: '添加实体映射' }).click()
    const editor = page
      .locator('.editor-card')
      .filter({ hasText: entity })
      .filter({ has: page.locator('.map-selectors') })
      .first()
    await editor.locator('.map-selectors .n-base-selection').nth(1).click()
    await pickOption(page, 'main.' + table)
    await editor.locator('.field-table tbody .n-base-selection').first().click()
    await pickOption(page, 'name · TEXT')
    await editor
      .locator('.key-option')
      .filter({ has: page.getByText('id', { exact: true }) })
      .first()
      .locator('input')
      .check()
    await editor.getByLabel('增量水位字段', { exact: true }).click()
    await pickOption(page, 'id')
  }
  await page.getByRole('button', { name: '添加关系映射' }).click()
  const relation = page.locator('.relation-editor')
  await relation.locator('.map-selectors .n-base-selection').nth(1).click()
  await pickOption(page, '外键')
  await relation.locator('.map-selectors .n-base-selection').nth(2).click()
  await pickOption(page, 'main.hr_employee')
  await relation.locator('.endpoint-grid .n-base-selection').first().click()
  await pickOption(page, 'enterprise_id')
  await page.keyboard.press('Escape')
  await page.screenshot({ path: testInfo.outputPath('mapping.png'), fullPage: true })
  await page.locator('.wizard-footer').getByRole('button', { name: '保存并预览' }).click()
  await expect(page.getByText('当前样例没有发现字段错误。')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('preview.png'), fullPage: true })
  await page.locator('.wizard-footer').getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '发布映射' }).click()
  await expect(page.getByText(/映射 rev\./)).toBeVisible()
  await page.getByRole('button', { name: '启动抽取' }).click()
  await expect(page.getByText(/运行编号 #/)).toBeVisible()
  await page.goto('/graph')
  await expect(page.locator('.canvas-panel')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('graph.png'), fullPage: true })
  const originalGraph = await checkCompanyAttribute(page, 'Audit Company')
  await page.goto('/graph')
  await page.getByRole('link', { name: '追溯证据', exact: true }).first().click()
  await expect(page).toHaveURL(/graph\/evidence/)
  await expect(page.getByText('hr_employee', { exact: true }).first()).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('evidence.png'), fullPage: true })
  await page.getByRole('button', { name: '查看链', exact: true }).first().click()
  await expect(page.getByText('冻结映射 r1')).toBeVisible()
  await page.getByRole('link', { name: '修正当前映射' }).click()
  await expect(page).toHaveURL(/extraction\?mapping=\d+/)
  await page.getByRole('button', { name: '复制为新草稿' }).click()
  await page.locator('.wizard-footer').getByRole('button', { name: '下一步' }).click()
  await page.locator('.datasource-form .n-base-selection').first().click()
  await pickOption(page, '审计样例源 · sqlite')
  await page.locator('.wizard-footer').getByRole('button', { name: '下一步' }).click()
  const copiedCompany = page
    .locator('.editor-card')
    .filter({ hasText: 'AuditCompany' })
    .filter({ has: page.locator('.map-selectors') })
    .first()
  await expect(copiedCompany.getByLabel('增量水位字段', { exact: true })).toContainText('id')
  await copiedCompany.locator('.field-table tbody .n-base-selection').first().click()
  await pickOption(page, 'alternate_name · TEXT')
  await page.locator('.wizard-footer').getByRole('button', { name: '保存并预览' }).click()
  await expect(page.getByText('当前样例没有发现字段错误。')).toBeVisible()
  await page.locator('.wizard-footer').getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '发布映射' }).click()
  await expect(page.getByText(/映射 rev\./)).toBeVisible()
  await page.getByRole('button', { name: '启动抽取' }).click()
  await expect(page.getByText(/运行编号 #/)).toBeVisible()
  await page.goto('/graph')
  const correctedGraph = await checkCompanyAttribute(page, 'Corrected Company')
  expect(correctedGraph).not.toBe(originalGraph)
  await page.goto('/graph')
  await page.getByRole('button', { name: '历史图谱版本' }).click()
  const older = overlay(page)
    .locator('li')
    .filter({ hasText: `图谱 #${originalGraph} ·` })
  await older.getByRole('button', { name: '设为当前' }).click()
  await page.getByRole('button', { name: '确认', exact: true }).click()
  await expect(older).toContainText('当前版本')
  await page.screenshot({ path: testInfo.outputPath('history.png'), fullPage: true })
  await page.goto('/graph')
  expect(await checkCompanyAttribute(page, 'Audit Company')).toBe(originalGraph)

  await page.goto('/governance/clauses')
  await page.getByRole('button', { name: '新建条款' }).click()
  await fillField(page, '标准号', 'AUDIT-SYNTHETIC')
  await fillField(page, '条款号', '1')
  await fillField(page, '条款标题 (zh-CN)', '合成测试资源要求')
  await saveOverlay(page)
  await expect(formItem(page, '自撰说明 (zh-CN)').locator('.n-form-item-feedback')).toBeVisible()
  await formItem(page, '自撰说明 (zh-CN)')
    .locator('textarea')
    .fill('Synthetic requirement for UI verification only')
  await saveOverlay(page)
  await expect(page.getByText('AUDIT-SYNTHETIC', { exact: true }).first()).toBeVisible()
  await page.goto('/governance/templates')
  await page.getByRole('button', { name: '从本体保存模板' }).click()
  await fillField(page, '机读名', 'AuditTemplate')
  await fillField(page, '来源', 'AUDIT')
  await fillField(page, '中文标签', '审计模板')
  await formItem(page, '依据与说明').locator('textarea').fill('Synthetic test only')
  await selectField(page, '本体', '审计本体 · AuditOntology')
  await saveOverlay(page)
  await expect(page.getByText('模板已保存。').first()).toBeVisible()
  await page.goto('/governance/templates')
  await page
    .locator('tr')
    .filter({ hasText: 'AuditTemplate' })
    .getByRole('button', { name: '核心资源核对' })
    .click()
  await overlay(page).getByLabel('机读名', { exact: true }).fill('AuditCompany')
  await overlay(page).getByLabel('依据条款', { exact: true }).click()
  await pickOption(page, 'AUDIT-SYNTHETIC · 1')
  await overlay(page).getByRole('button', { name: '开始核对' }).click()
  await expect(overlay(page)).toContainText('模板 r1 已包含全部所列核心资源')
  await overlay(page).getByLabel('机读名', { exact: true }).fill('MissingAuditResource')
  await expect(overlay(page)).not.toContainText('已包含全部所列核心资源')
  await overlay(page).getByRole('button', { name: '开始核对' }).click()
  await expect(overlay(page)).toContainText('存在缺失或种类不符的资源')
  await page.screenshot({ path: testInfo.outputPath('core-check.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(overlay(page).getByRole('button', { name: '开始核对' })).toBeInViewport()
  await page.screenshot({ path: testInfo.outputPath('core-check-mobile.png'), fullPage: true })
  await page.setViewportSize({ width: 1440, height: 960 })

  await page.goto('/ontology/entity-types')
  await page.getByRole('button', { name: '卡片', exact: true }).click()
  await page.getByRole('button', { name: 'AuditCompany' }).first().click()
  await page.getByRole('button', { name: '修订下一版' }).click()
  await page.getByRole('button', { name: '确认', exact: true }).click()
  await page.getByRole('button', { name: '编辑', exact: true }).first().click()
  await fillField(page, '中文标签', '审计企业修订')
  await saveOverlay(page)
  await expect(page.getByText('基本信息已保存。')).toBeVisible()
  await page.getByRole('button', { name: '发布', exact: true }).first().click()
  await expect(page.getByRole('button', { name: '修订下一版' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: '审计企业修订', exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('revised-resource.png'), fullPage: true })
  await page.goto('/graph')
  expect(await checkCompanyAttribute(page, 'Audit Company')).toBe(originalGraph)

  await page.goto(`/governance/export?ontology=${ontologyId}&revision=1`)
  const frozen = page.locator('.n-card').filter({ hasText: '本体 r1 的冻结内容' })
  await frozen.getByRole('button', { name: '审计企业 · r1', exact: true }).click()
  await expect(frozen.getByRole('heading', { name: '审计企业', exact: true })).toBeVisible()
  await expect(frozen).not.toContainText('审计企业修订')
  await expect(frozen).toContainText('https://example.org/audit#AuditCompany/Name')
  await frozen.getByRole('button', { name: '数据属性 · 名称', exact: true }).click()
  await expect(frozen.locator('.detail')).toContainText('string')
  await frozen.getByRole('button', { name: 'AuditUniqueName · r1', exact: true }).click()
  await expect(frozen.locator('pre').first()).toContainText('unique_attr')
  await expect(frozen).not.toContainText('此历史版本未保存规则正文')
  await page.reload()
  await expect(frozen.getByRole('button', { name: '审计企业 · r1', exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('frozen-contents.png'), fullPage: true })

  await page.goto('/graph?layout=org_tree')
  await page.getByText('视图语义配置', { exact: true }).click()
  await page.getByLabel('层级关系', { exact: true }).click()
  await pickOption(page, '审计任职 · https://example.org/audit#AuditWorksFor')
  await expect(page.locator('.canvas-scroll .node')).toHaveCount(2)
  await expect(page.locator('.canvas-scroll .edge')).toHaveCount(1)
  await page.getByPlaceholder('输入模板名称', { exact: true }).fill('AuditHierarchy')
  await page.getByRole('button', { name: '保存当前视图', exact: true }).click()
  await expect(page).toHaveURL(/template=\d+/)
  await page.reload()
  await page.getByText('视图语义配置', { exact: true }).click()
  await expect(page.getByLabel('层级关系', { exact: true })).toContainText('审计任职')
  await expect(page.locator('.canvas-scroll .node')).toHaveCount(2)
  await expect(page.locator('.canvas-scroll .edge')).toHaveCount(1)
  await page.screenshot({ path: testInfo.outputPath('semantic-hierarchy.png'), fullPage: true })
  await page.locator('.canvas-scroll').screenshot({
    path: testInfo.outputPath('semantic-hierarchy-canvas.png'),
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.locator('.mobile-backdrop').click({ position: { x: 350, y: 300 } })
  await expect(page.getByLabel('层级关系', { exact: true })).toBeVisible()
  await page.screenshot({
    path: testInfo.outputPath('semantic-hierarchy-mobile.png'),
    fullPage: true,
  })
  await page.setViewportSize({ width: 1440, height: 960 })
  await page.goto('/system/audit-logs')
  const assetAudit = page.locator('.asset-audit')
  await assetAudit.getByLabel('操作', { exact: true }).click()
  await pickOption(page, '切换当前图谱')
  await assetAudit.getByRole('button', { name: '搜索', exact: true }).click()
  await expect(assetAudit.locator('tbody tr')).toHaveCount(1)
  await expect(assetAudit.locator('tbody')).toContainText('切换当前图谱')
  await expect(assetAudit.locator('tbody')).toContainText('成功')
  await page.screenshot({ path: testInfo.outputPath('asset-audit.png'), fullPage: true })
})
