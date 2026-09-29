import type { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import axios from 'axios'

import type { TokenPair } from '@/api/tokens'
import { clearTokens, getAccessToken, getRefreshToken, storeTokens } from '@/api/tokens'

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

http.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) config.headers.set('Authorization', `Bearer ${token}`)
  return config
})

let refreshing: Promise<TokenPair> | null = null

/**
 * 认证失效回调：由应用启动处（`main.ts`）注册，避免 client 直接依赖路由/页面。
 * 未注册时（如单测、SSR）只清本地凭据，不做跳转。
 */
let unauthorizedHandler: (() => void) | null = null

export function registerUnauthorizedHandler(handler: () => void): void {
  unauthorizedHandler = handler
}

function handleUnauthorized(): void {
  clearTokens()
  unauthorizedHandler?.()
}

/**
 * 401 时用 refresh token 换新 access token；并发请求共用同一次刷新。
 *
 * 必须走 `http` 而不是原生 axios：后端所有响应都包在 `{code, message, data}`
 * 外壳里，只有经过下面的响应拦截器解包，`response.data` 才是 `TokenPair`。
 * 走原生 axios 会把整个外壳当成 `TokenPair` 存进 localStorage，
 * 结果是 `Bearer undefined` —— 续期变成掉登录态。
 */
async function refreshTokens(): Promise<TokenPair> {
  refreshing ??= http
    .post<TokenPair>('/auth/refresh', { refresh_token: getRefreshToken() })
    .then((response) => {
      const tokens = response.data
      storeTokens(tokens)
      return tokens
    })
    .finally(() => {
      refreshing = null
    })
  return refreshing
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

    if (status === 401 && config && !config._retried && renewable && getRefreshToken()) {
      config._retried = true
      try {
        const tokens = await refreshTokens()
        config.headers.set('Authorization', `Bearer ${tokens.access_token}`)
        return await http.request(config)
      } catch (refreshError) {
        const refreshStatus = (refreshError as { status?: number } | undefined)?.status
        // 只有后端明确拒绝续期（401/403）才认定会话失效；网络抖动、超时
        // 不能清凭据踢登录——那会把在线用户误登出。
        if (refreshStatus === 401 || refreshStatus === 403) {
          handleUnauthorized()
        }
      }
    } else if (status === 401 && renewable) {
      handleUnauthorized()
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
