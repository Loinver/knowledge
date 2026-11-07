import { expect, test } from '@playwright/test'

import { ensureAdmin, loginAsAdmin } from './admin'

test('two real browser tabs share refresh rotation and observe logout', async ({
  page,
  context,
}) => {
  await ensureAdmin(page)
  await loginAsAdmin(page)
  const other = await context.newPage()
  await other.goto('/')
  await expect(other).toHaveURL(/\/$/)
  await Promise.all([page.waitForLoadState('networkidle'), other.waitForLoadState('networkidle')])
  let initial = 0
  let release: () => void = () => {}
  const both = new Promise<void>((resolve) => {
    release = resolve
  })
  let refreshes = 0
  context.on('request', (request) => {
    if (request.url().endsWith('/api/v1/auth/refresh')) refreshes++
  })
  await context.route('**/api/v1/auth/me', async (route) => {
    if (++initial <= 2) {
      if (initial === 2) release()
      await both
      await route.fulfill({
        status: 401,
        json: { code: 'AUTH.TOKEN_EXPIRED', message: '', params: {}, data: null },
      })
    } else await route.continue()
  })
  const requestMe = () =>
    import('/src/api/client.ts').then(({ http }) =>
      http.get('/auth/me').then((response: { data: { id: string } }) => response.data.id),
    )
  const ids = await Promise.all([page.evaluate(requestMe), other.evaluate(requestMe)])
  expect(ids[0]).toBe(ids[1])
  expect(refreshes).toBe(1)
  await page.evaluate(async () => {
    const { useAuthStore } = await import('/src/stores/auth.ts')
    const { pinia } = await import('/src/stores/index.ts')
    await useAuthStore(pinia).logout()
  })
  await expect
    .poll(() =>
      other.evaluate(async () => {
        const { hasSession } = await import('/src/api/tokens.ts')
        return hasSession()
      }),
    )
    .toBe(false)
})
