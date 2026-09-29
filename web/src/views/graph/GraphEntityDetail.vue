<script setup lang="ts">
import { NAlert, NButton, NDataTable, NEmpty, NSpace, NTabPane, NTabs } from 'naive-ui'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import type { EntityFusion, EvidenceItem } from '@/api/graph'
import { graphApi } from '@/api/graph'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'
import { useAsyncData } from '@/composables/useAsyncData'
import EvidenceTable from '@/views/graph/components/EvidenceTable.vue'
import GraphFactTable from '@/views/graph/components/GraphFactTable.vue'

const { t } = useI18n()
const { toMessage } = useApiError()
const route = useRoute()
const router = useRouter()
const { data, error, loading, reload } = useAsyncData(async (signal) => {
  const iri = String(route.params.id)
  const graphId = route.query.graph ? Number(route.query.graph) : undefined
  const detail = await graphApi.detail(iri, graphId, signal)
  const evidence = await graphApi.entityEvidence(iri, detail.entity.graph_revision_id, signal)
  return { detail, evidence }
})
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
  fusionController = new AbortController()
  fusionLoading.value = true
  fusionError.value = ''
  try {
    fusion.value = await graphApi.entityFusion(iri, grId, fusionController.signal)
  } catch (err) {
    fusionError.value = toMessage(err)
  } finally {
    fusionLoading.value = false
  }
}

watch(activeTab, (tab) => {
  if (tab === 'fusion' && !fusion.value && !fusionLoading.value) void loadFusion()
})

/** 「查看证据链」跳到证据页并按三元组定位，与证据页 triple 模式共用查询参数。 */
function openChain(item: EvidenceItem) {
  void router.push({
    name: 'graph-evidence',
    query: {
      graph: route.query.graph,
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
    render: (row: { contributions: unknown[] }) => row.contributions.length,
  },
  {
    key: 'quarantined',
    title: t('graph.fusionQuarantined'),
    render: (row: { quarantined: boolean }) => t(row.quarantined ? 'common.yes' : 'common.no'),
  },
])
const fusionRowKey = (row: { source_id: number; table_name: string; row_key: string }) =>
  `${row.source_id}:${row.table_name}:${row.row_key}`
const conflictColumns = computed(() => [
  { key: 'predicate', title: t('graph.fusionPredicate') },
  {
    key: 'values',
    title: t('graph.fusionValues'),
    render: (row: { values: { table_name: string; row_key: string; value: string }[] }) =>
      row.values.map((v) => `${v.table_name}:${v.row_key}=${v.value}`).join(', '),
  },
])
const conflictRowKey = (row: { predicate: string }) => row.predicate
</script>

<template>
  <section class="graph-page">
    <PageHeader :title="t('page.graphEntityDetail')">
      <template #actions>
        <RouterLink :to="{ name: 'graph-entities', query: { graph: route.query.graph } }">{{
          t('page.graphEntities')
        }}</RouterLink>
        <NButton :loading="loading" @click="reload">{{ t('graph.refresh') }}</NButton>
      </template>
    </PageHeader>
    <NAlert v-if="error" type="error">{{ error }}</NAlert>
    <p v-if="loading" role="status">{{ t('common.loading') }}</p>
    <template v-if="data">
      <p class="iri">{{ data.detail.entity.iri }}</p>
      <p>{{ t('graph.type') }}: {{ data.detail.entity.type_iri }}</p>
      <p>{{ t('graph.resultSet', { id: data.detail.entity.graph_revision_id }) }}</p>
      <!-- G-30 实体 360 画像：分区跳转到各形态与追溯 -->
      <NSpace align="center" class="views-360">
        <span>{{ t('graph.views360') }}</span>
        <NButton
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
              },
            })
          "
        >
          {{ t(`graph.layout.${layout}`) }}
        </NButton>
        <RouterLink
          :to="{
            name: 'graph-evidence',
            query: { graph: data.detail.entity.graph_revision_id, iri: data.detail.entity.iri },
          }"
          >{{ t('graph.chainTitle') }}</RouterLink
        >
      </NSpace>
      <NTabs v-model:value="activeTab" type="line" animated>
        <NTabPane name="attrs" :tab="t('entityType.dataProps')">
          <NDataTable
            :columns="[
              { key: 'key', title: t('common.name') },
              { key: 'value', title: t('graph.value') },
            ]"
            :data="attrs"
            :row-key="attributeKey"
          />
        </NTabPane>
        <NTabPane name="out" :tab="t('graph.outgoing')">
          <GraphFactTable
            :items="data.detail.out_edges"
            :graph-revision-id="data.detail.entity.graph_revision_id"
          />
        </NTabPane>
        <NTabPane name="in" :tab="t('graph.incoming')">
          <GraphFactTable
            :items="data.detail.in_edges"
            :graph-revision-id="data.detail.entity.graph_revision_id"
          />
        </NTabPane>
        <NTabPane name="derived" :tab="t('graph.derived')">
          <NAlert type="info" class="notice">{{ t('graph.derivedHint') }}</NAlert>
          <GraphFactTable
            :items="data.detail.derived_edges"
            :graph-revision-id="data.detail.entity.graph_revision_id"
            derived
          />
        </NTabPane>
        <NTabPane name="evidence" :tab="t('page.graphEvidence')">
          <NAlert v-if="data.evidence.quarantined_count" type="warning" class="notice">{{
            t('graph.quarantineWarning')
          }}</NAlert>
          <NEmpty v-if="!data.evidence.total_count" :description="t('graph.noEvidence')" />
          <EvidenceTable v-else :items="data.evidence.evidences" @chain="openChain" />
        </NTabPane>
        <NTabPane name="fusion" :tab="t('graph.fusionTitle')">
          <p v-if="fusionLoading" role="status">{{ t('common.loading') }}</p>
          <NAlert v-if="fusionError" type="error">{{ fusionError }}</NAlert>
          <NEmpty v-if="fusion && !fusion.source_rows.length" :description="t('graph.noFusion')" />
          <template v-if="fusion && fusion.source_rows.length">
            <NAlert v-if="fusion.conflicts.length" type="warning" class="notice">{{
              t('graph.fusionConflictHint', { count: fusion.conflicts.length })
            }}</NAlert>
            <p>
              {{
                t('graph.fusionSummary', { sources: fusion.source_count, rows: fusion.row_count })
              }}
            </p>
            <NDataTable
              :columns="fusionColumns"
              :data="fusion.source_rows"
              :row-key="fusionRowKey"
            />
            <h3 v-if="fusion.conflicts.length">{{ t('graph.fusionConflicts') }}</h3>
            <NDataTable
              v-if="fusion.conflicts.length"
              :columns="conflictColumns"
              :data="fusion.conflicts"
              :row-key="conflictRowKey"
            />
          </template>
        </NTabPane>
      </NTabs>
    </template>
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
