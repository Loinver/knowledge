import { http } from '@/api/client'
import type { components } from '@/api/schema'

export type DashboardStats = components['schemas']['DashboardStatsOut']

export const dashboardApi = {
  stats: (signal: AbortSignal) =>
    http.get<DashboardStats>('/dashboard/stats', { signal }).then((response) => response.data),
}
