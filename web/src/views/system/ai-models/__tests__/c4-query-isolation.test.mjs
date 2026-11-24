import { queryIsolationTests } from '../../users/__tests__/c4-query-isolation.mjs'

queryIsolationTests({
  name: 'ai-models',
  entry: 'views/system/ai-models/AiModelsPage.vue',
  apiModule: '@/api/ai-models',
  apiName: 'aiModelsApi',
  method: 'page',
  expose: 'query,search,doSearch,enabledSelection,enabledFilter,capabilityFilter,sort',
  draft: 'search',
  submit: 'doSearch',
  filters: [
    { field: 'enabledSelection', value: 'false', key: 'enabled', expected: false },
    { field: 'enabledSelection', value: 'true', key: 'enabled', expected: true },
    { field: 'enabledSelection', value: null, key: 'enabled', expected: undefined },
    { field: 'capabilityFilter', value: 'CHAT', key: 'capability', expected: 'CHAT' },
    { field: 'capabilityFilter', value: 'EMBEDDING', key: 'capability', expected: 'EMBEDDING' },
    { field: 'capabilityFilter', value: null, key: 'capability', expected: undefined },
    { field: 'sort', value: '-name', key: 'sort', expected: '-name' },
    { field: 'sort', value: '-id', key: 'sort', expected: '-id' },
  ],
})
