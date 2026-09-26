<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import { NDataTable } from 'naive-ui'
import { computed, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import type { GraphFact } from '@/api/graph'

const props = defineProps<{ items: GraphFact[]; graphRevisionId: number; derived?: boolean }>()
const { t } = useI18n()
const formatProps = (value: GraphFact['props']) =>
  value
    ? Object.entries(value)
        .map(([key, item]) => `${key}=${String(item)}`)
        .join(' · ')
    : ''
const columns = computed<DataTableColumns<GraphFact>>(() => [
  ...(['subject', 'predicate', 'object_'] as const).map((key) => ({
    key,
    title: t(`graph.${key === 'object_' ? 'object' : key}`),
    width: 260,
    ellipsis: { tooltip: true },
    render: (row: GraphFact) =>
      key === 'predicate'
        ? row[key]
        : h(
            RouterLink,
            {
              to: {
                name: 'graph-entity-detail',
                params: { id: row[key] },
                query: { graph: props.graphRevisionId },
              },
            },
            () => row[key],
          ),
  })),
  {
    key: 'props',
    title: t('graph.edgeProps'),
    width: 160,
    render: (row: GraphFact) => formatProps(row.props) || '—',
  },
  ...(!props.derived
    ? [
        {
          key: 'evidence',
          title: t('page.graphEvidence'),
          width: 140,
          render: (row: GraphFact) =>
            h(
              RouterLink,
              {
                to: {
                  name: 'graph-evidence',
                  query: {
                    graph: props.graphRevisionId,
                    subject: row.subject,
                    predicate: row.predicate,
                    object: row.object_,
                  },
                },
              },
              () => t('graph.trace'),
            ),
        },
      ]
    : []),
])
</script>

<template>
  <NDataTable
    :columns="columns"
    :data="items"
    :row-key="(row: GraphFact) => row.id"
    :max-height="480"
    :scroll-x="derived ? 940 : 1080"
    virtual-scroll
  />
</template>
