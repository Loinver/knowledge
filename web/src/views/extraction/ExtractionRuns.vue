<script setup lang="ts">
import { NAlert, NButton, NEmpty, NSpace, NSpin, NTable } from 'naive-ui'
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { extractionApi } from '@/api/extraction'
import PageHeader from '@/components/PageHeader.vue'
import { useAsyncData } from '@/composables/useAsyncData'

const { t, locale } = useI18n()
const page = ref(1)
const { data, error, loading, reload } = useAsyncData((signal) =>
  extractionApi.list(page.value, signal),
)
const downloading = ref<number | null>(null)
const downloadError = ref('')
const controller = new AbortController()
onBeforeUnmount(() => controller.abort())
const dateFormat = computed(
  () => new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }),
)

function formatTime(value: string) {
  // Existing SQLite list responses omit the offset even though stored times are UTC.
  const timestamp = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`
  return dateFormat.value.format(new Date(timestamp))
}

async function download(id: number) {
  if (downloading.value !== null) return
  downloading.value = id
  downloadError.value = ''
  try {
    const blob = await extractionApi.exportRun(id, controller.signal)
    if (controller.signal.aborted) return
    const url = URL.createObjectURL(blob)
    try {
      const link = document.createElement('a')
      link.href = url
      link.download = `run-${id}.json`
      link.click()
    } finally {
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    }
  } catch (err: unknown) {
    if (!controller.signal.aborted) {
      downloadError.value =
        typeof err === 'object' && err && 'code' in err ? String(err.code) : 'NETWORK_ERROR'
    }
  } finally {
    downloading.value = null
  }
}
</script>

<template>
  <section class="runs-page">
    <PageHeader :title="t('page.extractionRuns')">
      <template #actions>
        <NButton :disabled="loading" @click="reload">{{ t('graph.refresh') }}</NButton>
      </template>
    </PageHeader>
    <NAlert type="info">{{ t('runs.exportNote') }}</NAlert>
    <NAlert v-if="error" type="error">{{ error }}</NAlert>
    <NAlert v-if="downloadError" type="error">
      {{ t('runs.downloadFailed', { code: downloadError }) }}
    </NAlert>
    <NSpin :show="loading">
      <div v-if="data?.length" class="table-scroll">
        <NTable :single-line="false" size="small">
          <thead>
            <tr>
              <th>{{ t('graph.run') }}</th>
              <th>{{ t('runs.mappingRevision') }}</th>
              <th>{{ t('common.status') }}</th>
              <th>{{ t('runs.startedAt') }}</th>
              <th>{{ t('runs.finishedAt') }}</th>
              <th>{{ t('runs.report') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="run in data" :key="run.id">
              <td>{{ run.id }}</td>
              <td>{{ run.mapping_revision_id }}</td>
              <td>
                {{
                  run.finished_at
                    ? t('runs.statuses.' + run.status, run.status)
                    : t('runs.unfinished')
                }}
              </td>
              <td>{{ formatTime(run.started_at) }}</td>
              <td>
                {{ run.finished_at ? formatTime(run.finished_at) : '-' }}
              </td>
              <td>
                <NButton
                  :disabled="downloading !== null"
                  :loading="downloading === run.id"
                  @click="download(run.id)"
                >
                  {{ t('runs.download') }}
                </NButton>
              </td>
            </tr>
          </tbody>
        </NTable>
      </div>
      <NEmpty v-else-if="!loading && !error" :description="t('runs.empty')" />
    </NSpin>
    <NSpace align="center">
      <NButton :disabled="loading || page === 1" @click="page--">
        {{ t('runs.previous') }}
      </NButton>
      <span aria-live="polite">{{ t('runs.page', { page }) }}</span>
      <NButton :disabled="loading || !data || data.length < 20" @click="page++">
        {{ t('runs.next') }}
      </NButton>
    </NSpace>
  </section>
</template>

<style scoped>
.runs-page {
  display: grid;
  gap: 16px;
}
.table-scroll {
  overflow-x: auto;
}
</style>
