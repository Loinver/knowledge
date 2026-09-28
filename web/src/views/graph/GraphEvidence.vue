<script setup lang="ts">
import {
  NAlert,
  NButton,
  NCard,
  NEmpty,
  NFormItem,
  NInput,
  NInputNumber,
  NRadioButton,
  NRadioGroup,
} from 'naive-ui'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import type { EvidenceItem, EvidenceTrace, ReverseTrace } from '@/api/graph'
import { graphApi } from '@/api/graph'
import PageHeader from '@/components/PageHeader.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import EvidenceTable from '@/views/graph/components/EvidenceTable.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const mode = ref<'entity' | 'fact' | 'reverse'>('entity')
const iri = ref('')
const subject = ref('')
const predicate = ref('')
const object = ref('')
const sourceId = ref<number | null>(null)
const reverseTable = ref('')
const reverseRowKey = ref('')
function goEntities() {
  void router.push({ name: 'graph-entities', query: { graph: route.query.graph } })
}
watch(
  () => route.query,
  (query) => {
    mode.value = query.subject ? 'fact' : 'entity'
    iri.value = String(query.iri ?? '')
    subject.value = String(query.subject ?? '')
    predicate.value = String(query.predicate ?? '')
    object.value = String(query.object ?? '')
  },
  { immediate: true },
)
const { data, error, loading, reload } = useAsyncData<EvidenceTrace>((signal) => {
  const query = route.query
  const graphId = query.graph ? Number(query.graph) : undefined
  if (query.iri) return graphApi.entityEvidence(String(query.iri), graphId, signal)
  if (query.subject && query.predicate && query.object) {
    return graphApi.factEvidence(
      {
        subject: String(query.subject),
        predicate: String(query.predicate),
        object: String(query.object),
      },
      graphId,
      signal,
    )
  }
  return Promise.resolve(null)
})

// ===== 反向追溯（源行 → 产出实体/事实，V-TR-05） =====
const reverseResult = ref<ReverseTrace | null>(null)
const reverseError = ref('')
async function runReverse() {
  reverseError.value = ''
  if (!sourceId.value || !reverseTable.value || !reverseRowKey.value) return
  try {
    reverseResult.value = await graphApi.reverseTrace(
      {
        source_id: sourceId.value,
        table: reverseTable.value,
        row_key: reverseRowKey.value,
      },
      route.query.graph ? Number(route.query.graph) : undefined,
      new AbortController().signal,
    )
  } catch (cause) {
    reverseError.value = String(cause)
  }
}

async function search() {
  if (mode.value === 'reverse') {
    await runReverse()
    return
  }
  await router.replace({
    name: 'graph-evidence',
    query: {
      graph: route.query.graph,
      ...(mode.value === 'entity'
        ? { iri: iri.value }
        : { subject: subject.value, predicate: predicate.value, object: object.value }),
    },
  })
  reload()
}

// ===== 证据冻结链（G-26）：事实 → 来源行 → 运行 → 冻结版本 =====
const chainItem = ref<EvidenceItem | null>(null)
function showChain(item: EvidenceItem) {
  chainItem.value = item
}

type TransformEntry = {
  column?: string | null
  target?: string | null
  transform?: string | null
  params?: Record<string, unknown> | null
}

/** 属性级转换链：columns 只说"用了哪些列"，这一列才说"值是怎么算出来的"。 */
function transformText(item: EvidenceItem) {
  const chain = (item.column_transforms ?? []) as TransformEntry[]
  if (!chain.length) return t('graph.chainNoTransform')
  return chain
    .map((entry) => {
      const params =
        entry.params && Object.keys(entry.params).length ? ` ${JSON.stringify(entry.params)}` : ''
      const target = entry.target ? ` → ${entry.target}` : ''
      return `${entry.column ?? '?'}${target}: ${entry.transform ?? 'IDENTITY'}${params}`
    })
    .join('； ')
}

const frozenChain = computed(() => {
  const item = chainItem.value
  if (!item) return []
  return [
    { label: t('graph.chainFact'), value: `${item.subject} ${item.predicate} ${item.object}` },
    {
      label: t('graph.chainSource'),
      value: `${item.source_name ?? item.source_id} · ${item.table_name} · ${item.row_key}`,
    },
    { label: t('graph.chainFields'), value: item.columns.join(', ') },
    { label: t('graph.chainTransforms'), value: transformText(item) },
    { label: t('graph.chainRun'), value: `#${item.run_id}` },
    {
      label: t('graph.chainMapping'),
      value: item.mapping_revision_id ? `#${item.mapping_revision_id}` : t('graph.chainUnpinned'),
    },
    {
      label: t('graph.chainOntology'),
      value: item.ontology_revision ? `#${item.ontology_revision}` : t('graph.chainUnpinned'),
    },
    {
      label: t('graph.chainResources'),
      value: item.resource_revisions
        ? Object.entries(item.resource_revisions)
            .map(([id, rev]) => `#${id}r${rev}`)
            .join(', ')
        : t('graph.chainUnpinned'),
    },
    {
      label: t('graph.chainRules'),
      value: item.rule_revisions
        ? Object.entries(item.rule_revisions)
            .map(([id, rev]) => `${id}r${rev}`)
            .join(', ')
        : t('graph.chainUnpinned'),
    },
  ]
})
const canSubmit = computed(() =>
  mode.value === 'entity'
    ? !!iri.value
    : mode.value === 'fact'
      ? !!subject.value && !!predicate.value && !!object.value
      : !!sourceId.value && !!reverseTable.value && !!reverseRowKey.value,
)
</script>

<template>
  <section class="graph-page">
    <PageHeader :title="t('page.graphEvidence')" :description="t('graph.traceHint')">
      <template #actions>
        <NButton secondary @click="goEntities">{{ t('page.graphEntities') }}</NButton>
      </template>
    </PageHeader>
    <form @submit.prevent="search">
      <NRadioGroup
        v-model:value="mode"
        :aria-label="t('graph.traceMode')"
        class="modes"
        @update:value="reverseResult = null"
      >
        <NRadioButton value="entity">{{ t('graph.byEntity') }}</NRadioButton>
        <NRadioButton value="fact">{{ t('graph.byFact') }}</NRadioButton>
        <NRadioButton value="reverse">{{ t('graph.bySourceRow') }}</NRadioButton>
      </NRadioGroup>
      <NFormItem
        v-if="mode === 'entity'"
        :label="t('common.iri')"
        label-placement="left"
        :label-width="72"
      >
        <NInput
          v-model:value="iri"
          :aria-label="t('common.iri')"
          :placeholder="t('graph.entityIri')"
        />
      </NFormItem>
      <template v-else-if="mode === 'fact'">
        <NFormItem :label="t('graph.subject')" label-placement="left" :label-width="72"
          ><NInput
            v-model:value="subject"
            :aria-label="t('graph.subject')"
            :placeholder="t('graph.subject')"
        /></NFormItem>
        <NFormItem :label="t('graph.predicate')" label-placement="left" :label-width="72"
          ><NInput
            v-model:value="predicate"
            :aria-label="t('graph.predicate')"
            :placeholder="t('graph.predicate')"
        /></NFormItem>
        <NFormItem :label="t('graph.object')" label-placement="left" :label-width="72"
          ><NInput
            v-model:value="object"
            :aria-label="t('graph.object')"
            :placeholder="t('graph.object')"
        /></NFormItem>
      </template>
      <template v-else>
        <NFormItem :label="t('graph.reverseSource')" label-placement="left" :label-width="72">
          <NInputNumber
            v-model:value="sourceId"
            :min="1"
            :precision="0"
            :input-props="{ 'aria-label': t('graph.reverseSource') }"
          />
        </NFormItem>
        <NFormItem :label="t('graph.table')" label-placement="left" :label-width="72">
          <NInput
            v-model:value="reverseTable"
            :placeholder="t('graph.table')"
            :input-props="{ 'aria-label': t('graph.table') }"
          />
        </NFormItem>
        <NFormItem :label="t('graph.rowKey')" label-placement="left" :label-width="72">
          <NInput
            v-model:value="reverseRowKey"
            :placeholder="t('graph.rowKey')"
            :input-props="{ 'aria-label': t('graph.rowKey') }"
          />
        </NFormItem>
      </template>
      <NButton attr-type="submit" type="primary" :loading="loading" :disabled="!canSubmit">{{
        t('graph.trace')
      }}</NButton>
    </form>
    <NAlert v-if="error" type="error">{{ error }}</NAlert>
    <template v-if="mode === 'reverse'">
      <NAlert v-if="reverseError" type="error">{{ reverseError }}</NAlert>
      <template v-if="reverseResult">
        <p>
          {{
            t('graph.reverseSummary', {
              table: reverseResult.table_name,
              row: reverseResult.row_key,
              facts: reverseResult.facts.length,
              entities: reverseResult.entities.length,
            })
          }}
        </p>
        <ol class="reverse-facts">
          <li v-for="fact in reverseResult.facts" :key="fact.evidence_id">
            {{ fact.subject }} · {{ fact.predicate }} · {{ fact.object }}
          </li>
        </ol>
        <ul class="reverse-entities">
          <li v-for="entity in reverseResult.entities" :key="entity">
            <RouterLink
              :to="{
                name: 'graph-entity-detail',
                params: { id: entity },
                query: { graph: route.query.graph },
              }"
              >{{ entity }}</RouterLink
            >
          </li>
        </ul>
      </template>
      <NEmpty v-else-if="!reverseError" :description="t('graph.reverseHint')" />
    </template>
    <template v-if="mode !== 'reverse' && data">
      <p>
        {{ t('graph.resultSet', { id: data.graph_revision_id }) }} ·
        {{ t('graph.totalEvidence', { n: data.total_count }) }}
      </p>
      <NAlert v-if="data.quarantined_count" type="warning">{{
        t('graph.quarantineWarning')
      }}</NAlert>
      <EvidenceTable v-if="data.total_count" :items="data.evidences" @chain="showChain" />
      <NEmpty v-else :description="t('graph.noEvidence')" />
      <!-- G-26 证据溯源链：事实 → 来源行 → 运行 → 冻结版本 -->
      <NCard v-if="chainItem" :title="t('graph.chainTitle')" class="chain-card">
        <ol class="chain-list">
          <li v-for="step in frozenChain" :key="step.label">
            <span class="chain-label">{{ step.label }}</span>
            <span class="chain-value">{{ step.value }}</span>
          </li>
        </ol>
      </NCard>
    </template>
    <NEmpty
      v-else-if="mode !== 'reverse' && !loading && !error"
      :description="t('graph.traceHint')"
    />
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
.modes {
  margin-bottom: 16px;
}
.reverse-facts,
.reverse-entities {
  margin: 0;
  padding-left: 20px;
  font-size: var(--font-caption);
}
.chain-card {
  border: 1px solid var(--border);
}
.chain-list {
  margin: 0;
  padding-left: 20px;
  display: grid;
  gap: 6px;
}
.chain-label {
  display: inline-block;
  min-width: 140px;
  color: var(--text-secondary);
}
.chain-value {
  word-break: break-all;
}
</style>
