<script setup lang="ts">
import { h, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { EntityTypeBrief } from '@/api/entity-types'
import type { KnowledgeBase } from '@/api/knowledge'
import type { DataTableColumns, RowKey, TableSort } from '@/components/ui/tableTypes'
import UiDataTable from '@/components/ui/UiDataTable.vue'

import SearchTable from '../SearchTable.vue'

const { t } = useI18n()
const entities = ref<EntityTypeBrief[]>([])
const bases = ref<KnowledgeBase[]>([])
const entityColumns: DataTableColumns<EntityTypeBrief> = [
  { type: 'selection', disabled: (row) => row.status === 'PUBLISHED' },
  {
    key: 'name',
    title: () => t('common.name'),
    minWidth: 200,
    sorter: (a, b) => a.name.localeCompare(b.name),
  },
  { key: 'iri', title: t('common.iri'), minWidth: 300, ellipsis: { tooltip: true } },
  {
    key: 'actions',
    title: t('common.actions'),
    width: 150,
    fixed: 'right',
    render: (row) => h('button', { type: 'button', 'data-id': row.id }, t('ui.view')),
  },
]
const baseColumns: DataTableColumns<KnowledgeBase> = [
  { key: 'name', title: t('kb.name'), render: (row) => row.name },
  { key: 'revision', title: t('common.revision'), width: 100 },
]
const page = ref(1)
const query = ref('')
const selection = ref<RowKey[]>([])
const sort = ref<TableSort>(null)
</script>

<template>
  <UiDataTable
    v-model:selection="selection"
    v-model:sort="sort"
    :rows="entities"
    :columns="entityColumns"
    :row-key="(row: EntityTypeBrief) => row.id"
    :row-props="(row: EntityTypeBrief) => ({ 'data-id': row.id })"
    mode="local"
    :pagination="{ page, pageSize: 20, onChange: (value: number) => (page = value) }"
  >
    <template #cell-iri="{ row }"
      ><a :href="row.iri">{{ row.iri }}</a></template
    >
  </UiDataTable>
  <SearchTable
    v-model:query="query"
    v-model:page="page"
    :rows="bases"
    :columns="baseColumns"
    :row-key="(row: KnowledgeBase) => row.id"
    mode="remote"
    :total="0"
    :page-size="20"
  >
    <template #cell-name="{ row }"
      ><span :data-revision="row.revision">{{ row.name }}</span></template
    >
    <template #toolbar-actions
      ><button type="button">{{ t('kb.create') }}</button></template
    >
  </SearchTable>
</template>
