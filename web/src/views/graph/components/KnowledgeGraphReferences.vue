<script setup lang="ts">
import { NAlert, NButton, NDrawer, NDrawerContent } from 'naive-ui'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { knowledgeApi, type KnowledgeGraphEvidence } from '@/api/knowledge'
import { useAsyncData } from '@/composables/useAsyncData'

const props = defineProps<{ graphId: number; entityIri: string; factId?: number }>()
const { t } = useI18n()
const selected = ref<KnowledgeGraphEvidence | null>(null)
let returnFocus: HTMLElement | null = null
const open = computed({
  get: () => !!selected.value,
  set: (value) => {
    if (!value) selected.value = null
  },
})
const evidence = useAsyncData((signal) =>
  selected.value
    ? knowledgeApi.evidence(selected.value.kb_id, selected.value.chunk_id, signal)
    : Promise.resolve(null),
)
const context = computed(() => {
  const value = evidence.data.value
  if (!value) return ['', '', '']
  const source = Array.from(value.normalized_text)
  const { start_offset: start, end_offset: end } = value.hit.location
  return [
    source.slice(Math.max(0, start - 800), start).join(''),
    source.slice(start, end).join(''),
    source.slice(end, end + 800).join(''),
  ]
})
watch(
  () => `${props.graphId}:${props.entityIri}:${props.factId}`,
  () => {
    selected.value = null
  },
)
function inspect(hit: KnowledgeGraphEvidence, event: MouseEvent) {
  returnFocus = event.currentTarget as HTMLElement
  selected.value = hit
}
const { data, loading, error, reload } = useAsyncData((signal) =>
  knowledgeApi.graphEvidence(
    {
      graph_revision_id: props.graphId,
      entity_iri: props.entityIri,
      fact_id: props.factId,
    },
    signal,
  ),
)
</script>

<template>
  <section class="document-references" :aria-label="t('kb.manualReference')">
    <h3>{{ t('kb.manualReference') }}</h3>
    <p class="reference-note">{{ t('kb.manualExplanation') }}</p>
    <p v-if="loading" role="status">{{ t('common.loading') }}</p>
    <NAlert v-else-if="error" type="warning">
      {{ error }} <NButton size="small" @click="reload">{{ t('ui.retry') }}</NButton>
    </NAlert>
    <p v-else-if="!data?.length">{{ t('kb.noGraphReferences') }}</p>
    <ul v-else>
      <li v-for="hit in data" :key="hit.chunk_id">
        <strong :title="hit.document_name">{{ hit.document_name }}</strong>
        <div class="reference-metadata">
          <span>{{ hit.kb_name }}</span>
          <span>{{ t('kb.generation', { n: hit.generation }) }}</span>
          <span>{{
            t('kb.lines', { start: hit.location.start_line, end: hit.location.end_line })
          }}</span>
        </div>
        <NAlert v-if="hit.historical" type="info">{{ t('kb.historicalEvidence') }}</NAlert>
        <p>{{ hit.text }}</p>
        <NButton size="small" @click="inspect(hit, $event)">{{ t('kb.viewEvidence') }}</NButton>
      </li>
    </ul>
    <p v-if="data?.length === 50" class="reference-note">{{ t('kb.referenceLimit') }}</p>
  </section>
  <NDrawer
    v-model:show="open"
    :width="640"
    style="max-width: 94vw"
    @after-leave="returnFocus?.focus({ preventScroll: true })"
  >
    <NDrawerContent :title="t('kb.evidence')" closable>
      <p v-if="evidence.loading.value" role="status">{{ t('common.loading') }}</p>
      <NAlert v-else-if="evidence.error.value" type="error"
        >{{ evidence.error.value }}
        <NButton @click="evidence.reload">{{ t('ui.retry') }}</NButton>
      </NAlert>
      <template v-else-if="evidence.data.value">
        <h3>{{ evidence.data.value.hit.document_name }}</h3>
        <div class="reference-metadata">
          <span>{{ evidence.data.value.hit.kb_name }}</span>
          <span>{{ t('kb.generation', { n: evidence.data.value.hit.generation }) }}</span>
          <span>{{
            t('kb.lines', {
              start: evidence.data.value.hit.location.start_line,
              end: evidence.data.value.hit.location.end_line,
            })
          }}</span>
          <span v-if="evidence.data.value.hit.location.paragraph_number != null">{{
            t('kb.paragraph', { n: evidence.data.value.hit.location.paragraph_number })
          }}</span>
          <span v-if="evidence.data.value.hit.location.row_number != null">{{
            t('kb.row', { n: evidence.data.value.hit.location.row_number })
          }}</span>
          <span v-if="evidence.data.value.hit.section">{{ evidence.data.value.hit.section }}</span>
        </div>
        <NAlert v-if="evidence.data.value.archived" type="warning">{{
          t('kb.archivedEvidence')
        }}</NAlert>
        <NAlert v-if="evidence.data.value.historical" type="info">{{
          t('kb.historicalEvidence')
        }}</NAlert>
        <p>{{ t('kb.excerptContext') }}</p>
        <pre
          class="source-context"
        ><span>{{ context[0] }}</span><mark>{{ context[1] }}</mark><span>{{ context[2] }}</span></pre>
        <RouterLink
          :to="{
            name: 'knowledge-base-search',
            params: { id: selected!.kb_id },
            query: { evidence: selected!.chunk_id },
          }"
          target="_blank"
          rel="noopener"
          >{{ t('kb.viewEvidence') }}</RouterLink
        >
      </template>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>
.document-references {
  margin-top: var(--space-5, 20px);
  border-top: 1px solid var(--border);
  padding-top: 12px;
}
.document-references h3 {
  font-size: 14px;
  margin: 0 0 8px;
}
.reference-note {
  color: var(--text-tertiary);
  font-size: 12px;
  line-height: 1.6;
}
.reference-metadata {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  margin: 8px 0;
  color: var(--text-secondary);
  font-size: 12px;
}
ul {
  list-style: none;
  padding: 0;
  margin: 12px 0;
}
li {
  padding: 10px 0;
  border-top: 1px solid var(--border);
  overflow-wrap: anywhere;
}
li p {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.6;
}
strong {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.source-context {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.8;
  font: inherit;
  padding: 16px;
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}
.source-context mark {
  background: var(--accent-soft);
  color: var(--text);
}
</style>
