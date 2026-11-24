<script setup lang="ts">
import { onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'

import { aiApi, type SuggestionKind } from '@/api/ai'
import { UiAlert, UiButton, UiEmpty, UiList, UiListItem, UiSpace, UiTag } from '@/components/ui'
import { useApiError } from '@/composables/useApiError'

import { suggestionPayloadLines, useAiSuggestions } from './useAiSuggestions'

/**
 * AI 建议审阅面板（V-DS-05 / V-EX-07 共用）：
 * 展示 PENDING 建议的标题、解释与内容明细，人工逐条应用/忽略。
 * 建议永远不自动落库；LLM 未配置时显示如实的未配置提示。
 *
 * - ONTOLOGY_COMPLETION / MAPPING_SUGGEST：generate() 即可发起；
 * - DOCUMENT_FACTS：由父组件经 generate(text) 传入待抽取文本。
 */
const props = defineProps<{
  kind: SuggestionKind
  title: string
  targetId: number
  datasourceId?: number
  reviewOnly?: boolean
}>()
const emit = defineEmits<{ applied: [id: number] }>()
const { t } = useI18n()
const { toMessage } = useApiError()
const { items, loading, busyId, error, notice, loaded, generate, apply, discard, dispose } =
  useAiSuggestions(
    () => props,
    aiApi,
    t,
    toMessage,
    (id) => emit('applied', id),
  )
onBeforeUnmount(dispose)

function kindLabel(kind: string): string {
  switch (kind) {
    case 'ONTOLOGY_COMPLETION':
      return t('ai.kinds.completion')
    case 'MAPPING_SUGGEST':
      return t('ai.kinds.mapping')
    case 'DOCUMENT_FACTS':
      return t('ai.kinds.facts')
    default:
      return t('ai.kinds.unknown')
  }
}

defineExpose({ generate })
</script>

<template>
  <div class="ai-panel">
    <UiSpace align="center" vertical>
      <UiSpace align="center">
        <UiButton type="primary" :loading="loading" :disabled="busyId !== null" @click="generate()">
          {{ t('ai.generate') }}
        </UiButton>
        <span class="hint">{{ t('ai.hint') }}</span>
      </UiSpace>
      <UiAlert v-if="error" type="error">{{ error }}</UiAlert>
      <UiAlert v-if="notice" type="success">{{ notice }}</UiAlert>
    </UiSpace>
    <UiEmpty v-if="loaded && !items.length" :description="t('ai.empty')" size="small" />
    <UiList v-if="items.length" bordered>
      <UiListItem v-for="item in items" :key="item.id">
        <div class="item">
          <div class="item-head">
            <strong>{{ item.title }}</strong>
            <UiTag size="small" round>{{ kindLabel(item.kind) }}</UiTag>
          </div>
          <p v-if="item.explanation" class="explanation">{{ item.explanation }}</p>
          <ul class="payload">
            <li v-for="line in suggestionPayloadLines(item)" :key="line">{{ line }}</li>
          </ul>
          <UiSpace v-if="!reviewOnly">
            <UiButton
              size="tiny"
              type="primary"
              :loading="busyId === item.id"
              :disabled="loading || busyId !== null"
              @click="apply(item.id)"
            >
              {{ t('ai.apply') }}
            </UiButton>
            <UiButton
              size="tiny"
              :loading="busyId === item.id"
              :disabled="loading || busyId !== null"
              @click="discard(item.id)"
            >
              {{ t('ai.discard') }}
            </UiButton>
          </UiSpace>
        </div>
      </UiListItem>
    </UiList>
  </div>
</template>

<style scoped>
.ai-panel {
  display: grid;
  gap: var(--space-3);
}
.hint {
  color: var(--foreground-secondary);
  font-size: var(--font-caption);
}
.item {
  display: grid;
  gap: 6px;
}
.item-head {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}
.explanation {
  margin: 0;
  color: var(--foreground-secondary);
  font-size: var(--font-caption);
}
.payload {
  margin: 0;
  padding-left: 18px;
  font-size: var(--font-caption);
  word-break: break-all;
}
</style>
