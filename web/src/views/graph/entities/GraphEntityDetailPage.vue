<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import type { EntityFusion, EvidenceItem } from '@/api/graph'
import { graphApi } from '@/api/graph'
import PageHeader from '@/components/PageHeader.vue'
import {
  SearchTable,
  UiAlert,
  UiButton,
  UiEmpty,
  UiSpace,
  UiTabPane,
  UiTabs,
} from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useAsyncData } from '@/composables/useAsyncData'
import { usePageIdentity } from '@/layout/navigation/usePageIdentity'
import EvidenceTable from '@/views/graph/components/EvidenceTable.vue'
import GraphFactTable from '@/views/graph/components/GraphFactTable.vue'
import { entityName } from '@/views/graph/components/graphWorkspace'
import { useFrozenRelationLabels } from '@/views/graph/composables/useFrozenRelationLabels'

const { t, n } = useI18n()
const { toMessage } = useApiError()
const route = useRoute()
const router = useRouter()
const kbReturn = computed(() =>
  typeof route.query.kbReturn === 'string' &&
  /^\/knowledge-bases\/[1-9]\d*\/search(?:\?|$)/.test(route.query.kbReturn)
    ? route.query.kbReturn
    : undefined,
)
let resolvedRevision: number | undefined
watch(
  () => route.query.graph,
  () => {
    resolvedRevision = undefined
  },
  { flush: 'sync' },
)
const detailKey = computed(() => JSON.stringify([String(route.params.id), route.query.graph]))
const { data, error, loading, reload } = useAsyncData(async (signal) => {
  const [iri, graph] = JSON.parse(detailKey.value) as [string, string | null]
  const graphId = graph ? Number(graph) : resolvedRevision
  const detail = await graphApi.detail(iri, graphId, signal)
  if (!signal.aborted) resolvedRevision = detail.entity.graph_revision_id
  return { detail }
})
usePageIdentity(() => (data.value ? entityName(data.value.detail.entity) : undefined))
const evidence = useAsyncData((signal) =>
  data.value
    ? graphApi.entityEvidence(
        data.value.detail.entity.iri,
        data.value.detail.entity.graph_revision_id,
        signal,
      )
    : Promise.resolve(null),
)
const frozenLabels = useFrozenRelationLabels(
  () => data.value?.detail.entity.graph_revision_id,
  () => [
    ...(data.value?.detail.out_edges ?? []).map((edge) => edge.predicate),
    ...(data.value?.detail.in_edges ?? []).map((edge) => edge.predicate),
    ...(data.value?.detail.derived_edges ?? []).map((edge) => edge.predicate),
    ...(evidence.data.value?.evidences ?? []).map((item) => item.predicate),
  ],
)
const attrs = computed(() =>
  Object.entries(data.value?.detail.entity.attrs ?? {}).map(([key, value]) => ({
    key,
    value: typeof value === 'string' ? value : JSON.stringify(value),
  })),
)
const attributeKey = (row: { key: string }) => row.key

const fusion = ref<EntityFusion | null>(null)
const fusionLoading = ref(false)
const fusionError = ref('')
const activeTab = ref('attrs')
let fusionController: AbortController | null = null

async function loadFusion() {
  if (!data.value) return
  const iri = data.value.detail.entity.iri
  const grId = data.value.detail.entity.graph_revision_id
  fusionController?.abort()
  const controller = new AbortController()
  fusionController = controller
  fusionLoading.value = true
  fusionError.value = ''
  fusion.value = null
  try {
    const result = await graphApi.entityFusion(iri, grId, controller.signal)
    if (!controller.signal.aborted) fusion.value = result
  } catch (err) {
    if (!controller.signal.aborted) fusionError.value = toMessage(err)
  } finally {
    if (!controller.signal.aborted) fusionLoading.value = false
  }
}

watch(
  data,
  () => {
    fusionController?.abort()
    fusion.value = null
    fusionError.value = ''
    fusionLoading.value = false
  },
  { flush: 'sync' },
)
watch([activeTab, data], ([tab]) => {
  if (tab === 'fusion' && data.value && !fusion.value && !fusionLoading.value) void loadFusion()
})
onBeforeUnmount(() => fusionController?.abort())

/** 「查看证据链」跳到证据页并按三元组定位，与证据页 triple 模式共用查询参数。 */
function openChain(item: EvidenceItem) {
  void router.push({
    name: 'graph-evidence',
    query: {
      ...route.query,
      kbReturn: kbReturn.value,
      graph: data.value?.detail.entity.graph_revision_id,
      returnEntity: route.params.id,
      iri: undefined,
      subject: item.subject,
      predicate: item.predicate,
      object: item.object,
    },
  })
}

const fusionColumns = computed(() => [
  { key: 'source_name', title: t('graph.fusionSource') },
  { key: 'table_name', title: t('graph.fusionTable') },
  { key: 'row_key', title: t('graph.fusionRowKey') },
  {
    key: 'contributions',
    title: t('graph.fusionContributions'),
    render: (row: { contributions: unknown[] }) => n(row.contributions.length),
  },
  {
    key: 'quarantined',
    title: t('graph.fusionQuarantined'),
    render: (row: { quarantined: boolean }) => t(row.quarantined ? 'common.yes' : 'common.no'),
  },
])
const fusionRowKey = (row: { source_id: number; table_name: string; row_key: string }) =>
  JSON.stringify([row.source_id, row.table_name, row.row_key])
const conflictColumns = computed(() => [
  { key: 'predicate', title: t('graph.fusionPredicate') },
  {
    key: 'values',
    title: t('graph.fusionValues'),
    render: (row: EntityFusion['conflicts'][number]) =>
      row.values.map((v) => `${v.table_name}:${v.row_key}=${v.value}`).join(', '),
  },
])
const conflictRowKey = (row: { predicate: string }) => row.predicate
</script>

<template>
  <section class="graph-page">
    <PageHeader
      :title="data ? entityName(data.detail.entity) : t('page.graphEntityDetail')"
      :identity="data?.detail.entity.iri"
    >
      <template #context
        ><span v-if="data" class="detail-context"
          >{{ t('graph.resultSet', { id: data.detail.entity.graph_revision_id }) }} ·
          {{ t('ui.readOnlyLabel') }}</span
        ></template
      >
      <template #actions>
        <RouterLink v-if="kbReturn" :to="kbReturn">{{ t('kb.backToSearch') }}</RouterLink>
        <RouterLink
          :to="{
            name: 'graph-entities',
            query: {
              ...route.query,
              kbReturn,
              graph: data?.detail.entity.graph_revision_id ?? route.query.graph,
            },
          }"
          >{{ t('ui.backList') }}</RouterLink
        >
        <UiButton :loading="loading" @click="reload">{{ t('graph.refresh') }}</UiButton>
      </template>
    </PageHeader>
    <UiAlert v-if="error" type="error"
      >{{ error }} <UiButton @click="reload">{{ t('ui.retry') }}</UiButton></UiAlert
    >
    <p v-if="loading" role="status">{{ t('common.loading') }}</p>
    <template v-if="data">
      <div class="detail-workspace">
        <div class="detail-content">
          <UiAlert v-if="frozenLabels.error.value" type="warning" role="alert">
            {{ frozenLabels.error.value }}
            <UiButton @click="frozenLabels.reload">{{ t('ui.retry') }}</UiButton>
          </UiAlert>
          <!-- G-30 实体 360 画像：分区跳转到各形态与追溯 -->
          <UiSpace align="center" class="views-360">
            <span>{{ t('graph.views360') }}</span>
            <UiButton
              v-for="layout in ['force', 'ring', 'org_tree', 'equity_tree', 'timeline']"
              :key="layout"
              size="small"
              @click="
                $router.push({
                  name: 'graph-browse',
                  query: {
                    graph: data.detail.entity.graph_revision_id,
                    center: data.detail.entity.iri,
                    layout,
                    kbReturn,
                  },
                })
              "
            >
              {{ t(`graph.layout.${layout}`) }}
            </UiButton>
            <RouterLink
              :to="{
                name: 'graph-evidence',
                query: {
                  ...route.query,
                  kbReturn,
                  subject: undefined,
                  predicate: undefined,
                  object: undefined,
                  graph: data.detail.entity.graph_revision_id,
                  iri: data.detail.entity.iri,
                  returnEntity: data.detail.entity.iri,
                },
              }"
              >{{ t('graph.chainTitle') }}</RouterLink
            >
          </UiSpace>
          <UiTabs v-model:value="activeTab" type="line" animated>
            <UiTabPane name="attrs" :tab="t('entityType.dataProps')">
              <SearchTable
                :searchable="false"
                mode="none"
                :max-height="480"
                :scroll-x="600"
                :columns="[
                  { key: 'key', title: t('common.name') },
                  { key: 'value', title: t('graph.value') },
                ]"
                :rows="attrs"
                :row-key="attributeKey"
              />
            </UiTabPane>
            <UiTabPane name="out" :tab="t('graph.outgoing')">
              <GraphFactTable
                :items="data.detail.out_edges"
                :kb-return="kbReturn"
                :relation-labels="frozenLabels.labels.value"
                :graph-revision-id="data.detail.entity.graph_revision_id"
              />
            </UiTabPane>
            <UiTabPane name="in" :tab="t('graph.incoming')">
              <GraphFactTable
                :items="data.detail.in_edges"
                :kb-return="kbReturn"
                :relation-labels="frozenLabels.labels.value"
                :graph-revision-id="data.detail.entity.graph_revision_id"
              />
            </UiTabPane>
            <UiTabPane name="derived" :tab="t('graph.derived')">
              <UiAlert type="info" class="notice">{{ t('graph.derivedHint') }}</UiAlert>
              <GraphFactTable
                :items="data.detail.derived_edges"
                :kb-return="kbReturn"
                :relation-labels="frozenLabels.labels.value"
                :graph-revision-id="data.detail.entity.graph_revision_id"
                derived
              />
            </UiTabPane>
            <UiTabPane name="evidence" :tab="t('page.graphEvidence')">
              <p v-if="evidence.loading.value" role="status">{{ t('common.loading') }}</p>
              <UiAlert v-else-if="evidence.error.value" type="warning"
                >{{ evidence.error.value }}
                <UiButton @click="evidence.reload">{{ t('ui.retry') }}</UiButton></UiAlert
              >
              <UiAlert
                v-if="evidence.data.value?.quarantined_count"
                type="warning"
                class="notice"
                >{{ t('graph.quarantineWarning') }}</UiAlert
              >
              <UiEmpty
                v-if="evidence.data.value && !evidence.data.value.total_count"
                :description="t('graphUi.noEvidence')"
              />
              <EvidenceTable
                v-else-if="evidence.data.value"
                :items="evidence.data.value.evidences"
                :relation-labels="frozenLabels.labels.value"
                @chain="openChain"
              />
            </UiTabPane>
            <UiTabPane name="fusion" :tab="t('graph.fusionTitle')">
              <p v-if="fusionLoading" role="status">{{ t('common.loading') }}</p>
              <UiAlert v-if="fusionError" type="error"
                >{{ fusionError }}
                <UiButton @click="loadFusion">{{ t('ui.retry') }}</UiButton></UiAlert
              >
              <UiEmpty
                v-if="fusion && !fusion.source_rows.length"
                :description="t('graph.noFusion')"
              />
              <template v-if="fusion && fusion.source_rows.length">
                <UiAlert v-if="fusion.conflicts.length" type="warning" class="notice">{{
                  t('graph.fusionConflictHint', { count: n(fusion.conflicts.length) })
                }}</UiAlert>
                <p>
                  {{
                    t('graph.fusionSummary', {
                      sources: n(fusion.source_count),
                      rows: n(fusion.row_count),
                    })
                  }}
                </p>
                <SearchTable
                  :searchable="false"
                  mode="none"
                  :max-height="480"
                  :scroll-x="600"
                  :columns="fusionColumns"
                  :rows="fusion.source_rows"
                  :row-key="fusionRowKey"
                />
                <h3 v-if="fusion.conflicts.length">{{ t('graph.fusionConflicts') }}</h3>
                <SearchTable
                  v-if="fusion.conflicts.length"
                  :searchable="false"
                  mode="none"
                  :max-height="480"
                  :scroll-x="600"
                  :columns="conflictColumns"
                  :rows="fusion.conflicts"
                  :row-key="conflictRowKey"
                />
              </template>
            </UiTabPane>
          </UiTabs>
        </div>
        <aside class="entity-identity">
          <h2>{{ t('studio.identity') }}</h2>
          <dl>
            <dt>{{ t('graph.type') }}</dt>
            <dd>{{ data.detail.entity.type_iri }}</dd>
            <dt>{{ t('graph.rowKey') }}</dt>
            <dd>{{ data.detail.entity.row_key }}</dd>
            <dt>{{ t('graph.revisionInput') }}</dt>
            <dd>{{ `#${data.detail.entity.graph_revision_id}` }}</dd>
          </dl>
          <div class="relation-readouts">
            <button type="button" :aria-pressed="activeTab === 'out'" @click="activeTab = 'out'">
              <span>{{ t('graph.outgoing') }}</span
              ><strong>{{ n(data.detail.out_edges.length) }}</strong>
            </button>
            <button type="button" :aria-pressed="activeTab === 'in'" @click="activeTab = 'in'">
              <span>{{ t('graph.incoming') }}</span
              ><strong>{{ n(data.detail.in_edges.length) }}</strong>
            </button>
            <button
              type="button"
              :aria-pressed="activeTab === 'derived'"
              @click="activeTab = 'derived'"
            >
              <span>{{ t('graph.derived') }}</span
              ><strong>{{ n(data.detail.derived_edges.length) }}</strong>
            </button>
          </div>
          <UiButton secondary @click="activeTab = 'evidence'">{{ t('graph.trace') }}</UiButton>
          <p>{{ t('graphUi.derivedEvidence') }}</p>
        </aside>
      </div>
    </template>
  </section>
</template>

<style scoped>
.detail-context {
  color: var(--text-secondary);
  font-size: 12px;
}
.detail-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 24px;
}
.entity-identity {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  align-self: start;
  border: 1px solid var(--border-muted);
  border-radius: var(--radius-panel);
  background: var(--surface-panel);
}
.entity-identity h2 {
  margin: 0;
  font-size: 14px;
}
.entity-identity dl {
  margin: 0;
  display: grid;
  gap: 8px;
}
.entity-identity dt {
  font-size: 12px;
  color: var(--text-secondary);
}
.entity-identity dd {
  margin: 0 0 8px;
  font: 12px var(--font-mono, monospace);
  overflow-wrap: anywhere;
}
.entity-identity p {
  color: var(--text-secondary);
  font-size: 12px;
}
.relation-readouts {
  display: grid;
  gap: 1px;
}
.relation-readouts button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px;
  border: 0;
  background: var(--surface-muted);
  color: var(--foreground-secondary);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.relation-readouts button:hover,
.relation-readouts button[aria-pressed='true'] {
  color: var(--action-primary);
  background: var(--surface-selected);
}
.relation-readouts strong {
  color: var(--text-primary);
  font: 600 18px var(--font-mono, monospace);
}
.detail-content {
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--border-muted);
  border-radius: var(--radius-panel);
  background: var(--surface-panel);
}
.views-360 {
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 12px;
}
@media (max-width: 64rem) {
  .detail-workspace {
    grid-template-columns: minmax(0, 1fr);
  }
  .entity-identity dl {
    grid-template-columns: 100px minmax(0, 1fr);
  }
  .relation-readouts {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@media (max-width: 48rem) {
  .detail-content {
    padding: 12px;
  }
  .relation-readouts button {
    flex-direction: column;
  }
}
.graph-page {
  display: grid;
  gap: 16px;
}
h2,
p {
  margin: 0;
}
.iri {
  overflow-wrap: anywhere;
}
.views-360 {
  flex-wrap: wrap;
}
.notice {
  margin-bottom: 16px;
}
</style>
