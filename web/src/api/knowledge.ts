import { http } from '@/api/client'
import type { components } from '@/api/schema'

type Schemas = components['schemas']
export type KnowledgeBase = Schemas['KnowledgeBaseOut']
export type KnowledgeDocument = Schemas['KnowledgeDocumentOut']
export type KnowledgeTask = Schemas['KnowledgeTaskOut']
export type KnowledgeHit = Schemas['KnowledgeSearchHit']
export type KnowledgeEvidence = Schemas['KnowledgeEvidenceOut']
export type KnowledgeSearchRequest = Schemas['KnowledgeSearchRequest']
export type KnowledgeGraphLink = Schemas['KnowledgeGraphLinkOut']
export type KnowledgeGraphEvidence = Schemas['KnowledgeGraphEvidenceOut']
export type KnowledgeCapabilities = Schemas['KnowledgeCapabilities']
export type KnowledgeBaseCreate = Schemas['KnowledgeBaseCreate']

export type KnowledgePageQuery = {
  page?: number
  page_size?: number
  q?: string
  sort?: string
  status?: 'active' | 'archived' | 'all'
}

const root = '/knowledge-bases'
const docPath = (id: number, doc: string) => `${root}/${id}/documents/${encodeURIComponent(doc)}`
const match = (revision: number, signal?: AbortSignal) => ({
  headers: { 'If-Match': String(revision) },
  signal,
})

export const knowledgeApi = {
  capabilities: (signal: AbortSignal) =>
    http.get<KnowledgeCapabilities>(`${root}/capabilities`, { signal }).then((r) => r.data),
  page: (params: KnowledgePageQuery, signal: AbortSignal) =>
    http.get<Schemas['KnowledgeBasePage']>(root, { params, signal }).then((r) => r.data),
  get: (id: number, signal: AbortSignal) =>
    http.get<KnowledgeBase>(`${root}/${id}`, { signal }).then((r) => r.data),
  create: (payload: KnowledgeBaseCreate, signal: AbortSignal) =>
    http.post<KnowledgeBase>(root, payload, { signal }).then((r) => r.data),
  update: (
    id: number,
    payload: Schemas['KnowledgeBaseUpdate'],
    revision: number,
    signal: AbortSignal,
  ) =>
    http.put<KnowledgeBase>(`${root}/${id}`, payload, match(revision, signal)).then((r) => r.data),
  archive: (id: number, revision: number, signal: AbortSignal) =>
    http
      .post<KnowledgeBase>(`${root}/${id}/archive`, null, match(revision, signal))
      .then((r) => r.data),
  restore: (id: number, revision: number, signal: AbortSignal) =>
    http
      .post<KnowledgeBase>(`${root}/${id}/restore`, null, match(revision, signal))
      .then((r) => r.data),
  documents: (id: number, params: KnowledgePageQuery, signal: AbortSignal) =>
    http
      .get<Schemas['KnowledgeDocumentPage']>(`${root}/${id}/documents`, { params, signal })
      .then((r) => r.data),
  upload: (id: number, file: File, signal: AbortSignal) =>
    http
      .post<KnowledgeDocument>(`${root}/${id}/documents`, file, {
        signal,
        headers: { 'Content-Type': 'application/octet-stream' },
        params: { filename: file.name, content_type: file.type || 'application/octet-stream' },
      })
      .then((r) => r.data),
  document: (id: number, doc: string, signal: AbortSignal) =>
    http.get<KnowledgeDocument>(docPath(id, doc), { signal }).then((r) => r.data),
  documentAction: (
    id: number,
    doc: string,
    action: 'archive' | 'restore' | 'reprocess',
    revision: number,
    signal: AbortSignal,
  ) =>
    http
      .post<KnowledgeDocument>(`${docPath(id, doc)}/${action}`, null, match(revision, signal))
      .then((r) => r.data),
  tasks: (id: number, doc: string, page: number, signal: AbortSignal) =>
    http
      .get<Schemas['KnowledgeTaskPage']>(`${docPath(id, doc)}/tasks`, {
        signal,
        params: { page, page_size: 10 },
      })
      .then((r) => r.data),
  search: (id: number, payload: KnowledgeSearchRequest, signal: AbortSignal) =>
    http
      .post<Schemas['KnowledgeSearchOut']>(`${root}/${id}/search`, payload, { signal })
      .then((r) => r.data),
  answer: (id: number, payload: KnowledgeSearchRequest, signal: AbortSignal) =>
    http
      .post<Schemas['KnowledgeAnswerOut']>(`${root}/${id}/answer`, payload, { signal })
      .then((r) => r.data),
  evidence: (id: number, chunk: string, signal: AbortSignal) =>
    http
      .get<KnowledgeEvidence>(`${root}/${id}/evidence/${encodeURIComponent(chunk)}`, { signal })
      .then((r) => r.data),
  original: (id: number, doc: string, signal: AbortSignal) =>
    http
      .get<Blob>(`${docPath(id, doc)}/original`, { signal, responseType: 'blob' })
      .then((r) => r.data),
  link: (
    id: number,
    chunk: string,
    payload: Schemas['KnowledgeGraphLinkCreate'],
    revision: number,
    signal: AbortSignal,
  ) =>
    http
      .post<KnowledgeGraphLink>(
        `${root}/${id}/evidence/${encodeURIComponent(chunk)}/links`,
        payload,
        match(revision, signal),
      )
      .then((r) => r.data),
  graphEvidence: (params: Schemas['KnowledgeGraphLinkCreate'], signal: AbortSignal) =>
    http
      .get<KnowledgeGraphEvidence[]>(`${root}/graph-evidence`, { params, signal })
      .then((r) => r.data),
}
