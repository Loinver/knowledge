import { queryIsolationTests } from '../../users/__tests__/c4-query-isolation.mjs'

queryIsolationTests({
  name: 'audit-logs',
  entry: 'views/system/audit-logs/AuditLogsPage.vue',
  apiModule: '@/api/auth',
  apiName: 'authApi',
  method: 'auditLogs',
  expose: 'query,keyword,search,actionFilter',
  draft: 'query',
  submit: 'search',
  manual: true,
  filters: [
    { field: 'actionFilter', value: 'LOGIN', key: 'action', expected: 'LOGIN' },
    { field: 'actionFilter', value: 'ROLE_CHANGED', key: 'action', expected: 'ROLE_CHANGED' },
    { field: 'actionFilter', value: null, key: 'action', expected: undefined },
  ],
})
