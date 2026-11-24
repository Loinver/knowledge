import { queryIsolationTests } from '../../../system/users/__tests__/c4-query-isolation.mjs'

queryIsolationTests({
  name: 'clauses',
  entry: 'views/governance/clauses/StandardClausesPage.vue',
  apiModule: '@/api/clauses',
  apiName: 'clausesApi',
  method: 'list',
  expose: 'query,search,doSearch',
  draft: 'query',
  submit: 'doSearch',
  filters: [],
})
