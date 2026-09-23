import { http } from '@/api/client'
import type { components } from '@/api/schema'

type S = components['schemas']

export type Ontology = S['OntologyBrief']
export type OntologyDetail = S['OntologyOut']
export type OntologyRef = S['OntologyRefOut']
export type OntologyConflict = S['ConflictInfo']
export type CanvasLayout = S['CanvasLayoutOut']
export type OntologyRuleRef = S['OntologyRuleOut']

/** 画布位置：`{ [资源 id]: { x, y } }`。拖动只改这个，不产生语义版本。 */
export type CanvasPositions = Record<string, { x: number; y: number }>

const base = '/ontologies'

export const ontologyApi = {
  list: (params: { q?: string; page?: number; page_size?: number } = {}, signal?: AbortSignal) =>
    http
      .get<Ontology[]>(base, { params: { page: 1, page_size: 100, ...params }, signal })
      .then((r) => r.data),

  get: (id: number, signal?: AbortSignal) =>
    http.get<OntologyDetail>(`${base}/${id}`, { signal }).then((r) => r.data),

  create: (payload: S['OntologyCreate']) =>
    http.post<OntologyDetail>(base, payload).then((r) => r.data),

  /** 装配引用的资源。实体类型是画布节点，对象属性是画布连线。 */
  refs: (id: number, signal?: AbortSignal) =>
    http.get<OntologyRef[]>(`${base}/${id}/refs`, { signal }).then((r) => r.data),

  addRef: (id: number, resourceId: number, pinnedRevision?: number) =>
    http
      .post<OntologyRef>(`${base}/${id}/refs`, {
        resource_id: resourceId,
        pinned_revision: pinnedRevision ?? null,
      })
      .then((r) => r.data),

  removeRef: (id: number, refId: number) => http.delete(`${base}/${id}/refs/${refId}`),

  /** 同资源不同修订号被同时引用时的冲突清单。 */
  conflicts: (id: number, signal?: AbortSignal) =>
    http.get<OntologyConflict[]>(`${base}/${id}/conflicts`, { signal }).then((r) => r.data),

  rules: (id: number, signal?: AbortSignal) =>
    http.get<OntologyRuleRef[]>(`${base}/${id}/rules`, { signal }).then((r) => r.data),

  getCanvas: (id: number, signal?: AbortSignal) =>
    http.get<CanvasLayout>(`${base}/${id}/canvas`, { signal }).then((r) => r.data),

  saveCanvas: (id: number, positions: CanvasPositions) =>
    http.put<CanvasLayout>(`${base}/${id}/canvas`, { positions }).then((r) => r.data),

  publish: (id: number) => http.post(`${base}/${id}/publish`).then((r) => r.data),
}
