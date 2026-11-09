<script setup lang="ts">
import { NAlert, NButton, NDrawer, NDrawerContent, NSpin, NTag } from 'naive-ui'
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteUpdate, RouterLink, useRoute, useRouter } from 'vue-router'

import { knowledgeApi } from '@/api/knowledge'
import { useAuthStore } from '@/stores/auth'

import { evidenceSegments, useKnowledgeAction, useKnowledgeRead } from '../composables/useKnowledge'
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
const { busy, error: actionError, run } = useKnowledgeAction(() => `${props.kbId}:${chunk.value}`)
const canWrite = computed(
  () =>
    ['ADMIN', 'EDITOR'].includes(auth.user?.role ?? '') &&
    !props.baseArchived &&
    !data.value?.archived &&
    !data.value?.historical,
)
const segments = computed(() =>
  data.value
    ? evidenceSegments(
        data.value.normalized_text,
        data.value.hit.location.start_offset,
        data.value.hit.location.end_offset,
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
  if (!hit) return
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
  <NDrawer
    :show="!!chunk"
    :width="760"
    @update:show="!$event && close()"
    @after-leave="$emit('closed')"
  >
    <NDrawerContent :title="t('kb.evidence')" closable>
      <div class="kb-stack">
        <NAlert v-if="error" type="error" role="alert"
          >{{ error }} <NButton @click="reload">{{ t('kb.retry') }}</NButton></NAlert
        >
        <NAlert v-if="actionError" type="error" role="alert">{{ actionError }}</NAlert>
        <NSpin :show="loading">
          <p v-if="loading" role="status">{{ t('kb.loading') }}</p>
          <div v-if="data" class="kb-stack">
            <h2 class="kb-wrap">{{ data.hit.document_name }}</h2>
            <div class="kb-meta">
              <span>{{ data.hit.kb_name }}</span
              ><span>{{ t('kb.generation', { n: data.hit.generation }) }}</span
              ><span>{{
                t('kb.lines', {
                  start: data.hit.location.start_line,
                  end: data.hit.location.end_line,
                })
              }}</span
              ><span v-if="data.hit.location.paragraph_number != null">{{
                t('kb.paragraph', { n: data.hit.location.paragraph_number })
              }}</span
              ><span v-if="data.hit.location.row_number != null">{{
                t('kb.row', { n: data.hit.location.row_number })
              }}</span
              ><span>{{ data.hit.section }}</span>
            </div>
            <NAlert v-if="data.historical || data.archived" type="warning">{{
              t(data.archived ? 'kb.archivedEvidence' : 'kb.historicalEvidence')
            }}</NAlert>
            <div class="kb-actions">
              <NButton :loading="busy" @click="download">{{ t('kb.original') }}</NButton
              ><NTag size="small">{{ data.parser_version }} · {{ data.chunker_version }}</NTag>
            </div>
            <p class="kb-muted">{{ t('kb.normalizedSource') }}</p>
            <div class="kb-source" tabindex="0" :aria-label="t('kb.evidence')">
              <span>{{ segments[0] }}</span
              ><mark ref="highlight" data-testid="kb-evidence-highlight">{{ segments[1] }}</mark
              ><span>{{ segments[2] }}</span>
            </div>
            <h2>{{ t('kb.manualReference') }}</h2>
            <p class="kb-muted">{{ t('kb.manualExplanation') }}</p>
            <div v-for="link in data.hit.graph_links" :key="link.id" class="kb-panel kb-stack">
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
              v-if="canWrite"
              :key="`${kbId}:${chunk}`"
              ref="linkForm"
              :kb-id="kbId"
              :evidence="data"
              @saved="reload"
            />
            <p v-else class="kb-muted">{{ t('kb.linkReadonly') }}</p>
          </div>
        </NSpin>
      </div>
    </NDrawerContent>
  </NDrawer>
</template>
