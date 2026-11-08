<script setup lang="ts">
import { NAlert, NButton, NEmpty, NSpin, NTag } from 'naive-ui'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { aiApi, type AiSuggestion, type SuggestionKind, suggestionPayloadLines } from '@/api/ai'
import { useApiError } from '@/composables/useApiError'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{
  kind: SuggestionKind
  title: string
  targetId: number
  datasourceId?: number
  reviewOnly?: boolean
  text?: string
}>()
const emit = defineEmits<{ applied: [id: number] }>()
const { t } = useI18n()
const { toMessage } = useApiError()
const auth = useAuthStore()
const canWrite = computed(() => auth.user?.role === 'ADMIN' || auth.user?.role === 'EDITOR')
const items = ref<AiSuggestion[]>([])
const loading = ref(false)
const busyId = ref<number | null>(null)
const error = ref('')
const notice = ref('')
const loaded = ref(false)
const selected = ref<number[]>([])
let generation = 0

function reset() {
  generation++
  items.value = []
  selected.value = []
  loaded.value = false
  loading.value = false
  busyId.value = null
  error.value = ''
  notice.value = ''
}
watch(() => [props.targetId, props.datasourceId, props.text], reset)
onBeforeUnmount(() => {
  generation++
})

async function generate() {
  if (
    !canWrite.value ||
    loading.value ||
    busyId.value !== null ||
    (props.kind === 'DOCUMENT_FACTS' && !props.text?.trim())
  )
    return
  const current = ++generation
  loading.value = true
  error.value = ''
  notice.value = ''
  try {
    const result =
      props.kind === 'MAPPING_SUGGEST'
        ? await aiApi.suggestMapping(props.targetId, props.datasourceId!)
        : await aiApi.extractDocument(props.targetId, props.text!.trim())
    if (current !== generation) return
    items.value = result
    selected.value = []
    loaded.value = true
  } catch (cause) {
    if (current === generation) error.value = toMessage(cause)
  } finally {
    if (current === generation) loading.value = false
  }
}
function toggle(id: number) {
  selected.value = selected.value.includes(id)
    ? selected.value.filter((value) => value !== id)
    : [...selected.value, id]
}
async function apply(id: number) {
  if (!canWrite.value || props.reviewOnly || busyId.value !== null || !selected.value.includes(id))
    return
  const current = generation
  busyId.value = id
  error.value = ''
  try {
    await aiApi.apply(id)
    if (current !== generation) return
    items.value = items.value.filter((item) => item.id !== id)
    selected.value = selected.value.filter((value) => value !== id)
    notice.value = t('ai.applied')
    emit('applied', id)
  } catch (cause) {
    if (current === generation) error.value = toMessage(cause)
  } finally {
    if (current === generation) busyId.value = null
  }
}
async function discard(id: number) {
  if (!canWrite.value || props.reviewOnly || busyId.value !== null) return
  const current = generation
  busyId.value = id
  error.value = ''
  try {
    await aiApi.discard(id)
    if (current !== generation) return
    items.value = items.value.filter((item) => item.id !== id)
    selected.value = selected.value.filter((value) => value !== id)
  } catch (cause) {
    if (current === generation) error.value = toMessage(cause)
  } finally {
    if (current === generation) busyId.value = null
  }
}
defineExpose({ generate })
</script>

<template>
  <section class="suggestions">
    <h3>{{ title }}</h3>
    <NAlert type="info">{{
      t(reviewOnly ? 'extractionUi.documentReview' : 'extractionUi.aiReview')
    }}</NAlert>
    <NAlert v-if="!canWrite" type="info">{{ t('extractionUi.viewer') }}</NAlert>
    <NButton
      type="primary"
      :loading="loading"
      :disabled="
        !canWrite || loading || busyId !== null || (kind === 'DOCUMENT_FACTS' && !text?.trim())
      "
      @click="generate"
      >{{ t('ai.generate') }}</NButton
    >
    <NAlert v-if="error" type="error"
      >{{ error
      }}<NButton :disabled="loading" @click="generate">{{
        t('extractionUi.retry')
      }}</NButton></NAlert
    >
    <NAlert v-if="notice" type="success">{{ notice }}</NAlert>
    <NSpin :show="loading" :aria-busy="loading">
      <NEmpty
        v-if="!items.length && !loading && !error"
        :description="t(loaded ? 'ai.empty' : 'extractionUi.aiNotGenerated')"
      />
      <article v-for="item in items" :key="item.id" class="suggestion">
        <div class="suggestion-title">
          <strong>{{ item.title }}</strong
          ><NTag size="small">{{
            t(
              selected.includes(item.id)
                ? 'extractionUi.selectedSuggestion'
                : 'extractionUi.suggestion',
            )
          }}</NTag>
        </div>
        <p v-if="item.explanation">{{ item.explanation }}</p>
        <ul>
          <li v-for="line in suggestionPayloadLines(item)" :key="line">{{ line }}</li>
        </ul>
        <div class="actions">
          <NButton :disabled="!canWrite || busyId !== null" @click="toggle(item.id)">{{
            t(
              selected.includes(item.id)
                ? 'extractionUi.undoSelection'
                : 'extractionUi.reviewSuggestion',
            )
          }}</NButton>
          <NButton
            v-if="!reviewOnly"
            type="primary"
            :loading="busyId === item.id"
            :disabled="!canWrite || busyId !== null || !selected.includes(item.id)"
            @click="apply(item.id)"
            >{{ t('ai.apply') }}</NButton
          >
          <NButton
            v-if="!reviewOnly"
            :disabled="!canWrite || busyId !== null"
            @click="discard(item.id)"
            >{{ t('ai.discard') }}</NButton
          >
        </div>
      </article>
    </NSpin>
  </section>
</template>

<style scoped>
.suggestions {
  display: grid;
  gap: 16px;
}
h3 {
  margin: 0;
  font-size: 16px;
}
.suggestion {
  padding: 16px;
  margin-bottom: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-medium);
  background: var(--bg-surface);
}
.suggestion-title,
.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
p,
li {
  overflow-wrap: anywhere;
}
ul {
  padding-left: 20px;
}
</style>
