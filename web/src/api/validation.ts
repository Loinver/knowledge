import { http } from '@/api/client'
import type { components, paths } from '@/api/schema'

type Schemas = components['schemas']
export type ValidationState = Schemas['ValidationState']
// The schema's generic summary dictionary always carries four numeric counts in these views.
export type ValidationSummary = NonNullable<Schemas['ValidationReportOut']['summary']> &
  Record<Lowercase<ValidationState>, number>
export type ValidationReport = Schemas['ValidationReportOut'] & { summary: ValidationSummary }
export type ValidationResultItem = Schemas['ValidationResultOut'] & { state: ValidationState }
export type GraphRevisionBrief = Schemas['GraphRevisionOut']
export type OntologyValidationOptions = NonNullable<
  paths['/api/v1/validation/ontologies/{ontology_id}']['post']['parameters']['query']
>

export const validationApi = {
  /** 资产层校验（A01–A08）。设计器装配完用它判断能不能发布。 */
  validateOntology: (ontologyId: number, options?: OntologyValidationOptions) =>
    http
      .post<ValidationReport>(`/validation/ontologies/${ontologyId}`, null, { params: options })
      .then((r) => r.data),
  validateGraph: (graphRevisionId: number) =>
    http.post<ValidationReport>(`/validation/graph/${graphRevisionId}`).then((r) => r.data),
  getReport: (reportId: number) =>
    http.get<ValidationReport>(`/validation/reports/${reportId}`).then((r) => r.data),
  getResults: (reportId: number) =>
    http.get<ValidationResultItem[]>(`/validation/reports/${reportId}/results`).then((r) => r.data),
  revisions: () =>
    http.get<GraphRevisionBrief[]>('/extraction/graph/revisions').then((r) => r.data),
}
