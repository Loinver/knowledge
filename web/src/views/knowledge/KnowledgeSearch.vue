<script setup lang="ts">
import './knowledge.css'

import {
  NAlert,
  NButton,
  NCollapse,
  NCollapseItem,
  NEmpty,
  NFormItem,
  NInput,
  NInputNumber,
  NPagination,
  NSelect,
  NSpin,
} from 'naive-ui'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { knowledgeApi, type KnowledgeSearchRequest } from '@/api/knowledge'
import PageHeader from '@/components/PageHeader.vue'

import EvidenceDrawer from './components/EvidenceDrawer.vue'
import SearchHit from './components/SearchHit.vue'
import { positivePage, useKnowledgeRead } from './composables/useKnowledge'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))
const base = useKnowledgeRead((signal) => knowledgeApi.get(id.value, signal))
const capabilities = useKnowledgeRead(knowledgeApi.capabilities)
const q = ref('')
const mode = ref<NonNullable<KnowledgeSearchRequest['mode']>>('KEYWORD')
const kind = ref('search')
const threshold = ref<number | null>(0.25)
const requestKey = computed(() =>
  JSON.stringify([
    id.value,
    typeof route.query.q === 'string' ? route.query.q : '',
    route.query.mode === 'SEMANTIC' || route.query.mode === 'HYBRID' ? route.query.mode : 'KEYWORD',
    route.query.kind === 'answer' ? 'answer' : 'search',
    typeof route.query.min_similarity === 'string' &&
    Number.isFinite(Number(route.query.min_similarity))
      ? Math.max(-1, Math.min(1, Number(route.query.min_similarity)))
      : 0.25,
  ]),
)
watch(
  requestKey,
  (value) => {
    const [, query, searchMode, searchKind, similarity] = JSON.parse(value)
    q.value = query
    mode.value = searchMode
    kind.value = searchKind
    threshold.value = similarity
  },
  { immediate: true },
)
type SearchData = {
  retrieval: Awaited<ReturnType<typeof knowledgeApi.search>>
  answer: Awaited<ReturnType<typeof knowledgeApi.answer>> | null
}
const { data, error, loading, cancelled, cancel, reload } = useKnowledgeRead<SearchData>(
  (signal) => {
    const [kbId, query, searchMode, searchKind, similarity] = JSON.parse(requestKey.value)
    if (!query.trim()) return Promise.resolve(null)
    const payload: KnowledgeSearchRequest = {
      q: query,
      mode: searchMode,
      min_similarity: similarity,
      top_k: 50,
    }
    return searchKind === 'answer'
      ? knowledgeApi
          .answer(kbId, payload, signal)
          .then((answer) => ({ retrieval: answer.retrieval, answer }))
      : knowledgeApi
          .search(kbId, payload, signal)
          .then((retrieval) => ({ retrieval, answer: null }))
  },
)
const modes = computed(() =>
  ['KEYWORD', 'SEMANTIC', 'HYBRID'].map((value) => ({
    value,
    label: t(`kb.mode.${value}`),
    disabled: value !== 'KEYWORD' && !capabilities.data.value?.embedding_configured,
  })),
)
const kinds = computed(() => [
  { value: 'search', label: t('kb.search') },
  { value: 'answer', label: t('kb.answer'), disabled: !capabilities.data.value?.chat_configured },
])
const page = computed(() =>
  Math.min(
    positivePage(route.query.page),
    Math.max(1, Math.ceil((data.value?.retrieval.items.length ?? 0) / 10)),
  ),
)
const hits = computed(() =>
  (data.value?.retrieval.items ?? []).slice((page.value - 1) * 10, page.value * 10),
)
const canSubmit = computed(
  () =>
    q.value.trim().length > 0 &&
    !!base.data.value &&
    !base.error.value &&
    !base.data.value.archived &&
    !!capabilities.data.value &&
    (mode.value === 'KEYWORD' || capabilities.data.value.embedding_configured) &&
    (kind.value !== 'answer' || capabilities.data.value.chat_configured),
)
function submit() {
  if (!canSubmit.value) return
  const query = {
    q: q.value.trim(),
    mode: mode.value,
    kind: kind.value,
    min_similarity: threshold.value ?? 0.25,
    page: 1,
  }
  const next = router.resolve({ name: 'knowledge-base-search', params: { id: id.value }, query })
  if (next.fullPath === route.fullPath) reload()
  else void router.push(next)
}
let evidenceTrigger: HTMLElement | null = null
function openEvidence(chunk: string, event: MouseEvent) {
  evidenceTrigger = event.currentTarget as HTMLElement
  void router.push({ query: { ...route.query, evidence: chunk } })
}
function restoreFocus() {
  if (evidenceTrigger?.isConnected) evidenceTrigger.focus()
}
</script>

<template>
  <section class="kb-page">
    <PageHeader :title="t('kb.searchTitle')" :description="base.data.value?.name">
      <template #actions
        ><RouterLink :to="{ name: 'knowledge-base-detail', params: { id } }">{{
          t('kb.backToDocuments')
        }}</RouterLink></template
      >
    </PageHeader>
    <NAlert v-if="base.error.value" type="error"
      >{{ base.error.value }} <NButton @click="base.reload">{{ t('kb.retry') }}</NButton></NAlert
    >
    <NAlert v-if="base.data.value?.archived" type="warning">{{ t('kb.archivedNotice') }}</NAlert>
    <NAlert v-if="capabilities.error.value" type="error"
      >{{ capabilities.error.value }}
      <NButton @click="capabilities.reload">{{ t('kb.retry') }}</NButton></NAlert
    >
    <section class="kb-panel kb-stack">
      <form class="kb-toolbar" @submit.prevent="submit">
        <NInput
          v-model:value="q"
          :maxlength="2000"
          clearable
          :placeholder="t('kb.queryPlaceholder')"
          :input-props="{ 'aria-label': t('kb.queryPlaceholder') }"
        />
        <NSelect v-model:value="mode" :options="modes" :aria-label="t('kb.searchMode')" />
        <NSelect v-model:value="kind" :options="kinds" :aria-label="t('kb.resultKind')" />
        <NButton attr-type="submit" type="primary" :disabled="!canSubmit" :loading="loading">{{
          t('kb.runSearch')
        }}</NButton>
        <NButton v-if="loading" @click="cancel">{{ t('kb.cancelSearch') }}</NButton>
      </form>
      <div v-if="capabilities.data.value" class="kb-stack">
        <p v-if="!capabilities.data.value.embedding_configured" class="kb-muted">
          {{ t('kb.semanticUnavailable') }}
        </p>
        <p v-if="!capabilities.data.value.chat_configured" class="kb-muted">
          {{ t('kb.answerUnavailable') }}
        </p>
      </div>
      <NCollapse
        ><NCollapseItem :title="t('kb.advanced')" name="threshold">
          <NFormItem :label="t('kb.minSimilarity')" :label-props="{ for: 'kb-threshold' }"
            ><NInputNumber
              v-model:value="threshold"
              :min="-1"
              :max="1"
              :step="0.05"
              :input-props="{ id: 'kb-threshold' }"
          /></NFormItem>
          <p class="kb-muted">{{ t('kb.scoreExplanation') }}</p>
        </NCollapseItem></NCollapse
      >
    </section>
    <NAlert v-if="error" type="error" role="alert"
      >{{ error }} <NButton @click="reload">{{ t('kb.retry') }}</NButton></NAlert
    >
    <NSpin :show="loading">
      <p v-if="loading" role="status">{{ t('kb.searching') }}</p>
      <div v-else-if="data" class="kb-stack">
        <div class="kb-meta" role="status">
          <span>{{
            t('kb.searchSummary', {
              matches: data.retrieval.total_matches,
              shown: data.retrieval.items.length,
              documents: data.retrieval.coverage.searchable_documents,
              total: data.retrieval.coverage.total_documents,
            })
          }}</span
          ><span>{{ data.retrieval.ranking_version }}</span>
        </div>
        <NAlert
          v-if="
            data.retrieval.coverage.failed_documents ||
            data.retrieval.coverage.processing_documents ||
            data.retrieval.coverage.partial_documents ||
            data.retrieval.coverage.excluded_semantic_chunks
          "
          type="warning"
          >{{
            t('kb.coverageWarning', {
              failed: data.retrieval.coverage.failed_documents,
              processing: data.retrieval.coverage.processing_documents,
              partial: data.retrieval.coverage.partial_documents,
              excluded: data.retrieval.coverage.excluded_semantic_chunks,
            })
          }}</NAlert
        >
        <section v-if="data.answer" class="kb-panel kb-stack">
          <h2>{{ t('kb.answer') }}</h2>
          <p class="kb-muted">{{ t('kb.answerExplanation') }}</p>
          <NAlert v-if="data.answer.status === 'INSUFFICIENT_EVIDENCE'" type="warning">{{
            t('kb.insufficientEvidence')
          }}</NAlert>
          <blockquote
            v-for="(citation, index) in data.answer.citations"
            :key="`${citation.source.chunk_id}:${index}`"
            class="kb-quote"
          >
            <p class="kb-wrap">{{ citation.quote }}</p>
            <NButton text type="primary" @click="openEvidence(citation.source.chunk_id, $event)">{{
              t('kb.citation', { n: index + 1, name: citation.source.document_name })
            }}</NButton>
          </blockquote>
        </section>
        <NEmpty
          v-if="!data.retrieval.items.length"
          class="kb-empty"
          :description="t('kb.noResults')"
        />
        <template v-else
          ><SearchHit
            v-for="hit in hits"
            :key="hit.chunk_id"
            :hit="hit"
            @evidence="openEvidence(hit.chunk_id, $event)"
          />
          <div class="kb-pagination">
            <NPagination
              :page="page"
              :page-size="10"
              :item-count="data.retrieval.items.length"
              @update:page="router.push({ query: { ...route.query, page: $event } })"
            />
          </div>
          <p class="kb-muted">{{ t('kb.scoreExplanation') }}</p>
          <p class="kb-muted">{{ t('kb.resultLimit') }}</p></template
        >
      </div>
      <NEmpty
        v-else-if="!loading && !error"
        class="kb-empty"
        :description="t(cancelled ? 'kb.searchCancelled' : 'kb.searchPrompt')"
      />
    </NSpin>
    <EvidenceDrawer
      :kb-id="id"
      :base-archived="base.data.value?.archived ?? true"
      @closed="restoreFocus"
    />
  </section>
</template>

<style scoped>
.kb-quote {
  margin: 0;
  border-left: 3px solid var(--accent);
  padding: var(--space-2) var(--space-4);
  background: var(--bg-subtle);
}
.kb-quote :deep(.n-button__content) {
  white-space: normal;
  overflow-wrap: anywhere;
}
</style>
