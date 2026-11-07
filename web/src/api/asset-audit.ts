import { http } from '@/api/client'
import type { components, operations } from '@/api/schema'

export type AssetAuditLog = components['schemas']['AssetAuditOut']
export type AssetAuditAction = components['schemas']['AssetAuditAction']
export type AssetType = components['schemas']['AssetType']
export type AssetAuditVersion = components['schemas']['AssetAuditVersion']
export type AssetAuditPage = components['schemas']['AssetAuditPage']
export type AssetAuditQuery = NonNullable<
  operations['list_asset_audit_logs_api_v1_asset_audit_logs_get']['parameters']['query']
>

/** Audit history is intentionally read-only and always server-paginated. */
export const assetAuditApi = {
  page: (query: AssetAuditQuery, signal?: AbortSignal) =>
    http.get<AssetAuditPage>('/asset-audit-logs', { params: query, signal }).then((r) => r.data),
}
