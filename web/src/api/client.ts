import type { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import axios from 'axios'

import type { TokenPair } from '@/api/tokens'
import {
  getAccessToken,
  getRefreshToken,
  getSessionGeneration,
  getTokenPair,
  hasSession,
  invalidateTokens,
  storeTokens,
} from '@/api/tokens'

declare module 'axios' {
  interface AxiosRequestConfig {
    _sessionGeneration?: string
  }
}

export const http: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

/** 后端统一响应外壳：成功 { code: 'KG.OK', message, data } */
export interface ApiEnvelope<T = unknown> {
  code: string
  message: string
  data: T
  params?: Record<string, unknown>
}

export const OK_CODE = 'KG.OK'

/** 失败响应与成功同构，额外带 params 供 i18n 占位替换，data 固定为 null */
export interface ApiError {
  code: string
  message: string
  params: Record<string, unknown>
  data?: null
  status?: number
}

function isEnvelope(body: unknown): body is ApiEnvelope {
  return (
    typeof body === 'object' &&
    body !== null &&
    'code' in body &&
    'data' in body &&
    typeof (body as { code: unknown }).code === 'string'
  )
}

/** 单次重放标记：避免 refresh 失败后无限重试 */
interface RetriableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean
  _accessToken?: string | null
}

/**
 * 这些接口的 401 表示「凭据无效」，不能拿 refresh token 去续期：
 * 登录失败要如实报错，换令牌的接口自身续期会递归。
 *
 * 其余接口（含 `/auth/me`）的 401 都可以先尝试续期——刷新页面时
 * access token 可能刚过期，靠这一次续期把登录态接回来。
 */
const NO_RENEW_PATHS = ['/auth/refresh', '/auth/login', '/auth/register']

function isRenewable(config?: RetriableConfig): boolean {
  const url = config?.url ?? ''
  return !NO_RENEW_PATHS.some((path) => url.startsWith(path))
}

http.interceptors.request.use(
  (config: RetriableConfig) => {
    config._sessionGeneration ??= getSessionGeneration()
    if (config._sessionGeneration !== getSessionGeneration()) throw sessionChanged()
    const token = getAccessToken(config._sessionGeneration)
    config._accessToken = token
    if (token) config.headers.set('Authorization', `Bearer ${token}`)
    return config
  },
  (error: unknown) => {
    throw error
  },
  // logout 发出时捕获凭据，然后可以立即清除本地身份。
  { synchronous: true },
)

let refreshing: { generation: string; promise: Promise<TokenPair> } | null = null

function sessionChanged() {
  return { code: '', message: 'Session changed', params: {}, data: null }
}

/**
 * 认证失效回调：由应用启动处（`main.ts`）注册，避免 client 直接依赖路由/页面。
 * 未注册时（如单测、SSR）只清本地凭据，不做跳转。
 */
let unauthorizedHandler: (() => void) | null = null

export function registerUnauthorizedHandler(handler: () => void): void {
  unauthorizedHandler = handler
}

function handleUnauthorized(generation: string, accessToken: string | null | undefined): void {
  invalidateTokens(generation, accessToken)
  if (generation === getSessionGeneration() && !hasSession()) unauthorizedHandler?.()
}

/**
 * 401 时用 refresh token 换新 access token；并发请求共用同一次刷新。
 *
 * 必须走 `http` 而不是原生 axios：后端所有响应都包在 `{code, message, data}`
 * 外壳里，只有经过下面的响应拦截器解包，`response.data` 才是 `TokenPair`。
 * 走原生 axios 会把整个外壳当成 `TokenPair` 存进 localStorage，
 * 结果是 `Bearer undefined` —— 续期变成掉登录态。
 */
async function refreshTokens(failedAccess: string | null | undefined): Promise<TokenPair> {
  const generation = getSessionGeneration()
  if (refreshing?.generation === generation) return refreshing.promise
  const renew = async (): Promise<TokenPair> => {
    const previous = getTokenPair(generation)
    if (!previous) throw sessionChanged()
    if (previous.access_token !== failedAccess) return previous
    try {
      const response = await http.post<TokenPair>(
        '/auth/refresh',
        {
          refresh_token: previous.refresh_token,
        },
        { _sessionGeneration: generation },
      )
      if (!storeTokens(response.data, generation)) throw sessionChanged()
      return response.data
    } catch (error) {
      const status = (error as { status?: number })?.status
      if (status === 401 || status === 403) {
        const current = getTokenPair(generation)
        if (current && current.refresh_token !== previous.refresh_token) return current
        handleUnauthorized(generation, previous.access_token)
      }
      throw error
    }
  }
  const locks = typeof navigator === 'undefined' ? undefined : navigator.locks
  const promise = (locks ? locks.request(`kg-refresh:${generation}`, renew) : renew()).finally(
    () => {
      if (refreshing?.promise === promise) refreshing = null
    },
  )
  refreshing = { generation, promise }
  return promise
}

http.interceptors.response.use(
  (res) => {
    // 解包统一响应外壳：业务侧继续用 res.data 拿 payload；
    // 文件下载等 blob 响应不是 JSON 外壳，原样透传。
    if (isEnvelope(res.data)) {
      res.data = res.data.data
    }
    return res
  },
  async (err: AxiosError) => {
    const config = err.config as RetriableConfig | undefined
    const status = err.response?.status
    const renewable = isRenewable(config)
    const generation = config?._sessionGeneration

    if (
      status === 401 &&
      config &&
      generation === getSessionGeneration() &&
      !config._retried &&
      renewable &&
      getRefreshToken()
    ) {
      config._retried = true
      let tokens: TokenPair
      try {
        tokens = await refreshTokens(config._accessToken)
      } catch (refreshError) {
        return Promise.reject(refreshError)
      }
      if (generation !== getSessionGeneration()) {
        return Promise.reject({ code: '', message: 'Session changed', params: {}, data: null })
      }
      config.headers.set('Authorization', `Bearer ${tokens.access_token}`)
      return http.request(config)
    } else if (status === 401 && renewable && generation !== undefined) {
      handleUnauthorized(generation, config?._accessToken)
    }

    const data = err.response?.data as ApiError | undefined
    if (data?.code) {
      return Promise.reject({ ...data, status })
    }
    // 没有统一外壳的失败（断网、超时、网关错误）归一成同一形状，且**不带 code**，
    // 交给 useApiError 走 errors.network 兜底。不能原样抛 AxiosError：它的
    // `code`（ERR_BAD_RESPONSE / ECONNABORTED …）会被错误翻译层当成业务码，
    // 渲染成「未知错误：ERR_BAD_RESPONSE」——那是 axios 的内部标识，不该给用户看。
    return Promise.reject({
      code: '',
      message: err.message,
      params: { status: status ?? 0 },
      data: null,
      status,
    })
  },
)
