import type { AxiosError } from 'axios'

import { http } from '@/api/client'
import type { components, operations } from '@/api/schema'

type S = components['schemas']

export type Ontology = S['OntologyBrief']
export type OntologyDetail = S['OntologyOut']
export type OntologyUpdate = S['OntologyUpdate']
export type OntologyRef = S['OntologyRefOut']
export type OntologyConflict = S['ConflictInfo']
export type CanvasLayout = S['CanvasLayoutOut']
export type OntologyRuleRef = S['OntologyRuleOut']
export type OntologyExportFormat = S['OntologyExportFormat']
export type OntologyListQuery = NonNullable<
  operations['list_onto_api_v1_ontologies_get']['parameters']['query']
>
export type OntologyExportQuery = NonNullable<
  operations['export_onto_endpoint_api_v1_ontologies__ontology_id__export_get']['parameters']['query']
>

/** 画布位置：`{ [资源 id]: { x, y } }`。拖动只改这个，不产生语义版本。 */
export type CanvasPositions = Record<string, { x: number; y: number }>

async function readExportError(blob: Blob) {
  try {
    const detail: unknown = JSON.parse(await blob.text())
    if (
      detail &&
      typeof detail === 'object' &&
      'code' in detail &&
      typeof detail.code === 'string' &&
      detail.code !== 'KG.OK'
    ) {
      return detail
    }
  } catch {
    // Non-JSON bodies keep the original HTTP error.
  }
  return null
}

const base = '/ontologies'

export const ontologyApi = {
  list: (params: OntologyListQuery = {}, signal?: AbortSignal) =>
    http
      .get<Ontology[]>(base, { params: { page: 1, page_size: 100, ...params }, signal })
      .then((r) => r.data),

  get: (id: number, signal?: AbortSignal) =>
    http.get<OntologyDetail>(`${base}/${id}`, { signal }).then((r) => r.data),

  export: async (id: number, params: OntologyExportQuery, signal?: AbortSignal) => {
    try {
      const { data } = await http.get<Blob>(`${base}/${id}/export`, {
        params,
        responseType: 'blob',
        signal,
      })
      if (data.type.split(';')[0]?.trim() === 'application/json') {
        const error = await readExportError(data)
        if (error) throw error
      }
      return data
    } catch (err) {
      const body = (err as AxiosError<Blob>)?.response?.data
      if (body instanceof Blob) {
        const error = await readExportError(body)
        if (error) throw error
      }
      throw err
    }
  },

  create: (payload: S['OntologyCreate']) =>
    http.post<OntologyDetail>(base, payload).then((r) => r.data),

  update: (id: number, payload: OntologyUpdate, editRevision?: number) =>
    http
      .put<OntologyDetail>(`${base}/${id}`, {
        ...payload,
        ...(editRevision === undefined ? {} : { if_edit_match: editRevision }),
      })
      .then((r) => r.data),

  /** 装配引用的资源。实体类型是画布节点，对象属性是画布连线。 */
  refs: (id: number, signal?: AbortSignal) =>
    http.get<OntologyRef[]>(`${base}/${id}/refs`, { signal }).then((r) => r.data),

  addRef: (id: number, resourceId: number, pinnedRevision?: number, editRevision?: number) =>
    http
      .post<OntologyRef>(`${base}/${id}/refs`, {
        resource_id: resourceId,
        pinned_revision: pinnedRevision ?? null,
        if_edit_match: editRevision,
      })
      .then((r) => r.data),

  removeRef: (id: number, refId: number, editRevision?: number) =>
    http.delete(`${base}/${id}/refs/${refId}`, {
      headers: { 'If-Edit-Match': editRevision },
    }),

  /** 同资源不同修订号被同时引用时的冲突清单。 */
  conflicts: (id: number, signal?: AbortSignal) =>
    http.get<OntologyConflict[]>(`${base}/${id}/conflicts`, { signal }).then((r) => r.data),

  rules: (id: number, signal?: AbortSignal) =>
    http.get<OntologyRuleRef[]>(`${base}/${id}/rules`, { signal }).then((r) => r.data),

  getCanvas: (id: number, signal?: AbortSignal) =>
    http.get<CanvasLayout>(`${base}/${id}/canvas`, { signal }).then((r) => r.data),

  saveCanvas: (id: number, positions: CanvasPositions) =>
    http.put<CanvasLayout>(`${base}/${id}/canvas`, { positions }).then((r) => r.data),

  publish: (id: number, editRevision?: number) =>
    http
      .post(`${base}/${id}/publish`, undefined, {
        headers: { 'If-Edit-Match': editRevision },
      })
      .then((r) => r.data),
}
