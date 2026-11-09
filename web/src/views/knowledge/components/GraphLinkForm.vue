<script setup lang="ts">
import { NAlert, NButton, NForm, NFormItem, NInput, NSelect } from 'naive-ui'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { graphApi } from '@/api/graph'
import { knowledgeApi, type KnowledgeEvidence } from '@/api/knowledge'
import { useDraftGuard } from '@/composables/useDraftGuard'
import { useAuthStore } from '@/stores/auth'

import { useKnowledgeAction, useKnowledgeRead } from '../composables/useKnowledge'

const props = defineProps<{ kbId: number; evidence: KnowledgeEvidence }>()
const emit = defineEmits<{ saved: [] }>()
const { t } = useI18n()
const auth = useAuthStore()
const open = ref(false)
const graph = ref<number | null>(null)
const entity = ref<string | null>(null)
const fact = ref<number | null>(null)
const query = ref('')
const committedQuery = ref('')
const guarded = useDraftGuard(open, () => ({
  graph: graph.value,
  entity: entity.value,
  fact: fact.value,
  query: query.value,
}))
watch(graph, () => {
  entity.value = null
  fact.value = null
  committedQuery.value = ''
  query.value = ''
})
watch(entity, () => {
  fact.value = null
})
const revisions = useKnowledgeRead((signal) =>
  open.value ? graphApi.revisions(signal) : Promise.resolve(null),
)
const documents = useKnowledgeRead((signal) =>
  open.value
    ? knowledgeApi.document(props.kbId, props.evidence.hit.document_id, signal)
    : Promise.resolve(null),
)
const entities = useKnowledgeRead((signal) =>
  open.value && graph.value
    ? graphApi.entities(
        { graph_revision_id: graph.value, q: committedQuery.value, page: 1, page_size: 30 },
        signal,
      )
    : Promise.resolve(null),
)
const detail = useKnowledgeRead((signal) =>
  open.value && graph.value && entity.value
    ? graphApi.detail(entity.value, graph.value, signal)
    : Promise.resolve(null),
)
const graphOptions = computed(() =>
  (revisions.data.value ?? []).map((value) => ({
    value: value.id,
    label: t('kb.graphRevision', { n: value.id }),
  })),
)
const entityOptions = computed(() =>
  (entities.data.value?.items ?? []).map((value) => ({
    value: value.iri,
    label: `${value.row_key} · ${value.iri}`,
  })),
)
const factOptions = computed(() =>
  (detail.data.value?.out_edges ?? []).map((edge) => ({
    value: edge.id,
    label: `${edge.predicate} → ${edge.object_}`,
  })),
)
const { busy, error, run } = useKnowledgeAction(
  () => `${props.kbId}:${props.evidence.hit.chunk_id}:${open.value}:${graph.value}:${entity.value}`,
)
const canSave = computed(
  () =>
    !!graph.value &&
    !!entity.value &&
    !!documents.data.value &&
    !documents.data.value.archived &&
    !documents.error.value &&
    !detail.error.value &&
    !detail.loading.value &&
    detail.data.value?.entity.iri === entity.value &&
    (fact.value == null || factOptions.value.some((value) => value.value === fact.value)),
)
async function save() {
  if (
    !canSave.value ||
    !['ADMIN', 'EDITOR'].includes(auth.user?.role ?? '') ||
    !graph.value ||
    !entity.value ||
    !documents.data.value
  )
    return
  const payload = { graph_revision_id: graph.value, entity_iri: entity.value, fact_id: fact.value }
  const result = await run((signal) =>
    knowledgeApi.link(
      props.kbId,
      props.evidence.hit.chunk_id,
      payload,
      documents.data.value!.revision,
      signal,
    ),
  )
  if (result) {
    open.value = false
    emit('saved')
  }
}
function confirmClose() {
  if (busy.value) return false
  guarded.value = false
  return !open.value
}
defineExpose({ confirmClose })
</script>

<template>
  <div class="kb-stack">
    <NButton v-if="!open" @click="open = true">{{ t('kb.addManualReference') }}</NButton>
    <NForm v-else class="kb-panel" @submit.prevent="save">
      <NAlert v-if="error" type="error" role="alert"
        >{{ error }}
        <NButton :disabled="busy" @click="documents.reload">{{ t('kb.refresh') }}</NButton></NAlert
      >
      <NAlert v-if="documents.error.value" type="error"
        >{{ documents.error.value }}
        <NButton @click="documents.reload">{{ t('kb.retry') }}</NButton></NAlert
      >
      <NAlert v-if="revisions.error.value" type="error"
        >{{ revisions.error.value }}
        <NButton @click="revisions.reload">{{ t('kb.retry') }}</NButton></NAlert
      >
      <NFormItem :label="t('kb.selectGraph')"
        ><NSelect
          v-model:value="graph"
          :options="graphOptions"
          :loading="revisions.loading.value"
          :disabled="busy"
          :aria-label="t('kb.selectGraph')"
      /></NFormItem>
      <NFormItem :label="t('kb.findEntity')" :label-props="{ for: 'kb-entity-query' }"
        ><div class="kb-toolbar">
          <NInput
            v-model:value="query"
            :input-props="{ id: 'kb-entity-query' }"
            :disabled="!graph || busy"
            @keydown.enter.prevent="committedQuery = query"
          /><NButton :disabled="!graph || busy" @click="committedQuery = query">{{
            t('kb.findEntity')
          }}</NButton>
        </div></NFormItem
      >
      <NAlert v-if="entities.error.value" type="error"
        >{{ entities.error.value }}
        <NButton @click="entities.reload">{{ t('kb.retry') }}</NButton></NAlert
      >
      <NFormItem :label="t('kb.selectEntity')"
        ><NSelect
          v-model:value="entity"
          :options="entityOptions"
          :loading="entities.loading.value"
          :disabled="!graph || busy"
          :aria-label="t('kb.selectEntity')"
      /></NFormItem>
      <p v-if="entities.data.value && entities.data.value.total > 30" class="kb-muted">
        {{ t('kb.refineEntity') }}
      </p>
      <NAlert v-if="detail.error.value" type="error"
        >{{ detail.error.value }}
        <NButton @click="detail.reload">{{ t('kb.retry') }}</NButton></NAlert
      >
      <NFormItem :label="t('kb.selectFact')"
        ><NSelect
          v-model:value="fact"
          clearable
          :options="factOptions"
          :loading="detail.loading.value"
          :disabled="!entity || busy"
          :aria-label="t('kb.selectFact')"
      /></NFormItem>
      <p class="kb-muted">{{ t('kb.directFactsOnly') }}</p>
      <div class="kb-actions">
        <NButton :disabled="busy" @click="guarded = false">{{ t('common.cancel') }}</NButton
        ><NButton type="primary" attr-type="submit" :disabled="!canSave || busy" :loading="busy">{{
          t('kb.saveReference')
        }}</NButton>
      </div>
    </NForm>
  </div>
</template>
