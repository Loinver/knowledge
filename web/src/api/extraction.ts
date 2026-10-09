import { http } from '@/api/client'
import type { components } from '@/api/schema'

export type ExtractionRun = components['schemas']['ExtractionRunOut']
export type RunStartResponse = components['schemas']['RunStartResponse']
export type ExtractionTask = components['schemas']['ExtractionTaskOut']
export type TaskCreateInput = components['schemas']['TaskCreateRequest']

export const extractionApi = {
  list: (page: number, signal: AbortSignal) =>
    http
      .get<ExtractionRun[]>('/extraction/runs', { params: { page, page_size: 20 }, signal })
      .then((r) => r.data),
  exportRun: (id: number, signal: AbortSignal) =>
    http
      .get<components['schemas']['ExtractionRunExport']>(`/extraction/runs/${id}/export`, {
        signal,
      })
      // JSON-only export: retain the client's normal JSON error-code handling.
      .then((r) => new Blob([JSON.stringify(r.data, null, 2)], { type: 'application/json' })),
  start: (payload: { mapping_revision_id: number; datasource_id: number; namespace: string }) =>
    http.post<RunStartResponse>('/extraction/runs', payload).then((r) => r.data),
  tasks: (page: number, signal?: AbortSignal) =>
    http
      .get<ExtractionTask[]>('/extraction/tasks', {
        params: { page, page_size: 20 },
        signal,
      })
      .then((r) => r.data),
  createTask: (payload: TaskCreateInput) =>
    http.post<ExtractionTask>('/extraction/tasks', payload).then((r) => r.data),
  getTask: (id: number, signal?: AbortSignal) =>
    http.get<ExtractionTask>(`/extraction/tasks/${id}`, { signal }).then((r) => r.data),
  cancelTask: (id: number) =>
    http.post<ExtractionTask>(`/extraction/tasks/${id}/cancel`).then((r) => r.data),
}
