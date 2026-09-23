import type { components } from '@/api/schema'

/**
 * token 的本地存取。
 *
 * 单独成模块是为了打断循环依赖：`client.ts` 需要在请求拦截器里读 token，
 * 而 `auth.ts` 又要用 `client.ts` 的 http 实例。
 */

export const ACCESS_KEY = 'kg-access-token'
export const REFRESH_KEY = 'kg-refresh-token'

export type TokenPair = components['schemas']['TokenPair']

function store(): Storage | null {
  return typeof localStorage === 'undefined' ? null : localStorage
}

type TokenListener = () => void

const listeners = new Set<TokenListener>()

/**
 * 订阅 token 的写入/清空。
 *
 * localStorage 不是响应式数据源，而登录态又必须跟着它走：
 * 401 拦截器（`client.ts`）会直接 `clearTokens()`，Pinia 那边的
 * `user` 可能本来就是 `null`（赋同样的值不会触发更新），
 * 于是 `isAuthenticated` 这类 computed 会一直返回旧值。
 * 由这里显式通知，让依赖它的 computed 重新求值。
 */
export function subscribeTokens(listener: TokenListener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function emitTokensChanged(): void {
  for (const listener of [...listeners]) listener()
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
  emitTokensChanged()
}

export function clearTokens(): void {
  const target = store()
  if (!target) return
  target.removeItem(ACCESS_KEY)
  target.removeItem(REFRESH_KEY)
  emitTokensChanged()
}

export function hasSession(): boolean {
  return Boolean(getAccessToken())
}
