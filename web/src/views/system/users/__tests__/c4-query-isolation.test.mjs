import { queryIsolationTests } from './c4-query-isolation.mjs'

queryIsolationTests({
  name: 'users',
  entry: 'views/system/users/UsersPage.vue',
  apiModule: '@/api/auth',
  apiName: 'authApi',
  method: 'users',
  expose: 'query,keyword,search,roleFilter,statusFilter',
  draft: 'query',
  submit: 'search',
  manual: true,
  filters: [
    { field: 'roleFilter', value: 'VIEWER', key: 'role', expected: 'VIEWER' },
    { field: 'statusFilter', value: 'DISABLED', key: 'status', expected: 'DISABLED' },
    { field: 'roleFilter', value: null, key: 'role', expected: undefined },
    { field: 'statusFilter', value: null, key: 'status', expected: undefined },
  ],
})
