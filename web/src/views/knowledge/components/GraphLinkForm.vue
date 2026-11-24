<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { graphApi } from '@/api/graph'
import { knowledgeApi, type KnowledgeEvidence } from '@/api/knowledge'
import type { FormInst, FormRules } from '@/components/ui'
import {
  FormActions,
  FormContainer,
  FormField,
  FormSection,
  SearchPanel,
  UiAlert,
  UiButton,
  UiSelect,
} from '@/components/ui'
import { useDraftGuard } from '@/composables/useDraftGuard'
import { useOwnedMutation } from '@/composables/useOwnedMutation'
import { useAuthStore } from '@/stores/auth'

import {
  useKnowledgeActor,
  useKnowledgeMessage,
  useKnowledgeRead,
} from '../composables/useKnowledge'

const props = withDefaults(
  defineProps<{
    kbId: number
    evidence: KnowledgeEvidence
    baseArchived?: boolean
    disabled?: boolean
  }>(),
  { baseArchived: false, disabled: false },
)
const emit = defineEmits<{ saved: [] }>()
const { t } = useI18n()
const auth = useAuthStore()
const actor = useKnowledgeActor()
const { message } = useKnowledgeMessage()
const open = ref(false)
const graph = ref<number | null>(null)
const entity = ref<string | null>(null)
const fact = ref<number | null>(null)
const query = ref('')
const committedQuery = ref('')
const formRef = ref<FormInst | null>(null)
const form = computed(() => ({ graph: graph.value, entity: entity.value, fact: fact.value }))
const evidenceKey = computed(() =>
  JSON.stringify([
    props.kbId,
    props.evidence.hit.document_id,
    props.evidence.hit.chunk_id,
    props.evidence.hit.generation,
  ]),
)
const guarded = useDraftGuard(
  open,
  () => ({ ...form.value, query: query.value }),
  () => true,
  () => evidenceKey.value,
)
watch(
  evidenceKey,
  () => {
    open.value = false
    graph.value = null
    entity.value = null
    fact.value = null
    query.value = ''
    committedQuery.value = ''
  },
  { flush: 'sync' },
)
watch(
  graph,
  () => {
    entity.value = null
    fact.value = null
    committedQuery.value = ''
    query.value = ''
  },
  { flush: 'sync' },
)
watch(
  entity,
  () => {
    fact.value = null
  },
  { flush: 'sync' },
)
const revisions = useKnowledgeRead((signal) =>
  open.value ? graphApi.revisions(signal) : Promise.resolve(null),
)
const documents = useKnowledgeRead((signal) =>
  open.value
    ? knowledgeApi.document(props.kbId, props.evidence.hit.document_id, signal)
    : Promise.resolve(null),
)
const entities = useKnowledgeRead((signal) =>
  open.value && graph.value != null
    ? graphApi.entities(
        { graph_revision_id: graph.value, q: committedQuery.value, page: 1, page_size: 30 },
        signal,
      )
    : Promise.resolve(null),
)
const detail = useKnowledgeRead((signal) =>
  open.value && graph.value != null && entity.value
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
const canWrite = computed(
  () =>
    ['ADMIN', 'EDITOR'].includes(auth.user?.role ?? '') &&
    !props.baseArchived &&
    !props.evidence.archived &&
    !props.evidence.historical,
)
const canEdit = computed(() => canWrite.value && !props.disabled)
const canSave = computed(
  () =>
    open.value &&
    canEdit.value &&
    Number.isSafeInteger(graph.value) &&
    (graph.value ?? 0) > 0 &&
    !!entity.value &&
    graphOptions.value.some((option) => option.value === graph.value) &&
    entityOptions.value.some((option) => option.value === entity.value) &&
    !revisions.error.value &&
    !revisions.loading.value &&
    !entities.error.value &&
    !entities.loading.value &&
    documents.data.value?.id === props.evidence.hit.document_id &&
    !documents.data.value.archived &&
    !documents.error.value &&
    !documents.loading.value &&
    !detail.error.value &&
    !detail.loading.value &&
    detail.data.value?.entity.iri === entity.value &&
    (fact.value == null || factOptions.value.some((option) => option.value === fact.value)),
)
const rules = computed<FormRules>(() => ({
  graph: {
    required: true,
    type: 'integer',
    validator: (_rule, value) =>
      graphOptions.value.some((option) => option.value === value) || t('common.required'),
  },
  entity: {
    required: true,
    validator: (_rule, value) =>
      entityOptions.value.some((option) => option.value === value) || t('common.required'),
  },
  fact: {
    validator: (_rule, value) =>
      value == null ||
      factOptions.value.some((option) => option.value === value) ||
      t('common.required'),
  },
}))
const { busy, error, run } = useOwnedMutation(
  () =>
    JSON.stringify([
      evidenceKey.value,
      open.value,
      graph.value,
      entity.value,
      fact.value,
      canWrite.value,
      actor.value,
    ]),
  (error) =>
    error instanceof Error && ['FORM_INVALID', 'FORM_CONTEXT_CHANGED'].includes(error.message)
      ? ''
      : message(error),
)
function searchEntities(value: string) {
  if (graph.value == null || busy.value || !canEdit.value) return
  const next = value.trim()
  if (committedQuery.value === next) entities.reload()
  else committedQuery.value = next
}
function resetSearch() {
  if (busy.value || !canEdit.value) return
  query.value = ''
  entity.value = null
  searchEntities('')
}
async function save() {
  if (!canSave.value || busy.value || !formRef.value) return
  const kbId = props.kbId
  const chunkId = props.evidence.hit.chunk_id
  const revision = documents.data.value!.revision
  const payload = {
    graph_revision_id: graph.value!,
    entity_iri: entity.value!,
    fact_id: fact.value,
  }
  const result = await run(async (signal) => {
    await formRef.value!.validate()
    if (signal.aborted || !canSave.value) throw new Error('FORM_CONTEXT_CHANGED')
    return knowledgeApi.link(kbId, chunkId, payload, revision, signal)
  })
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
    <UiButton v-if="!open" :disabled="!canEdit" @click="open = true">{{
      t('kb.addManualReference')
    }}</UiButton>
    <div v-else class="kb-panel kb-stack">
      <UiAlert v-if="error" type="error" role="alert"
        >{{ error
        }}<UiButton :disabled="busy" @click="documents.reload">{{
          t('kb.refresh')
        }}</UiButton></UiAlert
      >
      <UiAlert v-if="documents.error.value" type="error"
        >{{ documents.error.value
        }}<UiButton @click="documents.reload">{{ t('kb.retry') }}</UiButton></UiAlert
      >
      <UiAlert v-if="revisions.error.value" type="error"
        >{{ revisions.error.value
        }}<UiButton @click="revisions.reload">{{ t('kb.retry') }}</UiButton></UiAlert
      >
      <SearchPanel
        v-model:query="query"
        :label="t('kb.findEntity')"
        :disabled="graph == null || busy || !canEdit"
        :loading="entities.loading.value"
        @submit="searchEntities"
        @clear="searchEntities('')"
        @reset="resetSearch"
      />
      <FormContainer
        ref="formRef"
        :model="form"
        :rules="rules"
        :disabled="busy || !canEdit"
        :submitting="busy"
        @submit="save"
      >
        <FormSection :title="t('kb.selectGraph')">
          <FormField path="graph" :label="t('kb.selectGraph')" required
            ><UiSelect
              v-model:value="graph"
              :options="graphOptions"
              :loading="revisions.loading.value"
          /></FormField>
        </FormSection>
        <FormSection :title="t('kb.findEntity')">
          <UiAlert v-if="entities.error.value" type="error"
            >{{ entities.error.value
            }}<UiButton @click="entities.reload">{{ t('kb.retry') }}</UiButton></UiAlert
          >
          <FormField path="entity" :label="t('kb.selectEntity')" required
            ><UiSelect
              v-model:value="entity"
              :options="entityOptions"
              :loading="entities.loading.value"
              :disabled="graph == null"
          /></FormField>
          <p v-if="entities.data.value && entities.data.value.total > 30" class="kb-muted">
            {{ t('kb.refineEntity') }}
          </p>
          <UiAlert v-if="detail.error.value" type="error"
            >{{ detail.error.value
            }}<UiButton @click="detail.reload">{{ t('kb.retry') }}</UiButton></UiAlert
          >
        </FormSection>
        <FormSection :title="t('kb.selectFact')">
          <FormField path="fact" :label="t('kb.selectFact')" :help="t('kb.directFactsOnly')"
            ><UiSelect
              v-model:value="fact"
              clearable
              :options="factOptions"
              :loading="detail.loading.value"
              :disabled="!entity"
          /></FormField>
        </FormSection>
        <FormActions :submitting="busy">
          <UiButton :disabled="busy" @click="guarded = false">{{ t('common.cancel') }}</UiButton>
          <UiButton
            type="primary"
            attr-type="submit"
            :disabled="!canSave || busy"
            :loading="busy"
            >{{ t('kb.saveReference') }}</UiButton
          >
        </FormActions>
      </FormContainer>
    </div>
  </div>
</template>
