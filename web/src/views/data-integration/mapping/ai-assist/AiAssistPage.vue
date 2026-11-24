<script setup lang="ts">
import '../../integration.css'

import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ontologyApi } from '@/api/ontology'
import PageHeader from '@/components/PageHeader.vue'
import type { FormInst, FormRules, InputInst } from '@/components/ui'
import {
  FormContainer,
  FormField,
  UiAlert,
  UiButton,
  UiEmpty,
  UiInput,
  UiSelect,
  UiSpin,
} from '@/components/ui'
import { useAsyncData } from '@/composables/useAsyncData'
import { useAuthStore } from '@/stores/auth'
import ExtractionSuggestions from '@/views/data-integration/mapping/components/ExtractionSuggestions.vue'

const { t, locale } = useI18n()
const ontologyId = ref<number | null>(null)
const text = ref('')
const sourceInput = ref<InputInst | null>(null)
const sourceForm = ref<FormInst | null>(null)
const sourceModel = computed(() => ({ ontologyId: ontologyId.value, text: text.value }))
const sourceRules = computed<FormRules>(() => ({
  ontologyId: { required: true, message: t('dataAccess.mapping.chooseOntology') },
  text: { required: true, message: t('common.required') },
}))
async function validateSource(): Promise<boolean> {
  if (!active || !canWrite.value) return false
  const source = text.value
  const target = ontologyId.value
  try {
    await sourceForm.value?.validate()
    return active && canWrite.value && source === text.value && target === ontologyId.value
  } catch {
    return false
  }
}
const evidenceQuote = ref<string | null>(null)
const highlight = ref<HTMLElement | null>(null)
let active = true
const evidenceParts = computed(() => {
  const quote = evidenceQuote.value
  const start = quote ? text.value.indexOf(quote) : -1
  return quote && start >= 0
    ? [text.value.slice(0, start), quote, text.value.slice(start + quote.length)]
    : null
})
watch([text, ontologyId], () => (evidenceQuote.value = null), { flush: 'sync' })
onBeforeUnmount(() => {
  active = false
  evidenceQuote.value = null
})

async function locateEvidence(quote: string | null) {
  if (!quote?.trim() || !text.value.includes(quote)) {
    evidenceQuote.value = null
    return
  }
  evidenceQuote.value = quote
  const source = text.value
  const target = ontologyId.value
  await nextTick()
  if (
    !active ||
    evidenceQuote.value !== quote ||
    text.value !== source ||
    ontologyId.value !== target
  )
    return
  highlight.value?.focus({ preventScroll: true })
  highlight.value?.scrollIntoView({ block: 'center' })
}

async function editSource() {
  evidenceQuote.value = null
  await nextTick()
  if (active && !evidenceQuote.value) sourceInput.value?.focus()
}
const auth = useAuthStore()
const canWrite = computed(() => auth.user?.role === 'ADMIN' || auth.user?.role === 'EDITOR')
const {
  data: ontologies,
  error,
  loading,
  reload,
} = useAsyncData((signal) => ontologyApi.list({}, signal))
/** 显示当前语言标签；缺失时保留机读名并明确标记缺译。 */
function pickLabel(labels: Record<string, string> | null | undefined, fallback: string): string {
  return labels?.[locale.value]?.trim() || `${fallback} (${t('enumDictionaries.untranslated')})`
}
const ontologyOptions = computed(() =>
  (ontologies.value ?? []).map((item) => ({
    value: item.id,
    label: `${pickLabel(item.label_i18n, item.name)} · ${item.name}`,
  })),
)
</script>

<template>
  <section class="integration-page ai-page">
    <PageHeader :title="t('page.aiAssist')" :description="t('ai.pageHint')" />
    <UiAlert v-if="!canWrite" type="info">{{ t('extractionUi.viewer') }}</UiAlert>
    <UiAlert v-if="error" type="error"
      >{{ error }}<UiButton @click="reload">{{ t('extractionUi.retry') }}</UiButton></UiAlert
    >
    <UiSpin :show="loading" :aria-busy="loading">
      <div class="ai-workspace">
        <section class="source-panel">
          <header class="integration-panel-heading">
            <h2>{{ t('extractionUi.documentSource') }}</h2>
            <span>{{ t('extractionUi.sourceKept') }}</span>
          </header>
          <FormContainer
            ref="sourceForm"
            :model="sourceModel"
            :rules="sourceRules"
            :readonly="!canWrite"
          >
            <FormField
              path="ontologyId"
              :label="t('dataAccess.mapping.targetOntology')"
              label-placement="top"
            >
              <UiSelect
                v-model:value="ontologyId"
                :options="ontologyOptions"
                :disabled="loading || !canWrite"
                :placeholder="t('dataAccess.mapping.chooseOntology')"
                filterable
              />
            </FormField>
            <UiEmpty
              v-if="!loading && !error && !ontologies?.length"
              :description="t('dataAccess.mapping.noOntologies')"
            />
            <FormField path="text" :label="t('ai.documentText')" label-placement="top">
              <UiInput
                v-show="!evidenceParts"
                ref="sourceInput"
                v-model:value="text"
                type="textarea"
                :disabled="!canWrite"
                :autosize="{ minRows: 12, maxRows: 24 }"
                :placeholder="t('ai.documentPlaceholder')"
                :input-props="{ 'aria-label': t('ai.documentText') }"
              />
              <div v-if="evidenceParts" class="source-reading">
                <div
                  class="source-highlight"
                  role="region"
                  tabindex="0"
                  :aria-label="t('ai.documentText')"
                  data-testid="ai-source-evidence"
                >
                  <span>{{ evidenceParts[0] }}</span
                  ><mark ref="highlight" tabindex="-1" data-testid="ai-evidence-highlight">{{
                    evidenceParts[1]
                  }}</mark
                  ><span>{{ evidenceParts[2] }}</span>
                </div>
                <p class="hint" role="status">{{ t('extractionUi.evidenceLocated') }}</p>
                <UiButton :disabled="!canWrite" @click="editSource">{{
                  t('extractionUi.editSource')
                }}</UiButton>
              </div>
            </FormField>
          </FormContainer>
          <p class="hint">{{ t('extractionUi.sourceKept') }}</p>
        </section>
        <section class="review-panel">
          <header class="integration-panel-heading">
            <h2>{{ t('ai.documentSuggestions') }}</h2>
            <span>{{ t('extractionUi.documentReview') }}</span>
          </header>
          <ExtractionSuggestions
            v-if="ontologyId"
            :key="ontologyId"
            kind="DOCUMENT_FACTS"
            :title="t('ai.documentSuggestions')"
            :target-id="ontologyId"
            :text="text"
            :validate-context="validateSource"
            review-only
            @locate-evidence="locateEvidence"
          />
          <UiEmpty v-else :description="t('extractionUi.chooseAiContext')" />
        </section>
      </div>
    </UiSpin>
  </section>
</template>

<style scoped>
.ai-page {
  display: grid;
  gap: 16px;
  min-width: 0;
}
.ai-workspace {
  display: grid;
  grid-template-columns: minmax(300px, 0.9fr) minmax(320px, 1.1fr);
  gap: 16px;
  align-items: start;
}
.source-panel,
.review-panel {
  padding: 20px;
  min-width: 0;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-medium);
}
h2 {
  margin: 0 0 16px;
  font-size: 16px;
}
.hint {
  color: var(--text-secondary);
}
.source-reading {
  width: 100%;
  min-width: 0;
}
.source-highlight {
  max-height: 28rem;
  overflow: auto;
  padding: var(--space-3);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: var(--text);
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-medium);
}
.source-highlight mark {
  color: var(--text);
  background: var(--accent-soft);
  box-shadow: 0 0 0 1px var(--accent);
}
@media (max-width: 1000px) {
  .ai-workspace {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
