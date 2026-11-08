<script setup lang="ts">
import { NAlert, NButton, NEmpty, NFormItem, NInput, NSelect, NSpin } from 'naive-ui'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ontologyApi } from '@/api/ontology'
import PageHeader from '@/components/PageHeader.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useAuthStore } from '@/stores/auth'
import ExtractionSuggestions from '@/views/extraction/components/ExtractionSuggestions.vue'

const { t, locale } = useI18n()
const ontologyId = ref<number | null>(null)
const text = ref('')
const auth = useAuthStore()
const canWrite = computed(() => auth.user?.role === 'ADMIN' || auth.user?.role === 'EDITOR')
const {
  data: ontologies,
  error,
  loading,
  reload,
} = useAsyncData((signal) => ontologyApi.list({}, signal))
/** 与 OntologyExport 一致：按当前界面语言取标签，语言缺失回退 zh-CN，再回退机读名。 */
function pickLabel(labels: Record<string, string> | null | undefined, fallback: string): string {
  return labels?.[locale.value] ?? labels?.['zh-CN'] ?? fallback
}
const ontologyOptions = computed(() =>
  (ontologies.value ?? []).map((item) => ({
    value: item.id,
    label: `${pickLabel(item.label_i18n, item.name)} · ${item.name}`,
  })),
)
</script>

<template>
  <section class="ai-page">
    <PageHeader :title="t('page.aiAssist')" :description="t('ai.pageHint')" />
    <NAlert v-if="!canWrite" type="info">{{ t('extractionUi.viewer') }}</NAlert>
    <NAlert v-if="error" type="error"
      >{{ error }}<NButton @click="reload">{{ t('extractionUi.retry') }}</NButton></NAlert
    >
    <NSpin :show="loading" :aria-busy="loading">
      <div class="ai-workspace">
        <section class="source-panel">
          <h2>{{ t('extractionUi.documentSource') }}</h2>
          <NFormItem :label="t('dataAccess.mapping.targetOntology')" label-placement="top">
            <NSelect
              v-model:value="ontologyId"
              :options="ontologyOptions"
              :disabled="loading || !canWrite"
              :placeholder="t('dataAccess.mapping.chooseOntology')"
              filterable
            />
          </NFormItem>
          <NEmpty
            v-if="!loading && !error && !ontologies?.length"
            :description="t('dataAccess.mapping.noOntologies')"
          />
          <NFormItem :label="t('ai.documentText')" label-placement="top">
            <NInput
              v-model:value="text"
              type="textarea"
              :disabled="!canWrite"
              :autosize="{ minRows: 12, maxRows: 24 }"
              :placeholder="t('ai.documentPlaceholder')"
            />
          </NFormItem>
          <p class="hint">{{ t('extractionUi.sourceKept') }}</p>
        </section>
        <section class="review-panel">
          <ExtractionSuggestions
            v-if="ontologyId"
            :key="ontologyId"
            kind="DOCUMENT_FACTS"
            :title="t('ai.documentSuggestions')"
            :target-id="ontologyId"
            :text="text"
            review-only
          />
          <NEmpty v-else :description="t('extractionUi.chooseAiContext')" />
        </section>
      </div>
    </NSpin>
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
@media (max-width: 1000px) {
  .ai-workspace {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
