<script setup lang="ts">
import { NAlert, NButton, NDataTable, NEmpty, NSpace, NTabPane, NTabs } from 'naive-ui'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'

import { graphApi } from '@/api/graph'
import EvidenceTable from '@/components/EvidenceTable.vue'
import GraphFactTable from '@/components/GraphFactTable.vue'
import { useAsyncData } from '@/composables/useAsyncData'

const { t } = useI18n()
const route = useRoute()
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
</script>

<template>
  <section class="graph-page">
    <NSpace justify="space-between" align="center">
      <h2>{{ t('page.graphEntityDetail') }}</h2>
      <NSpace>
        <RouterLink :to="{ name: 'graph-entities', query: { graph: route.query.graph } }">{{
          t('page.graphEntities')
        }}</RouterLink>
        <NButton :loading="loading" @click="reload">{{ t('graph.refresh') }}</NButton>
      </NSpace>
    </NSpace>
    <NAlert v-if="error" type="error">{{ error }}</NAlert>
    <p v-if="loading" role="status">{{ t('common.loading') }}</p>
    <template v-if="data">
      <p class="iri">{{ data.detail.entity.iri }}</p>
      <p>{{ t('graph.type') }}: {{ data.detail.entity.type_iri }}</p>
      <p>{{ t('graph.resultSet', { id: data.detail.entity.graph_revision_id }) }}</p>
      <NTabs type="line" animated>
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
          <EvidenceTable v-else :items="data.evidence.evidences" />
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
.notice {
  margin-bottom: 16px;
}
</style>
