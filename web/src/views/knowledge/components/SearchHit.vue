<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { KnowledgeHit } from '@/api/knowledge'
import { UiButton, UiTag } from '@/components/ui'

import { useHitLocation } from '../composables/useKnowledge'
const props = defineProps<{ hit: KnowledgeHit }>()
defineEmits<{ evidence: [event: MouseEvent] }>()
const { t, locale } = useI18n()
const location = useHitLocation(() => props.hit)
const score = (value: number) =>
  new Intl.NumberFormat(locale.value, { maximumFractionDigits: 4 }).format(value)
</script>

<template>
  <article class="kb-panel kb-stack" data-testid="kb-search-hit">
    <div class="kb-hit-heading">
      <h2 class="kb-wrap" :title="hit.document_name">{{ hit.document_name }}</h2>
      <UiButton @click="$emit('evidence', $event)">{{ t('kb.viewEvidence') }}</UiButton>
    </div>
    <div class="kb-meta">
      <span class="kb-wrap">{{ hit.kb_name }}</span
      ><span class="kb-wrap">{{ location }}</span
      ><span>{{ t('kb.generation', { n: hit.generation }) }}</span>
    </div>
    <p class="kb-hit-text kb-wrap">{{ hit.text }}</p>
    <footer class="kb-hit-footer">
      <div class="kb-meta">
        <span>{{ t('kb.rankScore', { score: score(hit.score) }) }}</span>
        <span v-if="hit.keyword_score != null">{{
          t('kb.keywordScore', { score: score(hit.keyword_score) })
        }}</span>
        <span v-if="hit.similarity != null">{{
          t('kb.cosineScore', { score: score(hit.similarity) })
        }}</span>
      </div>
      <div class="kb-hit-identity">
        <code>{{ hit.chunk_id }}</code>
        <UiTag v-if="hit.graph_links?.length" size="small">{{
          t('kb.manualLinks', { n: hit.graph_links.length })
        }}</UiTag>
      </div>
    </footer>
  </article>
</template>

<style scoped>
.kb-hit-heading {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
  align-items: flex-start;
}
.kb-hit-heading h2 {
  margin: 0;
  font-size: 15px;
  min-width: 0;
}
.kb-hit-text {
  margin: 0;
  line-height: 1.8;
  padding: 12px 0;
  color: var(--foreground-secondary);
}
.kb-hit-footer {
  display: grid;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--border-muted);
}
.kb-hit-identity code {
  overflow-wrap: anywhere;
}
.kb-hit-identity {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  color: var(--text-secondary);
  font-size: 11px;
}
</style>
