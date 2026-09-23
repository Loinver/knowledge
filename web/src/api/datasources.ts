import { http } from '@/api/client'
import type { components } from '@/api/schema'

type S = components['schemas']
export type DatasourceBrief = S['DatasourceBrief']
export type DatasourceOut = S['DatasourceOut']
export type Datasource = DatasourceOut
export type DatasourceCreate = S['DatasourceCreate']
export type DatasourceInput = DatasourceCreate
export type TestConnectionRequest = S['TestConnectionRequest']
export type DatasourceTestInput = TestConnectionRequest
export type TestConnectionResponse = S['TestConnectionResponse']
export type DatasourceTestResult = TestConnectionResponse
export type MetadataSnapshotOut = S['MetadataSnapshotOut']
export type MetadataSnapshot = MetadataSnapshotOut
export type MetadataSnapshotBrief = S['MetadataSnapshotBrief']
export type TableReferenceResponse = S['TableReferenceResponse']
export type TableReferences = TableReferenceResponse

export const datasourcesApi = {
  list: (params: { q?: string } = {}, signal?: AbortSignal) =>
    http.get<DatasourceBrief[]>('/datasources', { params, signal }).then((r) => r.data),
  get: (id: number, signal?: AbortSignal) =>
    http.get<Datasource>(`/datasources/${id}`, { signal }).then((r) => r.data),
  create: (payload: DatasourceInput) =>
    http.post<Datasource>('/datasources', payload).then((r) => r.data),
  testConnection: (payload: DatasourceTestInput, signal?: AbortSignal) =>
    http
      .post<DatasourceTestResult>('/datasources/test-connection', payload, { signal })
      .then((r) => r.data),
  remove: (id: number) => http.delete(`/datasources/${id}`).then(() => undefined),
}

export const metadataApi = {
  latest: (id: number, signal?: AbortSignal) =>
    http
      .get<MetadataSnapshot>(`/datasources/${id}/metadata/latest`, { signal })
      .then((r) => r.data),
  snapshots: (id: number, signal?: AbortSignal) =>
    http
      .get<MetadataSnapshotBrief[]>(`/datasources/${id}/metadata/snapshots`, { signal })
      .then((r) => r.data),
  capture: (id: number) =>
    http.post<MetadataSnapshot>(`/datasources/${id}/metadata/capture`).then((r) => r.data),
  references: (table: string, signal?: AbortSignal) =>
    http
      .get<TableReferences>(
        `/datasources/metadata/tables/${encodeURIComponent(table)}/references`,
        {
          signal,
        },
      )
      .then((r) => r.data),
  get: (id: number, signal?: AbortSignal) =>
    http.get<MetadataSnapshot>(`/datasources/metadata/${id}`, { signal }).then((r) => r.data),
}
