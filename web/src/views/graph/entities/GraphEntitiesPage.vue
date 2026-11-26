<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import type { GraphEntity } from '@/api/graph'
import { graphApi } from '@/api/graph'
import PageHeader from '@/components/PageHeader.vue'
import { FormField, SearchPanel, SearchTable, UiButton, UiSelect } from '@/components/ui'
import type { DataTableColumns } from '@/components/ui/tableTypes'
import { useAsyncData } from '@/composables/useAsyncData'
import { entityName } from '@/views/graph/components/graphWorkspace'

const { t } = useI18n()
const shortName = (iri: string) => iri.split(/[/#]/).filter(Boolean).at(-1) || iri
const route = useRoute()
const router = useRouter()
const input = ref(String(route.query.q ?? ''))
const query = computed(() => String(route.query.q ?? ''))
const positive = (value: unknown, fallback: number) =>
  Number.isSafeInteger(Number(value)) && Number(value) > 0 ? Number(value) : fallback
const page = computed(() => positive(route.query.page, 1))
const pageSize = computed(() =>
  [25, 50, 100, 200].includes(Number(route.query.size)) ? Number(route.query.size) : 50,
)
const sort = computed(() => (route.query.sort === '-iri' ? '-iri' : 'iri'))
const kbReturn = computed(() =>
  typeof route.query.kbReturn === 'string' &&
  /^\/knowledge-bases\/[1-9]\d*\/search(?:\?|$)/.test(route.query.kbReturn)
    ? route.query.kbReturn
    : undefined,
)
const listContext = computed(() => ({
  graph: route.query.graph,
  kbReturn: kbReturn.value,
  q: query.value || undefined,
  page: page.value,
  size: pageSize.value,
  sort: sort.value,
}))
watch(query, (value) => {
  input.value = value
})
let resolvedRevision: number | undefined
watch(
  () => route.query.graph,
  () => {
    resolvedRevision = undefined
  },
  { flush: 'sync' },
)
const requestKey = computed(() =>
  JSON.stringify([route.query.graph, query.value, page.value, pageSize.value, sort.value]),
)
const { data, error, loading, reload } = useAsyncData((signal) => {
  // Only the applied route identity triggers a read. Navigation metadata does not.
  const [graph, q, pageNumber, size, order] = JSON.parse(requestKey.value) as [
    string | null,
    string,
    number,
    number,
    'iri' | '-iri',
  ]
  return graphApi
    .entities(
      {
        graph_revision_id: graph ? Number(graph) : resolvedRevision,
        q,
        page: pageNumber,
        page_size: size,
        sort: order,
      },
      signal,
    )
    .then((result) => {
      if (!signal.aborted && result) resolvedRevision = result.graph_revision_id
      return result
    })
})
const columns = computed<DataTableColumns<GraphEntity>>(() => [
  {
    key: 'name',
    title: t('common.name'),
    width: 360,
    ellipsis: { tooltip: true },
    render: (row) =>
      h(
        RouterLink,
        {
          class: 'entity-cell',
          to: {
            name: 'graph-entity-detail',
            params: { id: row.iri },
            query: { ...listContext.value, graph: row.graph_revision_id },
          },
        },
        () => [h('strong', entityName(row)), h('small', { title: row.iri }, row.iri)],
      ),
  },
  {
    key: 'type_iri',
    title: t('graph.type'),
    width: 260,
    ellipsis: { tooltip: true },
    render: (row) => h('span', { title: row.type_iri }, shortName(row.type_iri)),
  },
  { key: 'row_key', title: t('graph.rowKey'), width: 160 },
])
async function applyQuery(changes: Record<string, string | number | undefined>) {
  const previous = requestKey.value
  await router.replace({ query: { ...listContext.value, ...changes } })
  if (requestKey.value === previous && !loading.value) reload()
}
function search() {
  // SearchPanel emits a trimmed argument; this API has always received the raw draft.
  return applyQuery({ q: input.value || undefined, page: 1 })
}
function clearSearch() {
  input.value = ''
  return search()
}
function resetSearch() {
  input.value = ''
  return applyQuery({ q: undefined, page: 1, size: 50, sort: 'iri' })
}

function goEvidence() {
  void router.push({
    name: 'graph-evidence',
    query: {
      ...listContext.value,
      graph: data.value?.graph_revision_id ?? resolvedRevision ?? route.query.graph,
    },
  })
}
</script>

<template>
  <section class="graph-page">
    <PageHeader :title="t('page.graphEntities')" :eyebrow="t('studio.entityLedger')">
      <template #context
        ><span v-if="data" class="ledger-context"
          >{{ t('graph.resultSet', { id: data.graph_revision_id }) }} ·
          {{ t('ui.readOnlyLabel') }}</span
        ></template
      >
      <template #actions>
        <UiButton secondary @click="goEvidence">{{ t('page.graphEvidence') }}</UiButton>
      </template>
    </PageHeader>
    <SearchPanel
      v-model:query="input"
      class="ledger-toolbar"
      :label="t('common.search')"
      :placeholder="t('graph.searchHint')"
      :loading="loading"
      @submit="search"
      @clear="clearSearch"
      @reset="resetSearch"
    >
      <template #filter>
        <FormField :label="t('graph.sort')" :show-feedback="false">
          <UiSelect
            :value="sort"
            class="ledger-sort"
            :aria-label="t('graph.sort')"
            :options="[
              { label: t('graph.ascending'), value: 'iri' },
              { label: t('graph.descending'), value: '-iri' },
            ]"
            @update:value="applyQuery({ sort: String($event), page: 1 })"
          />
        </FormField>
      </template>
    </SearchPanel>
    <SearchTable
      :searchable="false"
      mode="remote"
      :columns="columns"
      :rows="data?.items ?? []"
      :row-key="(row: GraphEntity) => row.id"
      :total="data?.total"
      :page="page"
      :page-size="pageSize"
      :pagination="{ pageSizes: [25, 50, 100, 200], showSizePicker: true }"
      :initialized="data !== null"
      :loading="loading"
      :error="error"
      :empty-text="t(query ? 'ui.emptyFiltered' : 'graph.noVisibleNodes')"
      :label="t('page.graphEntities')"
      :max-height="520"
      :scroll-x="780"
      @update:page="applyQuery({ page: $event })"
      @update:page-size="applyQuery({ page: 1, size: $event })"
      @retry="reload"
    >
      <template #toolbar-actions>
        <UiButton :loading="loading" @click="reload">{{ t('graph.refresh') }}</UiButton>
      </template>
    </SearchTable>
  </section>
</template>

<style scoped>
.graph-page {
  display: grid;
  gap: 20px;
  min-width: 0;
}
.graph-page > * {
  min-width: 0;
}
.ledger-toolbar {
  padding: var(--space-4);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-panel);
  background: var(--surface-panel);
}
.graph-page :deep(.entity-cell) {
  display: grid;
  gap: 4px;
  min-width: 0;
  padding-block: 4px;
}
.graph-page :deep(.entity-cell strong) {
  font-weight: 500;
  color: var(--foreground-primary);
}
.graph-page :deep(.entity-cell small) {
  overflow: hidden;
  text-overflow: ellipsis;
  font: 11px var(--font-mono, monospace);
  color: var(--foreground-secondary);
}
.ledger-sort {
  min-width: 11rem;
}
.ledger-context {
  color: var(--foreground-secondary);
  font-size: var(--font-small);
}
</style>
