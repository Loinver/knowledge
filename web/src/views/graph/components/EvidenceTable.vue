<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { EvidenceItem } from '@/api/graph'
import { SearchTable, UiButton, UiTag } from '@/components/ui'
import type { DataTableColumns } from '@/components/ui/tableTypes'

const props = defineProps<{ items: EvidenceItem[]; relationLabels?: Record<string, string> }>()
const page = ref(1)
const pageSize = ref(20)
watch(
  () => props.items,
  () => {
    page.value = 1
  },
)
const emit = defineEmits<{ chain: [item: EvidenceItem] }>()
const { t } = useI18n()
const columns = computed<DataTableColumns<EvidenceItem>>(() => [
  ...(['subject', 'predicate', 'object'] as const).map((key) => ({
    key,
    title: t(`graph.${key}`),
    width: 230,
    ellipsis: { tooltip: true },
    render: (row: EvidenceItem) => {
      const label = key === 'predicate' ? props.relationLabels?.[row.predicate] : undefined
      return label
        ? h('span', { title: row.predicate, 'aria-label': `${label} · ${row.predicate}` }, label)
        : row[key]
    },
  })),
  {
    key: 'source_name',
    title: t('graph.source'),
    width: 180,
    render: (row) =>
      `${row.source_name ?? t('graph.deletedSource')} (#${row.source_id}, ${row.source_kind ?? '-'})`,
  },
  { key: 'table_name', title: t('graph.table'), width: 150 },
  { key: 'row_key', title: t('graph.rowKey'), width: 140 },
  {
    key: 'columns',
    title: t('graph.fields'),
    width: 200,
    render: (row) => row.columns.join(', '),
  },
  { key: 'run_id', title: t('graph.run'), width: 100, format: 'raw' },
  {
    key: 'evidence_type',
    title: t('graph.evidenceType'),
    width: 150,
    render: (row) =>
      ['ENTITY', 'RELATION'].includes(row.evidence_type)
        ? t(`graph.evidenceTypes.${row.evidence_type}`)
        : row.evidence_type,
  },
  {
    key: 'quarantined',
    title: t('graph.sourceStatus'),
    width: 180,
    render: (row) =>
      h(UiTag, { type: row.quarantined ? 'warning' : 'success', size: 'small' }, () =>
        t(row.quarantined ? 'graph.hasQuarantine' : 'graph.noQuarantine'),
      ),
  },
  {
    key: 'chain',
    fixed: 'right',
    title: t('graph.chain'),
    width: 120,
    render: (row) =>
      h(UiButton, { size: 'tiny', onClick: () => emit('chain', row) }, () => t('graph.chainView')),
  },
])
</script>

<template>
  <SearchTable
    v-model:page="page"
    v-model:page-size="pageSize"
    :searchable="false"
    mode="local"
    :pagination="{ pageSizes: [20, 50, 100], showSizePicker: true }"
    :label="t('page.graphEvidence')"
    :columns="columns"
    :rows="items"
    :row-key="(row: EvidenceItem) => row.id"
    :max-height="480"
    :scroll-x="2010"
  />
</template>
