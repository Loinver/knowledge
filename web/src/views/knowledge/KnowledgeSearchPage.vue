<script setup lang="ts">
import './knowledge.css'

import { computed, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { knowledgeApi, type KnowledgeSearchRequest } from '@/api/knowledge'
import PageHeader from '@/components/PageHeader.vue'
import { FormField, SearchPanel } from '@/components/ui'
import {
  UiAlert,
  UiButton,
  UiEmpty,
  UiInputNumber,
  UiPagination,
  UiSelect,
  UiSpin,
} from '@/components/ui'
import { usePageIdentity } from '@/layout/navigation/usePageIdentity'

import EvidenceDrawer from './components/EvidenceDrawer.vue'
import SearchHit from './components/SearchHit.vue'
import { positivePage, useKnowledgeRead } from './composables/useKnowledge'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))
const base = useKnowledgeRead((signal) => knowledgeApi.get(id.value, signal))
usePageIdentity(() => (base.data.value?.id === id.value ? base.data.value.name : ''))
const capabilities = useKnowledgeRead(knowledgeApi.capabilities)
const q = ref('')
const mode = ref<NonNullable<KnowledgeSearchRequest['mode']>>('KEYWORD')
const kind = ref('search')
const threshold = ref<number | null>(0.25)
const expanded = ref(false)
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
    if (!query.trim() || query.trim().length > 2000) return Promise.resolve(null)
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
const snapshot = shallowRef<{ key: string; value: SearchData } | null>(null)
watch(data, (value) => {
  if (value) snapshot.value = { key: requestKey.value, value }
})
const current = computed(
  () => data.value ?? (snapshot.value?.key === requestKey.value ? snapshot.value.value : null),
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
    Math.max(1, Math.ceil((current.value?.retrieval.items.length ?? 0) / 10)),
  ),
)
const hits = computed(() =>
  (current.value?.retrieval.items ?? []).slice((page.value - 1) * 10, page.value * 10),
)
const canSubmit = computed(
  () =>
    q.value.trim().length > 0 &&
    q.value.trim().length <= 2000 &&
    (threshold.value == null ||
      (Number.isFinite(threshold.value) && threshold.value >= -1 && threshold.value <= 1)) &&
    !!base.data.value &&
    base.data.value.id === id.value &&
    !base.error.value &&
    !base.data.value.archived &&
    !!capabilities.data.value &&
    (mode.value === 'KEYWORD' || capabilities.data.value.embedding_configured) &&
    (kind.value !== 'answer' || capabilities.data.value.chat_configured),
)
function submit() {
  if (!canSubmit.value) return
  const nextKey = JSON.stringify([
    id.value,
    q.value.trim(),
    mode.value,
    kind.value,
    threshold.value ?? 0.25,
  ])
  if (loading.value && nextKey === requestKey.value) return
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
function clearSearch(reset = false) {
  cancel()
  snapshot.value = null
  q.value = ''
  if (reset) {
    mode.value = 'KEYWORD'
    kind.value = 'search'
    threshold.value = 0.25
  }
  void router.push({
    query: {
      ...route.query,
      q: undefined,
      page: undefined,
      evidence: undefined,
      ...(reset ? { mode: undefined, kind: undefined, min_similarity: undefined } : {}),
    },
  })
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
  <section class="kb-page kb-search-page">
    <PageHeader
      :title="t('kb.searchTitle')"
      :description="base.data.value?.name"
      :eyebrow="t('kb.evidence')"
      :identity="
        base.data.value ? `${base.data.value.id} · r${base.data.value.index_revision}` : undefined
      "
    >
      <template #actions
        ><RouterLink :to="{ name: 'knowledge-base-detail', params: { id } }">{{
          t('kb.backToDocuments')
        }}</RouterLink></template
      >
    </PageHeader>
    <UiAlert v-if="base.error.value" type="error"
      >{{ base.error.value }} <UiButton @click="base.reload">{{ t('kb.retry') }}</UiButton></UiAlert
    >
    <UiAlert v-if="base.data.value?.archived" type="warning">{{ t('kb.archivedNotice') }}</UiAlert>
    <UiAlert v-if="capabilities.error.value" type="error"
      >{{ capabilities.error.value }}
      <UiButton @click="capabilities.reload">{{ t('kb.retry') }}</UiButton></UiAlert
    >
    <section class="kb-panel kb-stack kb-query-panel">
      <header class="kb-panel-heading">
        <h2>{{ t('kb.searchTitle') }}</h2>
        <span class="kb-muted">{{ t('kb.evidence') }}</span>
      </header>
      <SearchPanel
        v-model:query="q"
        v-model:expanded="expanded"
        :label="t('kb.queryPlaceholder')"
        :placeholder="t('kb.queryPlaceholder')"
        :loading="loading"
        @submit="submit"
        @clear="clearSearch()"
        @reset="clearSearch(true)"
      >
        <template #filters>
          <UiSelect
            v-model:value="mode"
            class="w-full sm:w-40"
            :options="modes"
            :aria-label="t('kb.searchMode')"
          />
          <UiSelect
            v-model:value="kind"
            class="w-full sm:w-36"
            :options="kinds"
            :aria-label="t('kb.resultKind')"
          />
        </template>
        <template #actions="{ clear, reset }">
          <UiButton attr-type="submit" type="primary" :disabled="!canSubmit" :loading="loading">{{
            t('kb.runSearch')
          }}</UiButton>
          <UiButton v-if="loading" @click="cancel">{{ t('kb.cancelSearch') }}</UiButton>
          <UiButton :disabled="!q" @click="clear">{{ t('ds.search.clear') }}</UiButton>
          <UiButton @click="reset">{{ t('ds.search.reset') }}</UiButton>
        </template>
        <template #advanced>
          <FormField :label="t('kb.minSimilarity')" :help="t('kb.scoreExplanation')">
            <UiInputNumber v-model:value="threshold" :min="-1" :max="1" :step="0.05" />
          </FormField>
        </template>
      </SearchPanel>
      <UiAlert v-if="q.trim().length > 2000" type="warning">{{
        t('ds.form.maxLength', { max: 2000 })
      }}</UiAlert>
      <div v-if="capabilities.data.value" class="kb-stack">
        <p v-if="!capabilities.data.value.embedding_configured" class="kb-muted">
          {{ t('kb.semanticUnavailable') }}
        </p>
        <p v-if="!capabilities.data.value.chat_configured" class="kb-muted">
          {{ t('kb.answerUnavailable') }}
        </p>
      </div>
    </section>
    <UiAlert v-if="error" type="error" role="alert"
      >{{ error }} <UiButton @click="reload">{{ t('kb.retry') }}</UiButton></UiAlert
    >
    <UiSpin :show="loading">
      <p v-if="loading" role="status">{{ t('kb.searching') }}</p>
      <div v-if="current" class="kb-search-workspace">
        <main class="kb-stack kb-results">
          <div class="kb-meta" role="status">
            <span>{{
              t('kb.searchSummary', {
                matches: current.retrieval.total_matches,
                shown: current.retrieval.items.length,
                documents: current.retrieval.coverage.searchable_documents,
                total: current.retrieval.coverage.total_documents,
              })
            }}</span
            ><span>{{ current.retrieval.ranking_version }}</span>
          </div>
          <UiAlert
            v-if="
              current.retrieval.coverage.failed_documents ||
              current.retrieval.coverage.processing_documents ||
              current.retrieval.coverage.partial_documents ||
              current.retrieval.coverage.excluded_semantic_chunks
            "
            type="warning"
            >{{
              t('kb.coverageWarning', {
                failed: current.retrieval.coverage.failed_documents,
                processing: current.retrieval.coverage.processing_documents,
                partial: current.retrieval.coverage.partial_documents,
                excluded: current.retrieval.coverage.excluded_semantic_chunks,
              })
            }}</UiAlert
          >

          <UiEmpty
            v-if="!current.retrieval.items.length"
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
              <UiPagination
                :page="page"
                :page-size="10"
                :item-count="current.retrieval.items.length"
                @update:page="router.push({ query: { ...route.query, page: $event } })"
              />
            </div>
          </template>
        </main>
        <aside class="kb-stack kb-retrieval-inspector" :aria-label="t('kb.coverage')">
          <section class="kb-panel kb-stack">
            <header class="kb-panel-heading">
              <h2>{{ t('kb.coverage') }}</h2>
              <code>{{ current.retrieval.ranking_version }}</code>
            </header>
            <dl class="kb-facts">
              <dt>{{ t('kb.documents') }}</dt>
              <dd>{{ current.retrieval.coverage.total_documents }}</dd>
              <dt>{{ t('kb.searchable') }}</dt>
              <dd>{{ current.retrieval.coverage.searchable_documents }}</dd>
              <dt>{{ t('kb.processing') }}</dt>
              <dd>{{ current.retrieval.coverage.processing_documents }}</dd>
              <dt>{{ t('kb.failedPartial') }}</dt>
              <dd>
                {{ current.retrieval.coverage.failed_documents }} /
                {{ current.retrieval.coverage.partial_documents }}
              </dd>
            </dl>
            <p class="kb-muted">{{ t('kb.resultLimit') }}</p>
            <details class="kb-score-help">
              <summary>{{ t('kb.rankScore', { score: '' }) }}</summary>
              <p class="kb-muted">{{ t('kb.scoreExplanation') }}</p>
            </details>
          </section>
          <section v-if="current.answer" class="kb-panel kb-stack">
            <h2>{{ t('kb.answer') }}</h2>
            <p class="kb-muted">{{ t('kb.answerExplanation') }}</p>
            <UiAlert v-if="current.answer.status === 'INSUFFICIENT_EVIDENCE'" type="warning">{{
              t('kb.insufficientEvidence')
            }}</UiAlert>
            <blockquote
              v-for="(citation, index) in current.answer.citations"
              :key="`${citation.source.chunk_id}:${index}`"
              class="kb-quote"
            >
              <p class="kb-wrap">{{ citation.quote }}</p>
              <UiButton
                text
                type="primary"
                @click="openEvidence(citation.source.chunk_id, $event)"
                >{{
                  t('kb.citation', { n: index + 1, name: citation.source.document_name })
                }}</UiButton
              >
            </blockquote>
          </section>
        </aside>
      </div>
      <UiEmpty
        v-else-if="!loading && !error"
        class="kb-empty"
        :description="t(cancelled ? 'kb.searchCancelled' : 'kb.searchPrompt')"
      />
    </UiSpin>
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
.kb-quote :deep(.ui-button) {
  white-space: normal;
  overflow-wrap: anywhere;
}
</style>
