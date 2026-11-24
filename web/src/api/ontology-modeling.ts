import { http } from '@/api/client'
import type { components } from '@/api/schema'

type Schemas = components['schemas']
export type ModelingCapabilities = Schemas['ModelingCapabilities']
export type ModelingCreate = Schemas['ModelingCreate']
export type ModelingProposal = Schemas['ModelingProposalOut']
export type ModelingProposalPage = Schemas['ModelingProposalPage']
export type ModelingCandidate = Schemas['OntologyCandidate']
export type ModelingCandidateUpdate = Schemas['ModelingCandidateUpdate']
export type ModelingValidation = Schemas['ModelingValidationOut']
export type ModelingApply = Schemas['ModelingApply']
export type ModelingApplication = Schemas['ModelingApplyOut']

const root = '/ai/ontology-modeling'
const revisionHeaders = (revision: number) => ({ 'If-Match': String(revision) })

export const ontologyModelingApi = {
  capabilities: (signal?: AbortSignal) =>
    http.get<ModelingCapabilities>(`${root}/capabilities`, { signal }).then((r) => r.data),
  list: (ontologyId: number, page = 1, signal?: AbortSignal) =>
    http
      .get<ModelingProposalPage>(`${root}/proposals`, {
        params: { ontology_id: ontologyId, page, page_size: 20 },
        signal,
      })
      .then((r) => r.data),
  get: (id: string) => http.get<ModelingProposal>(`${root}/proposals/${id}`).then((r) => r.data),
  create: (payload: ModelingCreate, key: string) =>
    http
      .post<ModelingProposal>(`${root}/proposals`, payload, {
        headers: { 'Idempotency-Key': key },
      })
      .then((r) => r.data),
  update: (id: string, revision: number, payload: ModelingCandidateUpdate) =>
    http
      .put<ModelingProposal>(`${root}/proposals/${id}/candidate`, payload, {
        headers: revisionHeaders(revision),
      })
      .then((r) => r.data),
  validate: (id: string, revision: number, candidateDigest: string) =>
    http
      .post<ModelingValidation>(
        `${root}/proposals/${id}/validate`,
        {
          candidate_digest: candidateDigest,
        },
        { headers: revisionHeaders(revision) },
      )
      .then((r) => r.data),
  apply: (id: string, revision: number, payload: ModelingApply, key: string) =>
    http
      .post<ModelingApplication>(`${root}/proposals/${id}/apply`, payload, {
        headers: { ...revisionHeaders(revision), 'Idempotency-Key': key },
      })
      .then((r) => r.data),
  applicationByKey: (key: string) =>
    http
      .get<ModelingApplication | null>(`${root}/applications/by-key`, {
        params: { key },
      })
      .then((r) => r.data),
  discard: (id: string, revision: number) =>
    http
      .post<ModelingProposal>(`${root}/proposals/${id}/discard`, null, {
        headers: revisionHeaders(revision),
      })
      .then((r) => r.data),
}
