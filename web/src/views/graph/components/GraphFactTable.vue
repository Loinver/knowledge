<script setup lang="ts">
import { computed, h, inject } from 'vue'
import { useI18n } from 'vue-i18n'
import { routeLocationKey, RouterLink } from 'vue-router'

import type { GraphFact } from '@/api/graph'
import { SearchTable } from '@/components/ui'
import type { DataTableColumns } from '@/components/ui/tableTypes'

const props = defineProps<{
  items: GraphFact[]
  graphRevisionId: number
  derived?: boolean
  relationLabels?: Record<string, string>
  kbReturn?: string
}>()
const { t } = useI18n()
// Keep the public component contract; inherit only list-navigation metadata from its host.
const route = inject(routeLocationKey, undefined)
const navigationContext = computed(() =>
  Object.fromEntries(
    ['q', 'page', 'size', 'sort', 'returnEntity']
      .filter((key) => route?.query[key] !== undefined)
      .map((key) => [key, route!.query[key]]),
  ),
)
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
        ? props.relationLabels?.[row[key]]
          ? h('span', { title: row[key] }, props.relationLabels[row[key]])
          : row[key]
        : h(
            RouterLink,
            {
              to: {
                name: 'graph-entity-detail',
                params: { id: row[key] },
                query: {
                  ...navigationContext.value,
                  graph: props.graphRevisionId,
                  kbReturn: props.kbReturn,
                },
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
          fixed: 'right' as const,
          title: t('page.graphEvidence'),
          width: 140,
          render: (row: GraphFact) =>
            h(
              RouterLink,
              {
                to: {
                  name: 'graph-evidence',
                  query: {
                    ...navigationContext.value,
                    ...(route?.name === 'graph-entity-detail'
                      ? { returnEntity: route.params.id }
                      : {}),
                    graph: props.graphRevisionId,
                    kbReturn: props.kbReturn,
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
  <SearchTable
    :searchable="false"
    mode="none"
    :columns="columns"
    :rows="items"
    :row-key="(row: GraphFact) => row.id"
    :max-height="480"
    :scroll-x="derived ? 940 : 1080"
  />
</template>
