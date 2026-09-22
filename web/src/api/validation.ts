import { http } from '@/api/client'

export interface ValidationSummary {
  pass: number
  violation: number
  na: number
  not_run: number
}

export interface ValidationResultItem {
  check_code: string
  state: 'PASS' | 'VIOLATION' | 'NA' | 'NOT_RUN'
  focus_node: string | null
  rule_id: string | null
  detail: Record<string, unknown> | null
  message: string | null
}

export interface ValidationReport {
  report_id: number
  scope: 'ontology' | 'instance'
  target_id: number
  summary: ValidationSummary
}

export interface GraphRevisionBrief {
  id: number
  run_id: number
  is_current: boolean
  publishable: boolean
}

export const validationApi = {
  validateGraph: (graphRevisionId: number) =>
    http
      .post(`/validation/graph/${  graphRevisionId}`)
      .then((r) => r.data as ValidationReport),
  getReport: (reportId: number) =>
    http
      .get(`/validation/reports/${  reportId}`)
      .then((r) => r.data as ValidationReport),
  getResults: (reportId: number) =>
    http
      .get(`/validation/reports/${  reportId  }/results`)
      .then((r) => r.data as ValidationResultItem[]),
  revisions: () =>
    http
      .get('/extraction/graph/revisions')
      .then((r) => r.data as GraphRevisionBrief[]),
}
