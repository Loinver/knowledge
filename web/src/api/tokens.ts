/**
 * token 的本地存取。
 *
 * 单独成模块是为了打断循环依赖：`client.ts` 需要在请求拦截器里读 token，
 * 而 `auth.ts` 又要用 `client.ts` 的 http 实例。
 */

export const ACCESS_KEY = 'kg-access-token'
export const REFRESH_KEY = 'kg-refresh-token'

export interface TokenPair {
  access_token: string
  refresh_token: string
  /** access token 剩余有效秒数 */
  expires_in: number
}

function store(): Storage | null {
  return typeof localStorage === 'undefined' ? null : localStorage
}

export function getAccessToken(): string | null {
  return store()?.getItem(ACCESS_KEY) ?? null
}

export function getRefreshToken(): string | null {
  return store()?.getItem(REFRESH_KEY) ?? null
}

export function storeTokens(tokens: TokenPair): void {
  const target = store()
  if (!target) return
  target.setItem(ACCESS_KEY, tokens.access_token)
  target.setItem(REFRESH_KEY, tokens.refresh_token)
}

export function clearTokens(): void {
  const target = store()
  if (!target) return
  target.removeItem(ACCESS_KEY)
  target.removeItem(REFRESH_KEY)
}

export function hasSession(): boolean {
  return Boolean(getAccessToken())
}
