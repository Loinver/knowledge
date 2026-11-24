<script setup lang="ts">
import { computed, nextTick, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteUpdate, RouterLink, useRoute, useRouter } from 'vue-router'

import { knowledgeApi } from '@/api/knowledge'
import { UiAlert, UiButton, UiDrawer, UiDrawerContent, UiSpin, UiTag } from '@/components/ui'
import { useAuthStore } from '@/stores/auth'

import {
  evidenceSegments,
  useKnowledgeAction,
  useKnowledgeActor,
  useKnowledgeRead,
} from '../composables/useKnowledge'
import GraphLinkForm from './GraphLinkForm.vue'

const props = defineProps<{ kbId: number; baseArchived: boolean }>()
defineEmits<{ closed: [] }>()
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const chunk = computed(() => (typeof route.query.evidence === 'string' ? route.query.evidence : ''))
const { data, error, loading, reload } = useKnowledgeRead((signal) => {
  const kb = props.kbId
  const evidence = chunk.value
  return evidence ? knowledgeApi.evidence(kb, evidence, signal) : Promise.resolve(null)
})
const readKey = computed(() => JSON.stringify([props.kbId, chunk.value]))
const snapshot = shallowRef<{ key: string; value: NonNullable<typeof data.value> } | null>(null)
watch(
  data,
  (value) => {
    if (value) snapshot.value = { key: readKey.value, value }
  },
  { flush: 'sync' },
)
const current = computed(() =>
  snapshot.value?.key === readKey.value ? snapshot.value.value : null,
)
const actor = useKnowledgeActor()
const {
  busy,
  error: actionError,
  run,
} = useKnowledgeAction(() => JSON.stringify([readKey.value, actor.value]))
const canWrite = computed(
  () =>
    ['ADMIN', 'EDITOR'].includes(auth.user?.role ?? '') &&
    !props.baseArchived &&
    !current.value?.archived &&
    !current.value?.historical &&
    !!current.value &&
    !error.value &&
    !loading.value,
)
const segments = computed(() =>
  current.value
    ? evidenceSegments(
        current.value.normalized_text,
        current.value.hit.location.start_offset,
        current.value.hit.location.end_offset,
      )
    : ['', '', ''],
)
const highlight = ref<HTMLElement | null>(null)
const linkForm = ref<InstanceType<typeof GraphLinkForm> | null>(null)
watch(data, async (value) => {
  if (value) {
    await nextTick()
    highlight.value?.scrollIntoView({ block: 'center' })
  }
})
function close() {
  if (linkForm.value && !linkForm.value.confirmClose()) return
  void router.push({ query: { ...route.query, evidence: undefined } })
}
onBeforeRouteUpdate((to, from) => {
  if (to.query.evidence !== from.query.evidence || to.params.id !== from.params.id) {
    return linkForm.value?.confirmClose() ?? true
  }
  return true
})
async function download() {
  const hit = data.value?.hit
  if (!hit || busy.value || loading.value || error.value) return
  const blob = await run((signal) => knowledgeApi.original(props.kbId, hit.document_id, signal))
  if (!blob) return
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = hit.document_name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
</script>

<template>
  <UiDrawer
    :show="!!chunk"
    :width="'min(760px, 100vw)'"
    :close-on-esc="!busy"
    :mask-closable="!busy"
    @update:show="!$event && close()"
    @after-leave="$emit('closed')"
  >
    <UiDrawerContent :title="t('kb.evidence')" :closable="!busy">
      <div class="kb-stack kb-inspector-content">
        <UiAlert v-if="error" type="error" role="alert"
          >{{ error }} <UiButton @click="reload">{{ t('kb.retry') }}</UiButton></UiAlert
        >
        <UiAlert v-if="actionError" type="error" role="alert">{{ actionError }}</UiAlert>
        <UiSpin :show="loading">
          <p v-if="loading" role="status">{{ t('kb.loading') }}</p>
          <div v-if="current" class="kb-stack">
            <h2 class="kb-wrap">{{ current.hit.document_name }}</h2>
            <div class="kb-meta">
              <span>{{ current.hit.kb_name }}</span
              ><span>{{ t('kb.generation', { n: current.hit.generation }) }}</span
              ><span>{{
                t('kb.lines', {
                  start: current.hit.location.start_line,
                  end: current.hit.location.end_line,
                })
              }}</span
              ><span v-if="current.hit.location.paragraph_number != null">{{
                t('kb.paragraph', { n: current.hit.location.paragraph_number })
              }}</span
              ><span v-if="current.hit.location.row_number != null">{{
                t('kb.row', { n: current.hit.location.row_number })
              }}</span
              ><span>{{ current.hit.section }}</span>
            </div>
            <UiAlert v-if="current.historical || current.archived" type="warning">{{
              t(current.archived ? 'kb.archivedEvidence' : 'kb.historicalEvidence')
            }}</UiAlert>
            <div class="kb-actions">
              <UiButton :loading="busy" @click="download">{{ t('kb.original') }}</UiButton
              ><UiTag size="small"
                >{{ current.parser_version }} · {{ current.chunker_version }}</UiTag
              >
            </div>
            <p class="kb-muted">{{ t('kb.normalizedSource') }}</p>
            <div class="kb-source" tabindex="0" :aria-label="t('kb.evidence')">
              <span>{{ segments[0] }}</span
              ><mark ref="highlight" data-testid="kb-evidence-highlight">{{ segments[1] }}</mark
              ><span>{{ segments[2] }}</span>
            </div>
            <h2>{{ t('kb.manualReference') }}</h2>
            <p class="kb-muted">{{ t('kb.manualExplanation') }}</p>
            <div v-for="link in current.hit.graph_links" :key="link.id" class="kb-panel kb-stack">
              <RouterLink
                :to="{
                  name: 'graph-browse',
                  query: {
                    graph: link.graph_revision_id,
                    center: link.entity_iri,
                    kbReturn: route.fullPath,
                  },
                }"
                >{{ t('kb.exploreGraph') }}</RouterLink
              >
              <span
                >{{ t('kb.manualReference') }} ·
                {{ t('kb.graphRevision', { n: link.graph_revision_id }) }}</span
              >
              <RouterLink
                class="kb-wrap"
                :to="{
                  name: 'graph-entity-detail',
                  params: { id: link.entity_iri },
                  query: { graph: link.graph_revision_id, kbReturn: route.fullPath },
                }"
                >{{ link.entity_iri }}</RouterLink
              >
              <RouterLink
                v-if="link.fact_id"
                class="kb-wrap"
                :to="{
                  name: 'graph-evidence',
                  query: {
                    graph: link.graph_revision_id,
                    subject: link.entity_iri,
                    predicate: link.predicate,
                    object: link.object_iri,
                    fact_id: link.fact_id,
                    kbReturn: route.fullPath,
                  },
                }"
                >{{ t('kb.fact', { n: link.fact_id }) }} · {{ link.predicate }} ·
                {{ link.object_iri }}</RouterLink
              >
            </div>
            <GraphLinkForm
              :key="`${kbId}:${chunk}`"
              ref="linkForm"
              :kb-id="kbId"
              :evidence="current"
              :base-archived="baseArchived"
              :disabled="loading || !!error || !data"
              @saved="reload"
            />
            <p v-if="!canWrite" class="kb-muted">{{ t('kb.linkReadonly') }}</p>
          </div>
        </UiSpin>
      </div>
    </UiDrawerContent>
  </UiDrawer>
</template>
