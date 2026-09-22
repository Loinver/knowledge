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

export interface HealthResponse {
  status: string
  version: string
}

export interface Namespace {
  id: number
  prefix: string
  iri: string
  protected: boolean
  label_i18n: Record<string, string> | null
}

export interface NamespaceCreate {
  prefix: string
  iri: string
  protected?: boolean
  label_i18n?: Record<string, string>
}

export type ResourceKind =
  'ENTITY' | 'DATATYPE_PROP' | 'OBJECT_PROP' | 'ASSOC' | 'NAMESPACE' | 'DOMAIN' | 'ONTOLOGY'
export type ResourceStatus = 'DRAFT' | 'PUBLISHED' | 'ARCHIVED'

export interface DataTypeProp {
  name: string
  label_i18n: Record<string, string> | null
  definition_i18n: Record<string, string> | null
  datatype: string
  enum_dict_id: number | null
  nullable: boolean
  default_value: string | null
}

export interface EntityType {
  id: number
  kind: ResourceKind
  name: string
  iri: string
  namespace_id: number
  label_i18n: Record<string, string> | null
  definition_i18n: Record<string, string> | null
  status: ResourceStatus
  current_revision: number
  data_props: DataTypeProp[]
  parent_ids: number[]
}

export interface EntityTypeBrief {
  id: number
  name: string
  iri: string
  label_i18n: Record<string, string> | null
  status: ResourceStatus
  current_revision: number
}

export interface EntityTypeCreate {
  name: string
  namespace_id: number
  label_i18n: Record<string, string>
  definition_i18n?: Record<string, string>
  parent_ids?: number[]
  data_props?: DataTypeProp[]
}

export interface EntityTypeUpdate {
  label_i18n?: Record<string, string>
  definition_i18n?: Record<string, string>
  parent_ids?: number[]
  data_props?: DataTypeProp[]
  if_match: number
}

export interface RelationTypeBrief {
  id: number
  name: string
  iri: string
  label_i18n: Record<string, string> | null
  status: ResourceStatus
  current_revision: number
}

export interface CardinalitySpec {
  min: number
  max: number
  role_label_i18n?: Record<string, string>
}

export interface EndpointSpec {
  type_id: number
  cardinality: CardinalitySpec
}

export interface OwlFeatures {
  functional: boolean
  symmetric: boolean
  transitive: boolean
  inverse_functional: boolean
}

export interface RelationTypeCreate {
  name: string
  namespace_id: number
  label_i18n: Record<string, string>
  domain_spec: EndpointSpec
  range_spec: EndpointSpec
  owl?: Partial<OwlFeatures>
  enable_attributes?: boolean
}

export interface DomainBrief {
  id: number
  name: string
  iri: string
  label_i18n: Record<string, string> | null
  status: ResourceStatus
  current_revision: number
}

export interface DomainCreate {
  name: string
  iri: string
  label_i18n: Record<string, string>
  definition_i18n?: Record<string, string>
  member_ids?: number[]
}

export interface DomainMember {
  id: number
  domain_id: number
  resource_id: number
  as_ref: boolean
  owner_domain_id: number | null
}

export interface PublishCheckResult {
  member_exists: boolean
  versions_available: boolean
  dependencies_complete: boolean
  no_circular_ref: boolean
  can_publish: boolean
  issues: string[]
}

/** 单次重放标记：避免 refresh 失败后无限重试 */
interface RetriableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean
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

/** 401 时用 refresh token 换新 access token；并发请求共用同一次刷新。 */
async function refreshTokens(): Promise<TokenPair> {
  refreshing ??= axios
    .post<TokenPair>('/api/v1/auth/refresh', { refresh_token: getRefreshToken() })
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
    const isAuthCall = config?.url?.startsWith('/auth/') ?? false

    if (status === 401 && config && !config._retried && !isAuthCall && getRefreshToken()) {
      config._retried = true
      try {
        const tokens = await refreshTokens()
        config.headers.set('Authorization', `Bearer ${tokens.access_token}`)
        return await http.request(config)
      } catch {
        handleUnauthorized()
      }
    } else if (status === 401 && !isAuthCall) {
      handleUnauthorized()
    }

    const data = err.response?.data as ApiError | undefined
    if (data?.code) {
      return Promise.reject({ ...data, status })
    }
    return Promise.reject(err)
  },
)

export const api = {
  health: () => http.get<HealthResponse>('/health').then((r) => r.data),
  namespaces: {
    list: () => http.get<Namespace[]>('/namespaces').then((r) => r.data),
    create: (payload: NamespaceCreate) =>
      http.post<Namespace>('/namespaces', payload).then((r) => r.data),
    remove: (id: number) => http.delete(`/namespaces/${id}`),
  },
  entityTypes: {
    list: (params?: { q?: string; page?: number; page_size?: number }) =>
      http.get<EntityTypeBrief[]>('/entity-types', { params }).then((r) => r.data),
    get: (id: number) => http.get<EntityType>(`/entity-types/${id}`).then((r) => r.data),
    create: (payload: EntityTypeCreate) =>
      http.post<EntityType>('/entity-types', payload).then((r) => r.data),
    update: (id: number, payload: EntityTypeUpdate) =>
      http.put<EntityType>(`/entity-types/${id}`, payload).then((r) => r.data),
    publish: (id: number) => http.post(`/entity-types/${id}/publish`).then((r) => r.data),
  },
  relations: {
    list: (params?: { q?: string; page?: number; page_size?: number }) =>
      http.get<RelationTypeBrief[]>('/relations', { params }).then((r) => r.data),
    create: (payload: RelationTypeCreate) => http.post('/relations', payload).then((r) => r.data),
  },
  domains: {
    list: (params?: { q?: string; page?: number; page_size?: number }) =>
      http.get<DomainBrief[]>('/domains', { params }).then((r) => r.data),
    create: (payload: DomainCreate) => http.post('/domains', payload).then((r) => r.data),
    members: (id: number) => http.get<DomainMember[]>(`/domains/${id}/members`).then((r) => r.data),
    addMember: (id: number, resourceId: number, asRef = false) =>
      http
        .post<DomainMember>(`/domains/${id}/members`, { resource_id: resourceId, as_ref: asRef })
        .then((r) => r.data),
    removeMember: (domainId: number, memberId: number) =>
      http.delete(`/domains/${domainId}/members/${memberId}`),
    publishCheck: (id: number) =>
      http.get<PublishCheckResult>(`/domains/${id}/publish-check`).then((r) => r.data),
    publish: (id: number) => http.post(`/domains/${id}/publish`).then((r) => r.data),
  },
}
