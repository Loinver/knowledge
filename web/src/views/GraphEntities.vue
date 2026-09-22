<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import { NAlert, NButton, NDataTable, NInput, NPagination, NSelect, NSpace } from 'naive-ui'
import { computed, h, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'

import type { GraphEntity } from '@/api/graph'
import { graphApi } from '@/api/graph'
import { useAsyncData } from '@/composables/useAsyncData'

const { t } = useI18n()
const route = useRoute()
const input = ref('')
const query = ref('')
const page = ref(1)
const pageSize = ref(50)
const sort = ref<'iri' | '-iri'>('iri')
const { data, error, loading, reload } = useAsyncData((signal) =>
  graphApi.entities(
    {
      graph_revision_id: route.query.graph ? Number(route.query.graph) : undefined,
      q: query.value,
      page: page.value,
      page_size: pageSize.value,
      sort: sort.value,
    },
    signal,
  ),
)
const columns = computed<DataTableColumns<GraphEntity>>(() => [
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
            query: { graph: row.graph_revision_id },
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
</script>

<template>
  <section class="graph-page">
    <NSpace justify="space-between" align="center">
      <h2>{{ t('page.graphEntities') }}</h2>
      <RouterLink :to="{ name: 'graph-evidence' }">{{ t('page.graphEvidence') }}</RouterLink>
    </NSpace>
    <form @submit.prevent="search">
      <NSpace align="center">
        <NInput
          v-model:value="input"
          :placeholder="t('graph.searchHint')"
          :aria-label="t('graph.searchHint')"
          clearable
        />
        <NButton attr-type="submit" type="primary">{{ t('common.search') }}</NButton>
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
        <NButton :loading="loading" @click="reload">{{ t('graph.refresh') }}</NButton>
      </NSpace>
    </form>
    <NAlert v-if="error" type="warning">{{ error }}</NAlert>
    <template v-if="data">
      <p>
        {{ t('graph.resultSet', { id: data.graph_revision_id }) }} ·
        {{ t('graph.total', { n: data.total }) }}
      </p>
      <NDataTable
        :columns="columns"
        :data="data.items"
        :row-key="(row: GraphEntity) => row.id"
        :loading="loading"
        :max-height="520"
        :scroll-x="900"
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
