import { http } from '@/api/client'
import type { components } from '@/api/schema'

type S = components['schemas']
export type DatasourceBrief = S['DatasourceBrief']
export type DatasourceOut = S['DatasourceOut']
export type Datasource = DatasourceOut
export type DatasourceCreate = S['DatasourceCreate']
export type DatasourceInput = DatasourceCreate
export type DatasourceUpdate = S['DatasourceUpdate']
export type TestConnectionRequest = S['TestConnectionRequest']
export type DatasourceTestInput = TestConnectionRequest
export type TestConnectionResponse = S['TestConnectionResponse']
export type DatasourceTestResult = TestConnectionResponse
export type MetadataSnapshotOut = S['MetadataSnapshotOut']
export type MetadataSnapshot = MetadataSnapshotOut
export type MetadataSnapshotBrief = S['MetadataSnapshotBrief']
export type TableReferenceResponse = S['TableReferenceResponse']
export type TableReferences = TableReferenceResponse
export type PreviewRequest = S['PreviewRequest']
export type PreviewResponse = S['PreviewResponse']

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
  /** 用库里保存的参数与凭据测试连接，结果落库到 status。 */
  testStored: (id: number, signal?: AbortSignal) =>
    http
      .post<DatasourceTestResult>(`/datasources/${id}/test-connection`, undefined, { signal })
      .then((r) => r.data),
  /** 更新连接信息（改名/换参数/换凭据）；参数与凭据留空即保持不变。 */
  update: (id: number, payload: DatasourceUpdate) =>
    http.put<Datasource>(`/datasources/${id}`, payload).then((r) => r.data),
  remove: (id: number) => http.delete(`/datasources/${id}`).then(() => undefined),
  preview: (payload: PreviewRequest, signal?: AbortSignal) =>
    http.post<PreviewResponse>('/datasources/preview', payload, { signal }).then((r) => r.data),
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
