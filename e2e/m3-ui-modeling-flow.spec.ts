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
  await page.getByLabel('账号或邮箱').fill(ADMIN.account)
  await page.getByLabel('密码', { exact: true }).fill(ADMIN.password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
}

/** naive-ui 的下拉选项浮层；按文本挑一项。 */
async function pickOption(page: Page, label: string): Promise<void> {
  await page.locator('.n-base-select-option').filter({ hasText: label }).first().click()
}

async function createNamespace(
  page: Page,
  prefix: string,
  iri: string,
  label: string,
): Promise<void> {
  await page.goto('/ontology/namespaces')
  await page.getByRole('button', { name: '登记命名空间' }).click()
  await page.getByLabel('前缀').fill(prefix)
  await page.getByLabel('命名空间 IRI').fill(iri)
  await page.getByLabel('中文标签').fill(label)
  await page.getByRole('button', { name: '保存' }).click()
  await expect(page.getByText(`命名空间 ${prefix} 已登记。`)).toBeVisible()
  await expect(page.getByText(iri).first()).toBeVisible()
}

async function createEntityType(
  page: Page,
  name: string,
  label: string,
  namespace: string,
): Promise<void> {
  await page.goto('/ontology/entity-types')
  await page.getByRole('button', { name: '新建实体类型' }).click()
  await page.getByLabel('机读名').fill(name)
  await page.getByLabel('命名空间').click()
  await pickOption(page, namespace)
  await page.getByLabel('中文标签').fill(label)
  await page.getByRole('button', { name: '保存' }).click()
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
  await page.getByRole('button', { name: '添加属性' }).click()
  await page.getByLabel('机读名').fill(propName)
  await page.getByLabel('中文标签').fill(propLabel)
  await page.getByRole('button', { name: '保存' }).click()
  await expect(page.getByText(propLabel).first()).toBeVisible()
}

async function createRelationType(
  page: Page,
  name: string,
  label: string,
  namespace: string,
  domain: string,
  range: string,
): Promise<void> {
  await page.goto('/ontology/relation-types')
  await page.getByRole('button', { name: '新建关系类型' }).click()
  await page.getByLabel('机读名').fill(name)
  await page.getByLabel('命名空间').click()
  await pickOption(page, namespace)
  await page.getByLabel('中文标签').fill(label)
  await page.getByLabel('定义域').click()
  await pickOption(page, domain)
  await page.getByLabel('值域').click()
  await pickOption(page, range)
  await page.getByRole('button', { name: '保存' }).click()
  await expect(page.getByText(name, { exact: true }).first()).toBeVisible()
}

async function createDomain(page: Page, name: string, iri: string, label: string): Promise<void> {
  await page.goto('/ontology/domains')
  await page.getByRole('button', { name: '新建业务域' }).click()
  await page.getByLabel('机读名').fill(name)
  await page.getByLabel('IRI').fill(iri)
  await page.getByLabel('中文标签').fill(label)
  await page.getByRole('button', { name: '保存' }).click()
  await expect(page.getByText(name, { exact: true }).first()).toBeVisible()
}

// 未验证的草稿：默认跳过，理由与解除步骤见文件头。跑绿之后再删掉本行。
test.skip(process.env.KG_E2E_UI_ONLY !== '1', '未验证草稿：需在机器空闲时显式开启')

test('建模链全程走界面：命名空间 → 实体类型 → 关系类型 → 业务域', async ({ page }) => {
  seedAdmin()
  const pageErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))

  await loginAsAdmin(page)

  const stamp = Date.now().toString().slice(-6)
  const prefix = `uie${stamp}`
  const namespaceLabel = `界面命名空间${stamp}`
  await createNamespace(page, prefix, `https://example.org/${prefix}#`, namespaceLabel)

  // 两个实体类型：关系类型需要一对定义域/值域
  await createEntityType(page, `UiEmployee${stamp}`, `界面员工${stamp}`, namespaceLabel)
  await createEntityType(page, `UiDepartment${stamp}`, `界面部门${stamp}`, namespaceLabel)

  // 类型 id 从详情页 URL 拿：列表卡片点击进入详情，全程不碰 API
  await page.goto('/ontology/entity-types')
  await page.getByText(`UiEmployee${stamp}`, { exact: true }).first().click()
  await expect(page).toHaveURL(/\/ontology\/entity-types\/\d+/)
  const typeId = Number(/entity-types\/(\d+)/.exec(page.url())![1])
  await addDataProperty(page, typeId, 'hireDate', `入职日期${stamp}`)

  await createRelationType(
    page,
    `UiWorksIn${stamp}`,
    `界面就职于${stamp}`,
    namespaceLabel,
    `界面员工${stamp}`,
    `界面部门${stamp}`,
  )

  await createDomain(
    page,
    `UiDomain${stamp}`,
    `urn:knowledge:domain:ui${stamp}`,
    `界面业务域${stamp}`,
  )
  // 把三个资源挂进业务域并发布
  for (const member of [`界面员工${stamp}`, `界面部门${stamp}`, `界面就职于${stamp}`]) {
    await page.getByPlaceholder('添加成员').click()
    await pickOption(page, member)
    await page.getByRole('button', { name: '添加成员' }).click()
    await expect(page.getByText(member).first()).toBeVisible()
  }
  await page.getByRole('button', { name: '发布', exact: true }).click()
  await expect(page.getByText('已发布').first()).toBeVisible()

  expect(pageErrors, '界面操作不应产生未捕获的前端错误').toEqual([])
})
