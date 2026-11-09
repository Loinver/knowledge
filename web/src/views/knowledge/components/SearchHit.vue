<script setup lang="ts">
import { NButton, NTag } from 'naive-ui'
import { useI18n } from 'vue-i18n'

import type { KnowledgeHit } from '@/api/knowledge'

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
      <NButton @click="$emit('evidence', $event)">{{ t('kb.viewEvidence') }}</NButton>
    </div>
    <div class="kb-meta">
      <span class="kb-wrap">{{ hit.kb_name }}</span
      ><span class="kb-wrap">{{ location }}</span
      ><span>{{ t('kb.generation', { n: hit.generation }) }}</span>
    </div>
    <p class="kb-hit-text kb-wrap">{{ hit.text }}</p>
    <div class="kb-meta">
      <span>{{ t('kb.rankScore', { score: score(hit.score) }) }}</span>
      <span v-if="hit.keyword_score != null">{{
        t('kb.keywordScore', { score: score(hit.keyword_score) })
      }}</span>
      <span v-if="hit.similarity != null">{{
        t('kb.cosineScore', { score: score(hit.similarity) })
      }}</span>
      <NTag v-if="hit.graph_links?.length" size="small" :bordered="false">{{
        t('kb.manualLinks', { n: hit.graph_links.length })
      }}</NTag>
    </div>
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
  font-size: var(--font-h2);
  min-width: 0;
}
.kb-hit-text {
  margin: 0;
  line-height: 1.8;
}
</style>
