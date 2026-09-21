import type { AxiosInstance } from 'axios'
import axios from 'axios'

const http: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

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
