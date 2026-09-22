<script setup lang="ts">
import {
  NAlert,
  NButton,
  NCheckbox,
  NEmpty,
  NInputNumber,
  NSelect,
  NSpace,
  NTabPane,
  NTabs,
} from 'naive-ui'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { graphApi } from '@/api/graph'
import GraphCanvas from '@/components/GraphCanvas.vue'
import GraphFactTable from '@/components/GraphFactTable.vue'
import { useAsyncData } from '@/composables/useAsyncData'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const center = computed(() => (typeof route.query.center === 'string' ? route.query.center : ''))
const graphId = computed(() => (route.query.graph ? Number(route.query.graph) : undefined))
const depth = ref(1)
const excludedTypes = ref<string[]>([])
const includeDerived = ref(true)
const searchText = ref('')
const { data, loading, error, reload } = useAsyncData((signal) =>
  graphApi.view(
    {
      graph_revision_id: graphId.value,
      center: center.value,
      depth: depth.value,
      excluded_types: excludedTypes.value,
      include_derived: includeDerived.value,
    },
    signal,
  ),
)
const search = useAsyncData((signal) =>
  graphApi.entities(
    {
      graph_revision_id: graphId.value ?? data.value?.graph_revision_id,
      q: searchText.value,
      page_size: 20,
    },
    signal,
  ),
)
const searchOptions = computed(
  () =>
    search.data.value?.items.map((node) => ({
      value: node.iri,
      label: `${node.attrs.name ?? node.row_key} · ${node.iri}`,
    })) ?? [],
)
const typeOptions = computed(
  () =>
    data.value?.type_counts.map((type) => ({
      value: type.type_iri,
      label: `${type.type_iri} (${type.count})`,
    })) ?? [],
)
function explore(iri: string | null) {
  void router.replace({
    query: {
      ...route.query,
      graph: graphId.value ?? data.value?.graph_revision_id,
      center: iri || undefined,
    },
  })
}
function selectGraph(id: number | null) {
  excludedTypes.value = []
  void router.replace({ query: { graph: id || undefined } })
}
</script>

<template>
  <section class="graph-page">
    <NSpace justify="space-between" align="center">
      <h2>{{ t('page.graphBrowse') }}</h2>
      <RouterLink :to="{ name: 'graph-entities', query: { graph: data?.graph_revision_id } }">{{
        t('page.graphEntities')
      }}</RouterLink>
    </NSpace>
    <div class="controls">
      <label>
        <span>{{ t('graph.searchHint') }}</span>
        <NSelect
          :value="center || null"
          :options="searchOptions"
          :loading="search.loading.value"
          filterable
          remote
          clearable
          :placeholder="t('graph.searchHint')"
          :aria-label="t('graph.searchHint')"
          @search="searchText = $event"
          @update:value="explore"
        />
      </label>
      <label>
        <span>{{ t('graph.depth') }}</span>
        <NSelect
          v-model:value="depth"
          :disabled="!center"
          :options="[
            { label: t('graph.oneDegree'), value: 1 },
            { label: t('graph.twoDegrees'), value: 2 },
          ]"
          :aria-label="t('graph.depth')"
        />
      </label>
      <label>
        <span>{{ t('graph.revisionInput') }}</span>
        <NInputNumber
          :value="graphId ?? null"
          :min="1"
          :precision="0"
          clearable
          :placeholder="t('graph.currentResult')"
          :aria-label="t('graph.revisionInput')"
          @update:value="selectGraph"
        />
      </label>
    </div>
    <NAlert v-if="search.error.value" type="warning">{{ search.error.value }}</NAlert>
    <NSpace align="center">
      <NButton :disabled="!center" @click="explore(null)">{{ t('graph.overview') }}</NButton>
      <NCheckbox v-model:checked="includeDerived">{{ t('graph.showDerived') }}</NCheckbox>
      <NButton :loading="loading" @click="reload">{{ t('graph.refresh') }}</NButton>
      <RouterLink
        v-if="center && data"
        :to="{
          name: 'graph-entity-detail',
          params: { id: center },
          query: { graph: data.graph_revision_id },
        }"
        >{{ t('page.graphEntityDetail') }}</RouterLink
      >
    </NSpace>
    <label>
      <span>{{ t('graph.hiddenTypes') }}</span>
      <NSelect
        v-model:value="excludedTypes"
        :options="typeOptions"
        multiple
        clearable
        :aria-label="t('graph.hiddenTypes')"
        :placeholder="t('graph.hiddenTypes')"
      />
    </label>
    <NAlert v-if="error" type="warning">{{ error }}</NAlert>
    <p v-if="loading" role="status">{{ t('common.loading') }}</p>
    <template v-if="data">
      <p>
        {{ t('graph.resultSet', { id: data.graph_revision_id }) }} ·
        {{
          t('graph.visibleCounts', {
            nodes: data.nodes.length,
            edges: data.edges.length,
            total: data.entity_total,
          })
        }}
      </p>
      <NAlert v-if="data.truncated" type="warning">{{ t('graph.truncated') }}</NAlert>
      <NAlert v-if="data.quarantine_count" type="warning">{{
        t('graph.graphQuarantine', { count: data.quarantine_count, run: data.run_id })
      }}</NAlert>
      <NEmpty v-if="!data.nodes.length" :description="t('graph.noVisibleNodes')" />
      <template v-else>
        <GraphCanvas :graph="data" :neighborhood="!!center" @select="explore" />
        <NTabs type="line" animated>
          <NTabPane name="direct" :tab="t('graph.directRelation')">
            <GraphFactTable
              :items="data.edges.filter((edge) => edge.kind === 'DIRECT')"
              :graph-revision-id="data.graph_revision_id"
            />
          </NTabPane>
          <NTabPane name="derived" :tab="t('graph.derived')">
            <p>{{ t('graph.derivedHint') }}</p>
            <GraphFactTable
              :items="data.edges.filter((edge) => edge.kind === 'DERIVED')"
              :graph-revision-id="data.graph_revision_id"
              derived
            />
          </NTabPane>
        </NTabs>
      </template>
    </template>
  </section>
</template>

<style scoped>
.graph-page {
  display: grid;
  gap: 16px;
  min-width: 0;
}
h2,
p {
  margin: 0;
}
.controls {
  display: grid;
  grid-template-columns: minmax(220px, 2fr) minmax(130px, 1fr) minmax(170px, 1fr);
  gap: 16px;
}
label {
  display: grid;
  gap: 8px;
}
@media (max-width: 900px) {
  .controls {
    grid-template-columns: 1fr;
  }
}
</style>
