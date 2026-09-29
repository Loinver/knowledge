<script setup lang="ts">
import { NAlert, NButton, NEmpty, NList, NListItem, NSpace, NTag } from 'naive-ui'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { aiApi, type AiSuggestion, type SuggestionKind, suggestionPayloadLines } from '@/api/ai'
import { useApiError } from '@/composables/useApiError'

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
const items = ref<AiSuggestion[]>([])
const loading = ref(false)
const busyId = ref<number | null>(null)
const error = ref('')
const notice = ref('')
const loaded = ref(false)

async function generate(text?: string) {
  loading.value = true
  error.value = ''
  notice.value = ''
  try {
    if (props.kind === 'ONTOLOGY_COMPLETION') {
      items.value = await aiApi.suggestCompletion(props.targetId)
    } else if (props.kind === 'MAPPING_SUGGEST') {
      if (!props.datasourceId) throw new Error(t('ai.datasourceRequired'))
      items.value = await aiApi.suggestMapping(props.targetId, props.datasourceId)
    } else {
      items.value = await aiApi.extractDocument(props.targetId, text ?? '')
    }
    loaded.value = true
  } catch (cause) {
    error.value = toMessage(cause)
  } finally {
    loading.value = false
  }
}

async function apply(id: number) {
  busyId.value = id
  error.value = ''
  try {
    await aiApi.apply(id)
    items.value = items.value.filter((item) => item.id !== id)
    notice.value = t('ai.applied')
    emit('applied', id)
  } catch (cause) {
    error.value = toMessage(cause)
  } finally {
    busyId.value = null
  }
}

async function discard(id: number) {
  busyId.value = id
  error.value = ''
  try {
    await aiApi.discard(id)
    items.value = items.value.filter((item) => item.id !== id)
  } catch (cause) {
    error.value = toMessage(cause)
  } finally {
    busyId.value = null
  }
}

defineExpose({ generate })
</script>

<template>
  <div class="ai-panel">
    <NSpace align="center" vertical>
      <NSpace align="center">
        <NButton type="primary" :loading="loading" @click="generate()">
          {{ t('ai.generate') }}
        </NButton>
        <span class="hint">{{ t('ai.hint') }}</span>
      </NSpace>
      <NAlert v-if="error" type="error">{{ error }}</NAlert>
      <NAlert v-if="notice" type="success">{{ notice }}</NAlert>
    </NSpace>
    <NEmpty v-if="loaded && !items.length" :description="t('ai.empty')" size="small" />
    <NList v-if="items.length" bordered>
      <NListItem v-for="item in items" :key="item.id">
        <div class="item">
          <div class="item-head">
            <strong>{{ item.title }}</strong>
            <NTag size="small" round>{{ item.kind }}</NTag>
          </div>
          <p v-if="item.explanation" class="explanation">{{ item.explanation }}</p>
          <ul class="payload">
            <li v-for="line in suggestionPayloadLines(item)" :key="line">{{ line }}</li>
          </ul>
          <NSpace v-if="!reviewOnly">
            <NButton
              size="tiny"
              type="primary"
              :loading="busyId === item.id"
              @click="apply(item.id)"
            >
              {{ t('ai.apply') }}
            </NButton>
            <NButton size="tiny" :loading="busyId === item.id" @click="discard(item.id)">
              {{ t('ai.discard') }}
            </NButton>
          </NSpace>
        </div>
      </NListItem>
    </NList>
  </div>
</template>

<style scoped>
.ai-panel {
  display: grid;
  gap: 12px;
}
.hint {
  color: var(--text-secondary);
  font-size: var(--font-caption);
}
.item {
  display: grid;
  gap: 6px;
}
.item-head {
  display: flex;
  gap: 8px;
  align-items: center;
}
.explanation {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-caption);
}
.payload {
  margin: 0;
  padding-left: 18px;
  font-size: var(--font-caption);
  word-break: break-all;
}
</style>
