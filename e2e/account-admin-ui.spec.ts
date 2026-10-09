import { expect, test, type Page } from '@playwright/test'

import { ensureAdmin, loginAsAdmin } from './admin'

function overlay(page: Page) {
  return page.locator('.n-modal:visible').last()
}

function formItem(page: Page, label: string) {
  return page.locator('.n-form-item').filter({ hasText: label }).first()
}

function modalFormItem(page: Page, label: string) {
  return overlay(page).locator('.n-form-item').filter({ hasText: label }).first()
}

async function pickOption(page: Page, label: string): Promise<void> {
  await page
    .locator('.n-base-select-option:visible')
    .filter({ hasText: label })
    .first()
    .waitFor({ state: 'visible' })
  await page.locator('.n-base-select-option:visible').filter({ hasText: label }).first().click()
}

async function logout(page: Page): Promise<void> {
  await page.getByRole('button', { name: '用户菜单' }).click()
  await page.locator('.n-dropdown-option-body__label').filter({ hasText: '退出登录' }).click()
  await page.getByRole('button', { name: '确认', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
}

test('account profile, admin user lifecycle, reset link and password change', async ({ page }) => {
  await ensureAdmin(page)
  await loginAsAdmin(page)

  const stamp = Date.now().toString().slice(-6)
  const displayName = `E2E管理员${stamp}`
  await page.goto('/account/profile')
  await formItem(page, '展示名称').locator('input').fill(displayName)
  await page.getByRole('button', { name: '保存' }).click()
  await expect(page.getByText('资料已保存')).toBeVisible()
  await page.reload()
  await expect(formItem(page, '展示名称').locator('input')).toHaveValue(displayName)

  const username = `e2eacct${stamp}`
  const email = `${username}@example.org`
  const initialPassword = 'E2E-Initial-Password-2026!'
  await page.goto('/system/users')
  await page.getByRole('button', { name: '新建用户' }).click()
  await modalFormItem(page, '用户名').locator('input').fill(username)
  await modalFormItem(page, '邮箱').locator('input').fill(email)
  await modalFormItem(page, '密码').locator('input').fill(initialPassword)
  await modalFormItem(page, '展示名称').locator('input').fill(`E2E账号${stamp}`)
  await modalFormItem(page, '角色').locator('.n-base-selection').click()
  await pickOption(page, '编辑者')
  await overlay(page).getByRole('button', { name: '创建' }).click()
  await expect(page.getByText('用户已创建')).toBeVisible()

  await page.getByPlaceholder('按用户名或邮箱搜索').fill(username)
  await page.getByRole('button', { name: '搜索' }).first().click()
  const row = page.locator('tr').filter({ hasText: username }).first()
  await expect(row).toBeVisible()

  await row.getByRole('button', { name: '编辑' }).click()
  await modalFormItem(page, '角色').locator('.n-base-selection').click()
  await pickOption(page, '只读')
  await overlay(page).getByRole('button', { name: '保存' }).click()
  await expect(page.getByText('用户已更新')).toBeVisible()
  await expect(row.getByText('只读')).toBeVisible()

  await row.getByRole('button', { name: '重置链接' }).click()
  const resetUrl = await overlay(page).locator('input').inputValue()
  expect(resetUrl).toContain('/reset-password?token=')
  await overlay(page).getByRole('button', { name: '关闭' }).click()
  await logout(page)

  const resetPassword = 'E2E-Reset-Password-2026!'
  await page.goto(resetUrl)
  await formItem(page, '新密码').locator('input').fill(resetPassword)
  await formItem(page, '确认密码').locator('input').fill(resetPassword)
  await page.getByRole('button', { name: '确认重置' }).click()
  await expect(page).toHaveURL(/\/login$/)

  await page.getByPlaceholder('用户名或邮箱', { exact: true }).fill(username)
  await page.getByPlaceholder('请输入密码', { exact: true }).fill(resetPassword)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)

  const changedPassword = 'E2E-Changed-Password-2026!'
  await page.goto('/account/security')
  await formItem(page, '当前密码').locator('input').fill(resetPassword)
  await formItem(page, '新密码').locator('input').fill(changedPassword)
  await formItem(page, '确认密码').locator('input').fill(changedPassword)
  await page.getByRole('button', { name: '修改密码' }).click()
  await expect(page.getByText('密码已更新，其他设备上的登录已失效')).toBeVisible()
  await logout(page)

  await page.getByPlaceholder('用户名或邮箱', { exact: true }).fill(username)
  await page.getByPlaceholder('请输入密码', { exact: true }).fill(changedPassword)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
})
