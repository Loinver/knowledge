import type { AxiosInstance } from 'axios'
import axios from 'axios'

const http: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// 统一后端错误体：{ code, params, message }
export interface ApiError {
  code: string
  params: Record<string, unknown>
  message: string
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

export interface IriBuildRequest {
  namespace: string
  name: string
}

export interface IriBuildResponse {
  iri: string
}

export interface IriValidateResponse {
  name: boolean
  namespace: boolean
}

export interface ImpactItem {
  source_id: number
  role: string
  ref_id: number
}

export interface ImpactResponse {
  resource_id: number
  references: ImpactItem[]
}

http.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err?.response?.data) {
      const body = err.response.data as ApiError
      if (body.code) {
        return Promise.reject({ ...body, status: err.response.status })
      }
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
    iriBuild: (payload: IriBuildRequest) =>
      http.get<IriBuildResponse>('/namespaces/iri/build', { params: payload }).then((r) => r.data),
    iriValidate: (name: string, namespace = '') =>
      http
        .get<IriValidateResponse>('/namespaces/iri/validate', { params: { name, namespace } })
        .then((r) => r.data),
    renameImpact: (resourceId: number) =>
      http.get<ImpactResponse>(`/namespaces/iri/impact/${resourceId}`).then((r) => r.data),
  },
}
