<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import {
  NAlert,
  NButton,
  NDataTable,
  NEmpty,
  NFormItem,
  NInput,
  NPagination,
  NSelect,
  NSpace,
} from 'naive-ui'
import { computed, h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import type { GraphEntity } from '@/api/graph'
import { graphApi } from '@/api/graph'
import PageHeader from '@/components/PageHeader.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { entityName } from '@/views/graph/components/graphWorkspace'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const input = ref(String(route.query.q ?? ''))
const query = ref(input.value)
const positive = (value: unknown, fallback: number) =>
  Number.isSafeInteger(Number(value)) && Number(value) > 0 ? Number(value) : fallback
const page = ref(positive(route.query.page, 1))
const pageSize = ref(
  [25, 50, 100, 200].includes(Number(route.query.size)) ? Number(route.query.size) : 50,
)
const sort = ref<'iri' | '-iri'>(route.query.sort === '-iri' ? '-iri' : 'iri')
const listContext = computed(() => ({
  ...route.query,
  q: query.value || undefined,
  page: page.value,
  size: pageSize.value,
  sort: sort.value,
}))
watch([query, page, pageSize, sort], () => void router.replace({ query: listContext.value }))
watch(
  () => route.query,
  (params) => {
    query.value = String(params.q ?? '')
    input.value = query.value
    page.value = positive(params.page, 1)
    pageSize.value = [25, 50, 100, 200].includes(Number(params.size)) ? Number(params.size) : 50
    sort.value = params.sort === '-iri' ? '-iri' : 'iri'
  },
)
let resolvedRevision: number | undefined
watch(
  () => route.query.graph,
  () => {
    resolvedRevision = undefined
  },
  { flush: 'sync' },
)
const { data, error, loading, reload } = useAsyncData((signal) =>
  graphApi
    .entities(
      {
        graph_revision_id: route.query.graph ? Number(route.query.graph) : resolvedRevision,
        q: query.value,
        page: page.value,
        page_size: pageSize.value,
        sort: sort.value,
      },
      signal,
    )
    .then((result) => {
      if (!signal.aborted && result) resolvedRevision = result.graph_revision_id
      return result
    }),
)
const columns = computed<DataTableColumns<GraphEntity>>(() => [
  {
    key: 'name',
    title: t('common.name'),
    width: 220,
    ellipsis: { tooltip: true },
    render: (row) =>
      h(
        RouterLink,
        {
          to: {
            name: 'graph-entity-detail',
            params: { id: row.iri },
            query: { ...listContext.value, graph: row.graph_revision_id },
          },
        },
        () => entityName(row),
      ),
  },
  {
    key: 'iri',
    title: t('common.iri'),
    width: 440,
    ellipsis: { tooltip: true },
    render: (row) =>
      h(
        RouterLink,
        {
          to: {
            name: 'graph-entity-detail',
            params: { id: row.iri },
            query: { ...listContext.value, graph: row.graph_revision_id },
          },
        },
        () => row.iri,
      ),
  },
  { key: 'type_iri', title: t('graph.type'), width: 300, ellipsis: { tooltip: true } },
  { key: 'row_key', title: t('graph.rowKey'), width: 160 },
])
function search() {
  page.value = 1
  query.value = input.value
  reload()
}

function goEvidence() {
  void router.push({
    name: 'graph-evidence',
    query: { graph: data.value?.graph_revision_id ?? route.query.graph },
  })
}
</script>

<template>
  <section class="graph-page">
    <PageHeader :title="t('page.graphEntities')" :description="t('graph.searchHint')">
      <template #actions>
        <NButton secondary @click="goEvidence">{{ t('page.graphEvidence') }}</NButton>
      </template>
    </PageHeader>
    <form @submit.prevent="search">
      <NSpace align="center">
        <NFormItem
          :label="t('common.search')"
          label-placement="left"
          :label-width="72"
          :show-feedback="false"
        >
          <NInput
            v-model:value="input"
            :placeholder="t('graph.searchHint')"
            :aria-label="t('graph.searchHint')"
            clearable
          />
        </NFormItem>
        <NButton attr-type="submit" type="primary">{{ t('common.search') }}</NButton>
        <NFormItem
          :label="t('graph.sort')"
          label-placement="left"
          :label-width="72"
          :show-feedback="false"
        >
          <NSelect
            v-model:value="sort"
            style="width: 180px"
            :aria-label="t('graph.sort')"
            :options="[
              { label: t('graph.ascending'), value: 'iri' },
              { label: t('graph.descending'), value: '-iri' },
            ]"
            @update:value="page = 1"
          />
        </NFormItem>
        <NButton :loading="loading" @click="reload">{{ t('graph.refresh') }}</NButton>
      </NSpace>
    </form>
    <NAlert v-if="error" type="warning"
      >{{ error }} <NButton @click="reload">{{ t('ui.retry') }}</NButton></NAlert
    >
    <template v-if="data">
      <p>
        {{ t('graph.resultSet', { id: data.graph_revision_id }) }} ·
        {{ t('graph.total', { n: data.total }) }}
      </p>
      <NEmpty
        v-if="!data.total"
        :description="t(query ? 'ui.emptyFiltered' : 'graph.noVisibleNodes')"
      />
      <NDataTable
        v-else
        :columns="columns"
        :data="data.items"
        :row-key="(row: GraphEntity) => row.id"
        :loading="loading"
        :max-height="520"
        :scroll-x="1120"
        virtual-scroll
      />
      <NPagination
        v-model:page="page"
        v-model:page-size="pageSize"
        :item-count="data.total"
        :page-sizes="[25, 50, 100, 200]"
        show-size-picker
        @update:page-size="page = 1"
      />
    </template>
    <p v-else-if="loading" role="status">{{ t('common.loading') }}</p>
  </section>
</template>

<style scoped>
.graph-page {
  display: grid;
  gap: 16px;
}
h2,
p {
  margin: 0;
}
</style>
