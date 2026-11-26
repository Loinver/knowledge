<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { datasourcesApi } from '@/api/datasources'
import { SearchTable, UiAlert, UiButton, UiEmpty } from '@/components/ui'
import type { DataTableColumns } from '@/components/ui/tableTypes'
import { useAsyncData } from '@/composables/useAsyncData'

const props = defineProps<{
  datasourceId: number
  schema: string
  table: string
  snapshotId: number | null
}>()
const { t, locale } = useI18n()
const requested = ref(false)
watch(
  () => [props.datasourceId, props.schema, props.table, props.snapshotId],
  () => {
    requested.value = false
  },
  { flush: 'sync' },
)
const { data, error, loading, reload } = useAsyncData((signal) =>
  requested.value
    ? datasourcesApi.preview(
        {
          datasource_id: props.datasourceId,
          schema: props.schema,
          table: props.table,
          limit: 5,
          offset: 0,
        },
        signal,
      )
    : Promise.resolve(null),
)
const columns = computed<DataTableColumns<Record<string, unknown>>>(() =>
  (data.value?.columns ?? []).map((column) => ({
    key: column.name,
    title: column.name,
    width: 150,
    format: 'raw' as const,
  })),
)
</script>

<template>
  <section class="catalog-samples card">
    <header class="integration-panel-heading">
      <h2>{{ t('dataAccess.catalog.actions.samplePreview') }}</h2>
      <UiButton
        size="small"
        :loading="loading"
        :disabled="loading"
        @click="requested ? reload() : (requested = true)"
      >
        {{ t('dataAccess.preview.fetch') }}
      </UiButton>
    </header>
    <p class="integration-caption sample-context">{{ schema }} / {{ table }}</p>
    <UiAlert type="info" :show-icon="false">{{ t('ui.livePreviewContext') }}</UiAlert>
    <SearchTable
      v-if="requested"
      :rows="data?.rows ?? []"
      :columns="columns"
      mode="none"
      :searchable="false"
      :loading="loading"
      :error="error"
      :empty-text="t('dataAccess.preview.emptyResult')"
      :label="t('dataAccess.preview.resultTitle')"
      @retry="reload"
      ><template #toolbar
    /></SearchTable>
    <UiEmpty v-else :description="t('dataAccess.redesign.fetchSamples')" size="small" />
    <p class="integration-caption sample-context">
      {{ t('dataAccess.preview.limitNote', { limit: new Intl.NumberFormat(locale).format(5) }) }}
    </p>
  </section>
</template>
