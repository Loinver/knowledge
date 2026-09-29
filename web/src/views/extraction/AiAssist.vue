<script setup lang="ts">
import { NAlert, NButton, NFormItem, NInput, NSelect } from 'naive-ui'
import { onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ontologyApi } from '@/api/ontology'
import PageHeader from '@/components/PageHeader.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import AiSuggestions from '@/views/ontology/components/AiSuggestions.vue'

const { t, locale } = useI18n()
const ontologyId = ref<number | null>(null)
const text = ref('')
const panelRef = ref<InstanceType<typeof AiSuggestions> | null>(null)
let controller: AbortController | undefined

const {
  data: ontologies,
  error,
  loading,
} = useAsyncData((_signal) => {
  controller?.abort()
  controller = new AbortController()
  return ontologyApi.list({ page: 1, page_size: 200 }, controller.signal)
})
/** 与 OntologyExport 一致：按当前界面语言取标签，语言缺失回退 zh-CN，再回退机读名。 */
function pickLabel(labels: Record<string, string> | null | undefined, fallback: string): string {
  return labels?.[locale.value] ?? labels?.['zh-CN'] ?? fallback
}
const ontologyOptions = ref<{ value: number; label: string }[]>([])
watch(
  ontologies,
  (items) => {
    ontologyOptions.value = (items ?? []).map((item) => ({
      value: item.id,
      label: `${pickLabel(item.label_i18n, item.name)} · ${item.name}`,
    }))
  },
  { immediate: true },
)
onBeforeUnmount(() => controller?.abort())

function extract() {
  if (!ontologyId.value || !text.value.trim()) return
  void panelRef.value?.generate(text.value.trim())
}
</script>

<template>
  <section class="ai-page">
    <PageHeader :title="t('page.aiAssist')" :description="t('ai.pageHint')" />
    <NAlert v-if="error" type="warning">{{ error }}</NAlert>
    <p v-if="loading" role="status">{{ t('common.loading') }}</p>
    <NFormItem :label="t('dataAccess.mapping.targetOntology')" label-placement="left">
      <NSelect
        v-model:value="ontologyId"
        :options="ontologyOptions"
        :placeholder="t('dataAccess.mapping.chooseOntology')"
        filterable
      />
    </NFormItem>
    <NFormItem :label="t('ai.documentText')" label-placement="top">
      <NInput
        v-model:value="text"
        type="textarea"
        :autosize="{ minRows: 6, maxRows: 16 }"
        :placeholder="t('ai.documentPlaceholder')"
      />
    </NFormItem>
    <NButton type="primary" :disabled="!ontologyId || !text.trim()" @click="extract">
      {{ t('ai.extract') }}
    </NButton>
    <template v-if="ontologyId">
      <AiSuggestions
        ref="panelRef"
        kind="DOCUMENT_FACTS"
        :title="t('ai.documentSuggestions')"
        :target-id="ontologyId"
        review-only
      />
    </template>
  </section>
</template>

<style scoped>
.ai-page {
  display: grid;
  gap: 16px;
  max-width: 900px;
}
</style>
