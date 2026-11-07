import type { components } from '@/api/schema'

/**
 * token 的本地存取。
 *
 * 单独成模块是为了打断循环依赖：`client.ts` 需要在请求拦截器里读 token，
 * 而 `auth.ts` 又要用 `client.ts` 的 http 实例。
 */

export const ACCESS_KEY = 'kg-access-token'
export const REFRESH_KEY = 'kg-refresh-token'
export const SESSION_KEY = 'kg-session-generation'
const PAIR_PREFIX = 'kg-token-pair:'
const INVALID_PREFIX = 'kg-invalid-access:'

export type TokenPair = components['schemas']['TokenPair']

function store(): Storage | null {
  return typeof localStorage === 'undefined' ? null : localStorage
}

type TokenListener = () => void

const listeners = new Set<TokenListener>()
let fallbackGeneration = 'initial'

/** 身份边界代次；普通 refresh 轮转仍属于同一会话。 */
export function getSessionGeneration(): string {
  return store()?.getItem(SESSION_KEY) ?? fallbackGeneration
}

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
  if (listeners.size === 0 && typeof window !== 'undefined') {
    window.addEventListener('storage', onStorage)
  }
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
    if (listeners.size === 0 && typeof window !== 'undefined') {
      window.removeEventListener('storage', onStorage)
    }
  }
}

function onStorage(event: StorageEvent): void {
  if (
    event.storageArea === store() &&
    (event.key === null ||
      event.key.startsWith(PAIR_PREFIX) ||
      event.key.startsWith(INVALID_PREFIX) ||
      [ACCESS_KEY, REFRESH_KEY, SESSION_KEY].includes(event.key))
  ) {
    emitTokensChanged()
  }
}

function emitTokensChanged(): void {
  for (const listener of [...listeners]) listener()
}

export function getTokenPair(generation = getSessionGeneration()): TokenPair | null {
  if (generation !== getSessionGeneration()) return null
  const target = store()
  const raw = target?.getItem(PAIR_PREFIX + generation)
  let pair: TokenPair | null = null
  try {
    pair = raw ? (JSON.parse(raw) as TokenPair) : null
  } catch {
    return null
  }
  // Existing installations used two keys; never reattach legacy credentials after logout.
  if (!pair && !target?.getItem(SESSION_KEY)) {
    const access = target?.getItem(ACCESS_KEY)
    const refresh = target?.getItem(REFRESH_KEY)
    if (access && refresh) pair = { access_token: access, refresh_token: refresh, expires_in: 0 }
  }
  if (generation !== getSessionGeneration() || !pair?.access_token || !pair.refresh_token)
    return null
  if (target?.getItem(`${INVALID_PREFIX}${generation}:${pair.access_token}`)) return null
  return pair
}

export function getAccessToken(generation = getSessionGeneration()): string | null {
  return getTokenPair(generation)?.access_token ?? null
}

export function getRefreshToken(): string | null {
  return getTokenPair()?.refresh_token ?? null
}

export function storeTokens(tokens: TokenPair, generation = getSessionGeneration()): boolean {
  const target = store()
  if (!target || generation !== getSessionGeneration()) return false
  // A late writer can only touch its own session's key, never a newer identity.
  target.setItem(PAIR_PREFIX + generation, JSON.stringify(tokens))
  if (generation !== getSessionGeneration()) {
    target.removeItem(PAIR_PREFIX + generation)
    return false
  }
  emitTokensChanged()
  return true
}

export function clearTokens(): void {
  const previous = getSessionGeneration()
  fallbackGeneration = crypto.randomUUID()
  const target = store()
  target?.setItem(SESSION_KEY, fallbackGeneration)
  target?.removeItem(PAIR_PREFIX + previous)
  if (target) {
    for (let index = target.length - 1; index >= 0; index--) {
      const key = target.key(index)
      if (key?.startsWith(`${INVALID_PREFIX}${previous}:`)) target.removeItem(key)
    }
  }
  target?.removeItem(ACCESS_KEY)
  target?.removeItem(REFRESH_KEY)
  emitTokensChanged()
}

/** Reject only the credential actually refused by the server; never move the identity pointer. */
export function invalidateTokens(generation: string, accessToken: string | null | undefined): void {
  if (!accessToken) return
  store()?.setItem(`${INVALID_PREFIX}${generation}:${accessToken}`, '1')
  emitTokensChanged()
}

export function hasSession(): boolean {
  return Boolean(getAccessToken())
}
