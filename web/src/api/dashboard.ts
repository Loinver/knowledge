import { http } from '@/api/client'

export interface DashboardStats {
  entityTypes: number
  relationTypes: number
  domains: number
  ontologies: number
  datasources: number
  runs: number
  currentGraphId: number | null
  resultSetCount: number
  quarantineCount: number
  unpublishedCount: number
}

interface Brief {
  status?: string
}

async function countAndUnpublished(url: string, signal: AbortSignal): Promise<{ count: number; unpublished: number }> {
  const res = await http.get<Brief[]>(url, { signal })
  const items = Array.isArray(res.data) ? res.data : []
  let unpublished = 0
  for (const item of items) {
    if (item && item.status === 'DRAFT') unpublished += 1
  }
  return { count: items.length, unpublished }
}

export const dashboardApi = {
  async stats(signal: AbortSignal): Promise<DashboardStats> {
    const [entityTypes, relationTypes, domains, ontologies, datasources, runs, current, revisions] = await Promise.all([
      countAndUnpublished('/entity-types', signal),
      countAndUnpublished('/relations', signal),
      countAndUnpublished('/domains', signal),
      countAndUnpublished('/ontologies', signal),
      countAndUnpublished('/datasources', signal),
      countAndUnpublished('/extraction/runs', signal),
      http.get('/extraction/graph/current', { signal }).then((r) => r.data).catch(() => null),
      http.get('/extraction/graph/revisions', { signal }).then((r) => r.data).catch(() => []),
    ])
    let quarantineCount = 0
    if (current && current.id && current.run_id) {
      const runId = current.run_id
      quarantineCount = await http
        .get(`/extraction/runs/${runId}/quarantine`, { signal })
        .then((r) => (Array.isArray(r.data) ? r.data.length : 0))
        .catch(() => 0)
    }
    return {
      entityTypes: entityTypes.count,
      relationTypes: relationTypes.count,
      domains: domains.count,
      ontologies: ontologies.count,
      datasources: datasources.count,
      runs: runs.count,
      currentGraphId: current && current.id ? current.id : null,
      resultSetCount: Array.isArray(revisions) ? revisions.length : 0,
      quarantineCount,
      unpublishedCount:
        entityTypes.unpublished + relationTypes.unpublished + domains.unpublished + ontologies.unpublished,
    }
  },
}
