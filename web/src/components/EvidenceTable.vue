<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import { NDataTable, NTag } from 'naive-ui'
import { computed, h } from 'vue'
import { useI18n } from 'vue-i18n'

import type { EvidenceItem } from '@/api/graph'

defineProps<{ items: EvidenceItem[] }>()
const { t } = useI18n()
const columns = computed<DataTableColumns<EvidenceItem>>(() => [
  ...(['subject', 'predicate', 'object'] as const).map((key) => ({
    key,
    title: t(`graph.${key}`),
    width: 230,
    ellipsis: { tooltip: true },
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
  { key: 'run_id', title: t('graph.run'), width: 100 },
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
      h(NTag, { type: row.quarantined ? 'warning' : 'success', size: 'small' }, () =>
        t(row.quarantined ? 'graph.hasQuarantine' : 'graph.noQuarantine'),
      ),
  },
])
</script>

<template>
  <NDataTable
    :columns="columns"
    :data="items"
    :row-key="(row: EvidenceItem) => row.id"
    :max-height="480"
    :scroll-x="1890"
    virtual-scroll
  />
</template>
