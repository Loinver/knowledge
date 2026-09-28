import { execFileSync } from 'node:child_process'
import { join, resolve } from 'node:path'

import { expect, test, type Page } from '@playwright/test'

/**
 * B-10 第一步：建模链全程走界面（零业务 API）。
 *
 * 既有 m3-browser-flow 的建模部分是 API 预置的（seedOntology / seedMapping），
 * 所以"业务人员能不能只靠界面走到本体"一直没有实测证据。本 spec 专门验证
 * 「登记命名空间 → 建实体类型（含数据属性） → 建关系类型（含端点） → 建业务域
 * （含成员、发布）」这一段。
 *
 * 边界（如实说明，不做超出范围的成功声明）：
 * - 管理员账号由 scripts/seed_admin.py 种入，与既有 spec 一致，属环境准备；
 *   登录本身走界面。除此之外本文件不调用任何业务 API。
 * - 「本体装配」需要在设计器画布上把资源拖进画布，属另一段工作，不在本 spec 范围；
 *   业务域之后的主流程（映射、抽取、图谱、追溯）由 m3-browser-flow 覆盖。
 *
 * ⚠️ 状态：本 spec 尚未在本机跑通过。写完时主机负载 14～69，
 * vite 预转换与沙箱 broker 连续超时（`Broker request timed out`），
 * 浏览器根本渲染不出页面，选择器一次都没被真正验证。因此默认跳过，
 * 避免让 `make test-e2e` 带上一个未验证的哑雷。
 *
 * 取消跳过的步骤（机器空闲时，`uptime` 确认 load < 10）：
 *   1. 删掉下面的 test.skip(...) 这一行；
 *   2. KG_E2E_UI_ONLY=1 不必再传，直接跑：
 *      TMPDIR=$(mktemp -d) NO_PROXY=127.0.0.1,localhost \
 *        env -u CODEBUDDY_SAFE_DELETE_BULK_STATE_DIR -u CODEBUDDY_TOOL_CALL_ID \
 *        ./node_modules/.bin/playwright test e2e/m3-ui-modeling-flow.spec.ts
 *   3. 选择器按实际 DOM 校正后跑绿，再提交。
 */

const ADMIN = { account: 'e2e_admin', password: 'E2E-Admin-Password-2026!' }

function seedAdmin(): void {
  const tempDir = process.env.KG_E2E_TEMP_DIR
  expect(tempDir, 'Playwright config provides an isolated temp directory').toBeTruthy()
  execFileSync(
    resolve('server/.venv/bin/python'),
    [
      resolve('scripts/seed_admin.py'),
      '--username',
      ADMIN.account,
      '--email',
      'e2e_admin@example.org',
      '--password',
      ADMIN.password,
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
}

async function loginAsAdmin(page: Page): Promise<void> {
  await page.goto('/login')
  // 登录表单的 label 没有关联到 input（可访问名来自 placeholder），只能按 placeholder 定位。
  await page.getByPlaceholder('用户名或邮箱', { exact: true }).fill(ADMIN.account)
  await page.getByPlaceholder('请输入密码', { exact: true }).fill(ADMIN.password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
}

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
    .filter({ hasText: label })
    .first()
    .waitFor({ state: 'visible', timeout: 10000 })
  await page.locator('.n-base-select-option:visible').filter({ hasText: label }).first().click()
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
  return overlay(page).locator('.n-form-item').filter({ hasText: label }).first()
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
  await page.getByRole('button', { name: '发布', exact: true }).first().click()
  await expect(page.getByText('已发布').first()).toBeVisible({ timeout: 15000 })
}

/** 发布关系类型：列表页行内发布按钮。 */
async function publishRelationType(page: Page, label: string): Promise<void> {
  await page.goto('/ontology/relation-types')
  // 行内发布按钮的父行包含关系类型名；naive-ui 的 NDataTable 行无 role，按文本定位。
  const row = page.locator('tr').filter({ hasText: label }).first()
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

// 未验证的草稿：默认跳过，理由与解除步骤见文件头。跑绿之后再删掉本行。
test('建模链全程走界面：命名空间 → 实体类型 → 关系类型 → 业务域', async ({ page }) => {
  seedAdmin()
  const pageErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))

  await loginAsAdmin(page)

  const stamp = Date.now().toString().slice(-6)
  const prefix = `uie${stamp}`
  const namespaceLabel = `界面命名空间${stamp}`
  await createNamespace(page, prefix, `https://example.org/${prefix}#`, namespaceLabel)

  // 两个实体类型：关系类型需要一对定义域/值域（命名空间按前缀选）
  await createEntityType(page, `UiEmployee${stamp}`, `界面员工${stamp}`, prefix)
  await createEntityType(page, `UiDepartment${stamp}`, `界面部门${stamp}`, prefix)

  // 类型 id 从详情页 URL 拿：切到卡片视图后点卡片进详情，全程不碰 API。
  // （表格视图的名字单元格不可点，进入详情要走操作列按钮；卡片本身是 button，
  //  可访问名是整张卡片的文本，按子串匹配即可。）
  await page.goto('/ontology/entity-types')
  await page.getByRole('button', { name: '卡片', exact: true }).click()
  await page
    .getByRole('button', { name: `UiEmployee${stamp}` })
    .first()
    .click()
  await expect(page).toHaveURL(/\/ontology\/entity-types\/\d+/)
  const typeId = Number(/entity-types\/(\d+)/.exec(page.url())![1])
  // 属性机读名必须是 PascalCase（小写开头会被表单拒："请填写 PascalCase 属性名与中文标签"）。
  await addDataProperty(page, typeId, 'HireDate', `入职日期${stamp}`)

  // 业务域发布要求成员已有发布版本（版本冻结）：先发布实体类型与关系类型。
  await publishEntityType(page, `UiEmployee${stamp}`)
  await publishEntityType(page, `UiDepartment${stamp}`)

  await createRelationType(
    page,
    `UiWorksIn${stamp}`,
    `界面就职于${stamp}`,
    prefix,
    `界面员工${stamp}`,
    `界面部门${stamp}`,
  )
  await publishRelationType(page, `界面就职于${stamp}`)

  await createDomain(
    page,
    `UiDomain${stamp}`,
    `urn:knowledge:domain:ui${stamp}`,
    `界面业务域${stamp}`,
  )
  // reload 确保成员下拉的类型/关系列表含刚创建并发布的资源
  await page.reload()
  // 成员区在右侧详情面板，只有「已选中某个域」时才渲染；左列表是 NTree。
  await page
    .locator('.n-tree-node-content')
    .filter({ hasText: `界面业务域${stamp}` })
    .first()
    .click()
  for (const member of [`界面员工${stamp}`, `界面部门${stamp}`, `界面就职于${stamp}`]) {
    // NSelect 的 placeholder 在 loading 态不挂在 input 上，直接点触发器更稳。
    await page.locator('.member-select .n-base-selection').click()
    await pickOption(page, member)
    await page.getByRole('button', { name: '添加成员', exact: true }).first().click()
    await expect(page.getByText(member).first()).toBeVisible()
  }
  await page.getByRole('button', { name: '发布', exact: true }).first().click()
  await expect(page.getByText('已发布').first()).toBeVisible()

  expect(pageErrors, '界面操作不应产生未捕获的前端错误').toEqual([])
})
