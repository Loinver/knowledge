import { queryIsolationTests } from '../../../system/users/__tests__/c4-query-isolation.mjs'

queryIsolationTests({
  name: 'rules',
  entry: 'views/governance/rules/GovernanceRulesPage.vue',
  apiModule: '@/api/governance',
  apiName: 'rulesApi',
  method: 'list',
  expose: 'query,search,sourceKind,doSearch',
  draft: 'query',
  submit: 'doSearch',
  filters: [
    { field: 'sourceKind', value: 'STANDARD', key: 'source_kind', expected: 'STANDARD' },
    { field: 'sourceKind', value: 'ENTERPRISE', key: 'source_kind', expected: 'ENTERPRISE' },
    { field: 'sourceKind', value: null, key: 'source_kind', expected: undefined },
  ],
})
