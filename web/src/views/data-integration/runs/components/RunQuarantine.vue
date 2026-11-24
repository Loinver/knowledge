<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { graphApi } from '@/api/graph'
import type { components } from '@/api/schema'
import SearchTable from '@/components/business/SearchTable.vue'
import type { DataTableColumns } from '@/components/ui'
import { UiAlert, UiButton } from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useAsyncData } from '@/composables/useAsyncData'

const props = defineProps<{ runId: number }>()
const { t, locale } = useI18n()
const { toMessage } = useApiError()
const exportError = ref('')
const page = ref(1)
watch(
  () => props.runId,
  () => {
    page.value = 1
    exportError.value = ''
  },
  { flush: 'sync' },
)
const columns = computed<DataTableColumns<components['schemas']['QuarantineOut']>>(() => [
  { key: 'table_name', title: t('graph.table'), minWidth: 150, ellipsis: true },
  { key: 'row_key', title: t('graph.rowKey'), minWidth: 160, ellipsis: true },
  { key: 'field', title: t('graph.fields'), minWidth: 150, ellipsis: true },
  { key: 'rule_id', title: t('graph.chainRules'), minWidth: 160, format: 'raw' },
  { key: 'raw_value', title: t('graph.value'), minWidth: 180 },
  { key: 'transform_chain', title: t('graph.chainTransforms'), minWidth: 260 },
])
const { data, error, loading, reload } = useAsyncData((signal) => {
  const run = props.runId
  return graphApi.runQuarantine(run, signal).then((rows) => {
    if (rows.some((row) => row.run_id !== run)) throw { code: 'KG.INVALID_REQUEST' }
    return rows
  })
})

function download() {
  if (!data.value || loading.value || error.value) return
  exportError.value = ''
  let url: string | undefined
  try {
    const blob = new Blob(
      [JSON.stringify({ run_id: props.runId, quarantine: data.value }, null, 2)],
      { type: 'application/json' },
    )
    url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `run-${props.runId}-quarantine.json`
    link.click()
  } catch (cause) {
    exportError.value = toMessage(cause)
  } finally {
    if (url) {
      const captured = url
      setTimeout(() => URL.revokeObjectURL(captured), 1000)
    }
  }
}
</script>

<template>
  <section class="run-quarantine">
    <UiAlert v-if="exportError" type="error" role="alert">{{ exportError }}</UiAlert>
    <SearchTable
      v-model:page="page"
      :rows="data ?? []"
      :columns="columns"
      row-key="id"
      mode="local"
      :searchable="false"
      :page-size="20"
      :loading="loading"
      :error="error"
      :label="t('extractionUi.counts.quarantine_count')"
      :empty-text="t('graph.noQuarantine')"
      :max-height="420"
      :scroll-x="1060"
      @retry="reload"
    >
      <template #cell-raw_value="{ row }">{{
        row.raw_value ?? t('dataAccess.mapping.nullValue')
      }}</template>
      <template #cell-transform_chain="{ row }">
        <pre>{{ JSON.stringify(row.transform_chain, null, 2) }}</pre>
      </template>
    </SearchTable>
    <div class="quarantine-footer">
      <span
        >{{ t('extractionUi.runTitle', { id: runId })
        }}<template v-if="data && !loading && !error">
          · {{ new Intl.NumberFormat(locale).format(data.length) }}</template
        ></span
      ><UiButton :disabled="!data || loading || !!error" @click="download">{{
        t('graph.export.title')
      }}</UiButton>
    </div>
  </section>
</template>

<style scoped>
.run-quarantine {
  display: grid;
  gap: 12px;
  min-width: 0;
}
pre {
  margin: 0;
  font: 11px var(--font-mono);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.quarantine-footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  color: var(--text-secondary);
  font-size: 12px;
}
</style>
