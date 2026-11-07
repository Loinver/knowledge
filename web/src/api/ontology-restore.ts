import { http } from '@/api/client'
import type { components } from '@/api/schema'

type S = components['schemas']
export type RestorePreview = S['OntologyRestorePreview']
export type RestoreInput = S['OntologyImportPreviewRequest']
export type RestoreResult = S['OntologyRestoreResult']

export const ontologyRestoreApi = {
  preview: (payload: RestoreInput, signal?: AbortSignal) =>
    http
      .post<RestorePreview>('/ontologies/import/restore-preview', payload, { signal })
      .then((response) => response.data),
  apply: (payload: S['OntologyRestoreRequest'], signal?: AbortSignal) =>
    http
      .post<RestoreResult>('/ontologies/import/restore', payload, { signal })
      .then((response) => response.data),
}
