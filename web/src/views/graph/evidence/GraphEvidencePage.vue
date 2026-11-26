<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import type { EvidenceItem, EvidenceTrace, ReverseTrace } from '@/api/graph'
import { graphApi } from '@/api/graph'
import { mappingsApi } from '@/api/mappings'
import PageHeader from '@/components/PageHeader.vue'
import {
  FormContainer,
  FormField,
  UiAlert,
  UiButton,
  UiEmpty,
  UiInput,
  UiInputNumber,
  UiRadioButton,
  UiRadioGroup,
} from '@/components/ui'
import type { FormInst, FormRules } from '@/components/ui/formTypes'
import { useApiError } from '@/composables/useApiError'
import { useAsyncData } from '@/composables/useAsyncData'
import EvidenceTable from '@/views/graph/components/EvidenceTable.vue'
import { useFrozenRelationLabels } from '@/views/graph/composables/useFrozenRelationLabels'
import FusionEvidence from '@/views/graph/evidence/components/FusionEvidence.vue'

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
const mode = ref<'entity' | 'fact' | 'reverse'>('entity')
const iri = ref('')
const subject = ref('')
const predicate = ref('')
const object = ref('')
const sourceId = ref<number | null>(null)
const reverseTable = ref('')
const reverseRowKey = ref('')
const formRef = ref<FormInst | null>(null)
const formModel = reactive({
  iri,
  subject,
  predicate,
  object,
  sourceId,
  reverseTable,
  reverseRowKey,
})
const rules = computed((): FormRules => {
  const required = { required: true, message: t('common.required') }
  if (mode.value === 'entity') return { iri: required }
  if (mode.value === 'fact') return { subject: required, predicate: required, object: required }
  return {
    sourceId: [required, { type: 'integer', min: 1, message: t('graph.sourceIdInvalid') }],
    reverseTable: [required, { max: 128, message: t('ds.form.maxLength', { max: 128 }) }],
    reverseRowKey: [required, { max: 256, message: t('ds.form.maxLength', { max: 256 }) }],
  }
})
const advancedOpen = ref(!route.query.iri && !route.query.subject)
const listContext = computed(() => ({
  graph: resolvedGraph.value ?? route.query.graph,
  kbReturn: kbReturn.value,
  q: route.query.q,
  page: route.query.page,
  size: route.query.size,
  sort: route.query.sort,
}))
function goEntities() {
  void router.push({ name: 'graph-entities', query: listContext.value })
}
const routeIdentity = computed(() =>
  JSON.stringify([
    route.query.iri ?? '',
    route.query.subject ?? '',
    route.query.predicate ?? '',
    route.query.object ?? '',
    route.query.graph ?? null,
  ]),
)
let resolvedRevision: number | undefined
watch(
  () => route.query.graph,
  () => {
    resolvedRevision = undefined
  },
  { flush: 'sync' },
)
const appliedMode = computed(() =>
  route.query.iri ? 'entity' : route.query.subject ? 'fact' : null,
)
watch(
  routeIdentity,
  () => {
    mode.value = appliedMode.value ?? 'entity'
    iri.value = String(route.query.iri ?? '')
    subject.value = String(route.query.subject ?? '')
    predicate.value = String(route.query.predicate ?? '')
    object.value = String(route.query.object ?? '')
  },
  { immediate: true },
)
const { data, error, loading, reload } = useAsyncData<EvidenceTrace>((signal) => {
  const [entity, s, p, o, graph] = JSON.parse(routeIdentity.value) as [
    string,
    string,
    string,
    string,
    string | null,
  ]
  const graphId = graph ? Number(graph) : resolvedRevision
  if (mode.value !== (entity ? 'entity' : 'fact')) return Promise.resolve(null)
  const request = entity
    ? graphApi.entityEvidence(entity, graphId, signal)
    : s && p && o
      ? graphApi.factEvidence({ subject: s, predicate: p, object: o }, graphId, signal)
      : Promise.resolve(null)
  return request.then((result) => {
    if (!signal.aborted && result) resolvedRevision = result.graph_revision_id
    return result
  })
})

const fusion = useAsyncData((signal) => {
  const [entity] = JSON.parse(routeIdentity.value) as [string]
  // Pin to the evidence result so a current-graph switch cannot mix two runs.
  const graphId = data.value?.graph_revision_id
  return mode.value === 'entity' && entity && graphId
    ? graphApi.entityFusion(entity, graphId, signal)
    : Promise.resolve(null)
})

// ===== 反向追溯（源行 → 产出实体/事实，V-TR-05） =====
const reverseResult = ref<ReverseTrace | null>(null)
const reverseError = ref('')
const reverseLoading = ref(false)
const resolvedGraph = computed(
  () =>
    (mode.value === 'reverse'
      ? reverseResult.value?.graph_revision_id
      : data.value?.graph_revision_id) ?? resolvedRevision,
)
const frozenLabels = useFrozenRelationLabels(
  () => resolvedGraph.value,
  () =>
    mode.value === 'reverse'
      ? (reverseResult.value?.facts ?? []).map((fact) => fact.predicate)
      : (data.value?.evidences ?? []).map((item) => item.predicate),
)
let reverseController: AbortController | null = null
watch(
  [sourceId, reverseTable, reverseRowKey, mode, routeIdentity],
  () => {
    reverseController?.abort()
    reverseResult.value = null
    reverseError.value = ''
    reverseLoading.value = false
  },
  { flush: 'sync' },
)
onBeforeUnmount(() => reverseController?.abort())
async function runReverse() {
  if (reverseLoading.value) return
  reverseError.value = ''
  if (
    !Number.isSafeInteger(sourceId.value) ||
    sourceId.value === null ||
    sourceId.value < 1 ||
    !reverseTable.value.trim() ||
    !reverseRowKey.value.trim() ||
    reverseTable.value.length > 128 ||
    reverseRowKey.value.length > 256
  )
    return
  reverseController?.abort()
  const controller = new AbortController()
  reverseController = controller
  reverseResult.value = null
  reverseLoading.value = true
  try {
    const result = await graphApi.reverseTrace(
      {
        source_id: sourceId.value,
        table: reverseTable.value,
        row_key: reverseRowKey.value,
      },
      route.query.graph ? Number(route.query.graph) : resolvedRevision,
      controller.signal,
    )
    if (!controller.signal.aborted) {
      resolvedRevision = result.graph_revision_id
      reverseResult.value = result
    }
  } catch (cause) {
    if (!controller.signal.aborted) reverseError.value = toMessage(cause)
  } finally {
    if (reverseController === controller) reverseLoading.value = false
  }
}

async function search() {
  if (mode.value === 'reverse') {
    await runReverse()
    return
  }
  const previous = routeIdentity.value
  await router.replace({
    name: 'graph-evidence',
    query: {
      ...route.query,
      kbReturn: kbReturn.value,
      returnEntity: route.query.returnEntity,
      graph: route.query.graph,
      ...(mode.value === 'entity'
        ? { iri: iri.value, subject: undefined, predicate: undefined, object: undefined }
        : {
            iri: undefined,
            subject: subject.value,
            predicate: predicate.value,
            object: object.value,
          }),
    },
  })
  if (routeIdentity.value === previous && !loading.value) reload()
}

// ===== 证据冻结链（G-26）：事实 → 来源行 → 运行 → 冻结版本 =====
const chainItem = ref<EvidenceItem | null>(null)
watch(
  [data, mode, routeIdentity],
  () => {
    chainItem.value = null
  },
  { flush: 'sync' },
)
const frozenMapping = useAsyncData((signal) => {
  const id = chainItem.value?.mapping_revision_id
  return id ? mappingsApi.revision(id, signal) : Promise.resolve(null)
})
const mappingOwner = useAsyncData((signal) => {
  const id = frozenMapping.data.value?.mapping_id
  return id ? mappingsApi.get(id, signal) : Promise.resolve(null)
})
function showChain(item: EvidenceItem) {
  if (mode.value !== 'reverse' && data.value?.evidences.includes(item)) chainItem.value = item
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
    {
      label: t('graph.chainFact'),
      value: `${item.subject} ${frozenLabels.name(item.predicate)} (${item.predicate}) ${item.object}`,
    },
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
</script>

<template>
  <section class="graph-page">
    <PageHeader :title="t('page.graphEvidence')" :eyebrow="t('studio.evidenceLedger')">
      <template #context
        ><span v-if="resolvedGraph" class="evidence-readout"
          >{{ t('graph.resultSet', { id: resolvedGraph }) }} · {{ t('ui.readOnlyLabel') }}</span
        ></template
      >
      <template #actions>
        <RouterLink v-if="kbReturn" :to="kbReturn">{{ t('kb.backToSearch') }}</RouterLink>
        <RouterLink
          v-if="typeof route.query.returnEntity === 'string'"
          :to="{
            name: 'graph-entity-detail',
            params: { id: route.query.returnEntity },
            query: listContext,
          }"
          >{{ t('graphUi.backObject') }}</RouterLink
        >
        <UiButton @click="advancedOpen = !advancedOpen">{{ t('graphUi.advancedQuery') }}</UiButton>
        <UiButton secondary @click="goEntities">{{ t('page.graphEntities') }}</UiButton>
      </template>
    </PageHeader>
    <FormContainer
      v-if="advancedOpen"
      ref="formRef"
      :model="formModel"
      :rules="rules"
      class="workspace-panel"
      @submit="search"
    >
      <UiRadioGroup v-model:value="mode" :aria-label="t('graph.traceMode')" class="modes">
        <UiRadioButton value="entity">{{ t('graph.byEntity') }}</UiRadioButton>
        <UiRadioButton value="fact">{{ t('graph.byFact') }}</UiRadioButton>
        <UiRadioButton value="reverse">{{ t('graph.bySourceRow') }}</UiRadioButton>
      </UiRadioGroup>
      <FormField
        v-if="mode === 'entity'"
        path="iri"
        :label="t('common.iri')"
        label-placement="left"
        :label-width="72"
      >
        <UiInput
          v-model:value="iri"
          :aria-label="t('common.iri')"
          :placeholder="t('graph.entityIri')"
        />
      </FormField>
      <template v-else-if="mode === 'fact'">
        <FormField
          path="subject"
          :label="t('graph.subject')"
          label-placement="left"
          :label-width="72"
          ><UiInput
            v-model:value="subject"
            :aria-label="t('graph.subject')"
            :placeholder="t('graph.subject')"
        /></FormField>
        <FormField
          path="predicate"
          :label="t('graph.predicate')"
          label-placement="left"
          :label-width="72"
          ><UiInput
            v-model:value="predicate"
            :aria-label="t('graph.predicate')"
            :placeholder="t('graph.predicate')"
        /></FormField>
        <FormField path="object" :label="t('graph.object')" label-placement="left" :label-width="72"
          ><UiInput
            v-model:value="object"
            :aria-label="t('graph.object')"
            :placeholder="t('graph.object')"
        /></FormField>
      </template>
      <template v-else>
        <FormField
          path="sourceId"
          :label="t('graph.reverseSource')"
          label-placement="left"
          :label-width="72"
        >
          <UiInputNumber
            v-model:value="sourceId"
            :min="1"
            :precision="0"
            :input-props="{ 'aria-label': t('graph.reverseSource') }"
          />
        </FormField>
        <FormField
          path="reverseTable"
          :label="t('graph.table')"
          label-placement="left"
          :label-width="72"
        >
          <UiInput
            v-model:value="reverseTable"
            :placeholder="t('graph.table')"
            :input-props="{ 'aria-label': t('graph.table') }"
          />
        </FormField>
        <FormField
          path="reverseRowKey"
          :label="t('graph.rowKey')"
          label-placement="left"
          :label-width="72"
        >
          <UiInput
            v-model:value="reverseRowKey"
            :placeholder="t('graph.rowKey')"
            :input-props="{ 'aria-label': t('graph.rowKey') }"
          />
        </FormField>
      </template>
      <UiButton attr-type="submit" type="primary" :aria-busy="loading || reverseLoading">{{
        t('graph.trace')
      }}</UiButton>
    </FormContainer>
    <p v-if="loading || reverseLoading" role="status">{{ t('common.loading') }}</p>
    <UiAlert v-if="mode !== 'reverse' && error" type="error"
      >{{ error }} <UiButton @click="reload">{{ t('ui.retry') }}</UiButton></UiAlert
    >
    <UiAlert v-if="frozenLabels.error.value" type="warning" role="alert">
      {{ frozenLabels.error.value }}
      <UiButton @click="frozenLabels.reload">{{ t('ui.retry') }}</UiButton>
    </UiAlert>
    <template v-if="mode === 'reverse'">
      <UiAlert v-if="reverseError" type="error"
        >{{ reverseError }} <UiButton @click="runReverse">{{ t('ui.retry') }}</UiButton></UiAlert
      >
      <template v-if="reverseResult">
        <p>
          {{
            t('graph.reverseSummary', {
              table: reverseResult.table_name,
              row: reverseResult.row_key,
              facts: n(reverseResult.facts.length),
              entities: n(reverseResult.entities.length),
            })
          }}
        </p>
        <ol class="reverse-facts">
          <li v-for="fact in reverseResult.facts" :key="fact.evidence_id">
            {{ fact.subject }} ·
            <span :title="fact.predicate">{{ frozenLabels.name(fact.predicate) }}</span>
            · {{ fact.object }}
          </li>
        </ol>
        <ul class="reverse-entities">
          <li v-for="entity in reverseResult.entities" :key="entity">
            <RouterLink
              :to="{
                name: 'graph-entity-detail',
                params: { id: entity },
                query: { ...listContext, graph: reverseResult.graph_revision_id },
              }"
              >{{ entity }}</RouterLink
            >
          </li>
        </ul>
      </template>
      <UiEmpty v-else-if="!reverseError && !reverseLoading" :description="t('graph.reverseHint')" />
    </template>
    <template v-if="mode === appliedMode && data">
      <div class="evidence-workspace">
        <section class="evidence-ledger">
          <div class="evidence-readout ledger-head">
            {{ t('graph.resultSet', { id: data.graph_revision_id }) }} ·
            {{ t('graph.totalEvidence', { n: n(data.total_count) }) }}
          </div>
          <UiAlert v-if="data.quarantined_count" type="warning">{{
            t('graph.quarantineWarning')
          }}</UiAlert>
          <EvidenceTable
            v-if="data.total_count"
            :items="data.evidences"
            :relation-labels="frozenLabels.labels.value"
            @chain="showChain"
          />
          <UiEmpty v-else :description="t('graph.noEvidence')" />
          <template v-if="mode === 'entity'">
            <p v-if="fusion.loading.value" role="status">{{ t('common.loading') }}</p>
            <UiAlert v-if="fusion.error.value" type="error">{{ fusion.error.value }}</UiAlert>
            <UiButton v-if="fusion.error.value" @click="fusion.reload">{{
              t('graph.refresh')
            }}</UiButton>
            <FusionEvidence v-if="fusion.data.value" :data="fusion.data.value" />
          </template>
        </section>
        <!-- G-26 证据溯源链：事实 → 来源行 → 运行 → 冻结版本 -->
        <aside class="chain-card">
          <header class="chain-heading">
            <h2>{{ t('graph.chainTitle') }}</h2>
            <UiButton v-if="chainItem" size="small" quaternary @click="chainItem = null">{{
              t('common.close')
            }}</UiButton>
          </header>
          <UiEmpty v-if="!chainItem" :description="t('studio.selectEvidence')" />
          <template v-else>
            <ol class="chain-list">
              <li v-for="step in frozenChain" :key="step.label">
                <span class="chain-label">{{ step.label }}</span>
                <span class="chain-value">{{ step.value }}</span>
              </li>
            </ol>
            <UiAlert v-if="frozenMapping.error.value || mappingOwner.error.value" type="error">{{
              frozenMapping.error.value || mappingOwner.error.value
            }}</UiAlert>
            <UiButton v-if="frozenMapping.error.value" @click="frozenMapping.reload">{{
              t('graph.refresh')
            }}</UiButton>
            <template v-if="frozenMapping.data.value">
              <h3>
                {{ t('graph.frozenMapping', { revision: frozenMapping.data.value.revision }) }}
              </h3>
              <p>{{ t('graph.frozenMappingHint') }}</p>
              <details>
                <summary>{{ t('graph.mappingConfiguration') }}</summary>
                <pre>{{
                  JSON.stringify(
                    {
                      entity_maps: frozenMapping.data.value.entity_maps,
                      rel_maps: frozenMapping.data.value.rel_maps,
                    },
                    null,
                    2,
                  )
                }}</pre>
              </details>
              <RouterLink
                :to="{
                  name: 'mapping-wizard',
                  query: { mapping: frozenMapping.data.value.mapping_id },
                }"
                >{{ t('graph.correctMapping') }}</RouterLink
              >
              <RouterLink
                v-if="mappingOwner.data.value"
                :to="{
                  name: 'ontology-export',
                  query: {
                    ontology: mappingOwner.data.value.ontology_id,
                    revision: frozenMapping.data.value.onto_version,
                  },
                }"
                >{{ t('graph.exportFrozenOntology') }}</RouterLink
              >
            </template>
          </template>
        </aside>
      </div>
    </template>
    <UiEmpty
      v-else-if="mode !== 'reverse' && !loading && !error"
      :description="t('graph.traceHint')"
    />
  </section>
</template>

<style scoped>
.graph-page {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 20px;
}
.graph-page > * {
  min-width: 0;
}
h2,
p {
  margin: 0;
}
.modes {
  grid-column: 1 / -1;
  margin-bottom: 4px;
}
.reverse-facts,
.reverse-entities {
  margin: 0;
  padding-left: 20px;
  font-size: var(--font-caption);
}
.chain-card {
  border: 1px solid var(--border-muted);
  border-radius: var(--radius-panel);
  background: var(--surface-panel);
  min-width: 0;
  padding: 16px;
  display: grid;
  align-content: start;
  gap: 16px;
}
.evidence-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 24px;
  align-items: start;
}
.evidence-ledger {
  min-width: 0;
  display: grid;
  gap: 16px;
}
.evidence-readout {
  color: var(--text-secondary);
  font-size: 12px;
}
.ledger-head {
  padding: 10px 16px;
  border-left: 2px solid var(--action-primary);
  background: var(--surface-muted);
}
.workspace-panel {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr)) auto;
  align-items: start;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--border-muted);
  border-radius: var(--radius-panel);
  background: var(--surface-muted);
}
.workspace-panel > :deep(.ui-form-field) {
  min-width: 0;
}
.workspace-panel > :deep(button[type='submit']) {
  justify-self: end;
}
.chain-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}
.chain-heading h2 {
  font-size: 14px;
  margin: 0;
}
.chain-card pre {
  max-height: 300px;
  overflow: auto;
  padding: 12px;
  background: var(--bg-inset);
  font-size: 11px;
}
.chain-card h3 {
  font-size: 13px;
  margin: 0;
}
@media (max-width: 64rem) {
  .evidence-workspace {
    grid-template-columns: minmax(0, 1fr);
  }
  .workspace-panel {
    grid-template-columns: minmax(0, 1fr);
  }
}
.chain-list {
  margin: 0;
  padding-left: 20px;
  display: grid;
  gap: 12px;
}
.chain-label {
  display: block;
  font-size: 12px;
  margin-bottom: 4px;
  color: var(--text-secondary);
}
.chain-value {
  word-break: break-all;
  font: 12px var(--font-mono, monospace);
}
</style>
