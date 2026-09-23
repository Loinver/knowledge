import { http } from '@/api/client'
import type { components } from '@/api/schema'

type S = components['schemas']

export type Datasource = S['DatasourceBrief']
export type MetadataSnapshot = S['MetadataSnapshotOut']
export type PreviewRequest = S['PreviewRequest']
export type PreviewResult = S['PreviewResponse']

export const samplePreviewApi = {
  listDatasources: (signal?: AbortSignal) =>
    http.get<Datasource[]>('/datasources', { signal }).then((response) => response.data),
  latestMetadata: (datasourceId: number, signal?: AbortSignal) =>
    http
      .get<MetadataSnapshot>(`/datasources/${datasourceId}/metadata/latest`, { signal })
      .then((response) => response.data),
  captureMetadata: (datasourceId: number) =>
    http
      .post<MetadataSnapshot>(`/datasources/${datasourceId}/metadata/capture`)
      .then((response) => response.data),
  preview: (request: PreviewRequest, signal?: AbortSignal) =>
    http.post<PreviewResult>('/datasources/preview', request, { signal }).then((r) => r.data),
}
