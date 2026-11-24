import { expect, test } from '@playwright/test'

import { ensureAdmin, loginAsAdmin } from '../../../../../e2e/admin.ts'
function overlay(page) {
  return page.getByRole('dialog').last()
}
function formItem(page, label) {
  return page.locator('.ui-field').filter({ hasText: label }).first()
}
function modalFormItem(page, label) {
  return overlay(page).locator('.ui-field').filter({ hasText: label }).first()
}
async function pickOption(page, label) {
  await page.getByRole('option', { name: label, exact: true }).click()
}
async function logout(page) {
  await page.getByRole('button', { name: '\u7528\u6237\u83DC\u5355' }).click()
  await page.getByRole('menuitem', { name: '\u9000\u51FA\u767B\u5F55', exact: true }).click()
  await page.getByRole('button', { name: '\u786E\u8BA4', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
}
test('account profile, admin user lifecycle, reset link and password change', async ({ page }) => {
  await ensureAdmin(page)
  await loginAsAdmin(page)
  const stamp = Date.now().toString().slice(-6)
  const displayName = `E2E\u7BA1\u7406\u5458${stamp}`
  await page.goto('/account/profile')
  await formItem(page, '\u5C55\u793A\u540D\u79F0').locator('input').fill(displayName)
  await page.getByRole('button', { name: '\u4FDD\u5B58' }).click()
  await expect(page.getByText('\u8D44\u6599\u5DF2\u4FDD\u5B58', { exact: true })).toBeVisible()
  await page.reload()
  await expect(formItem(page, '\u5C55\u793A\u540D\u79F0').locator('input')).toHaveValue(displayName)
  const username = `e2eacct${stamp}`
  const email = `${username}@example.org`
  const initialPassword = 'E2E-Initial-Password-2026!'
  await page.goto('/system/users')
  await page.getByRole('button', { name: '\u65B0\u5EFA\u7528\u6237' }).click()
  await modalFormItem(page, '\u7528\u6237\u540D').locator('input').fill(username)
  await modalFormItem(page, '\u90AE\u7BB1').locator('input').fill(email)
  await modalFormItem(page, '\u5BC6\u7801').locator('input').fill(initialPassword)
  await modalFormItem(page, '\u5C55\u793A\u540D\u79F0')
    .locator('input')
    .fill(`E2E\u8D26\u53F7${stamp}`)
  await modalFormItem(page, '\u89D2\u8272').getByRole('combobox').click()
  await pickOption(page, '\u7F16\u8F91\u8005')
  await overlay(page).getByRole('button', { name: '\u521B\u5EFA' }).click()
  await expect(page.getByText('\u7528\u6237\u5DF2\u521B\u5EFA', { exact: true })).toBeVisible()
  await page
    .getByPlaceholder('\u6309\u7528\u6237\u540D\u6216\u90AE\u7BB1\u641C\u7D22')
    .fill(username)
  await page
    .locator('.users-page')
    .getByRole('button', { name: '\u641C\u7D22', exact: true })
    .click()
  const row = page.locator('tr').filter({ hasText: username }).first()
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: '\u7F16\u8F91' }).click()
  await modalFormItem(page, '\u89D2\u8272').getByRole('combobox').click()
  await pickOption(page, '\u53EA\u8BFB')
  await overlay(page).getByRole('button', { name: '\u4FDD\u5B58' }).click()
  await expect(page.getByText('\u7528\u6237\u5DF2\u66F4\u65B0', { exact: true })).toBeVisible()
  await expect(row.getByText('\u53EA\u8BFB')).toBeVisible()
  await row.getByRole('button', { name: '\u91CD\u7F6E\u94FE\u63A5' }).click()
  const resetUrl = await overlay(page).locator('input').inputValue()
  expect(resetUrl).toContain('/reset-password?token=')
  await overlay(page).locator('.ui-overlay-close').click()
  await logout(page)
  const resetPassword = 'E2E-Reset-Password-2026!'
  await page.goto(resetUrl)
  await formItem(page, '\u65B0\u5BC6\u7801').locator('input').fill(resetPassword)
  await formItem(page, '\u786E\u8BA4\u5BC6\u7801').locator('input').fill(resetPassword)
  await page.getByRole('button', { name: '\u786E\u8BA4\u91CD\u7F6E' }).click()
  await expect(page).toHaveURL(/\/login$/)
  await page
    .getByPlaceholder('\u7528\u6237\u540D\u6216\u90AE\u7BB1', { exact: true })
    .fill(username)
  await page.getByPlaceholder('\u8BF7\u8F93\u5165\u5BC6\u7801', { exact: true }).fill(resetPassword)
  await page.getByRole('button', { name: '\u767B\u5F55', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  const changedPassword = 'E2E-Changed-Password-2026!'
  await page.goto('/account/security')
  await formItem(page, '\u5F53\u524D\u5BC6\u7801').locator('input').fill(resetPassword)
  await formItem(page, '\u65B0\u5BC6\u7801').locator('input').fill(changedPassword)
  await formItem(page, '\u786E\u8BA4\u5BC6\u7801').locator('input').fill(changedPassword)
  await page.getByRole('button', { name: '\u4FEE\u6539\u5BC6\u7801' }).click()
  await expect(
    page.getByText(
      '\u5BC6\u7801\u5DF2\u66F4\u65B0\uFF0C\u5176\u4ED6\u8BBE\u5907\u4E0A\u7684\u767B\u5F55\u5DF2\u5931\u6548',
    ),
  ).toBeVisible()
  await logout(page)
  await page
    .getByPlaceholder('\u7528\u6237\u540D\u6216\u90AE\u7BB1', { exact: true })
    .fill(username)
  await page
    .getByPlaceholder('\u8BF7\u8F93\u5165\u5BC6\u7801', { exact: true })
    .fill(changedPassword)
  await page.getByRole('button', { name: '\u767B\u5F55', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
})
