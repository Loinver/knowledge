<script setup lang="ts">
import {
  NAlert,
  NButton,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NSpace,
  NSpin,
  NTable,
  NTag,
} from 'naive-ui'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import type { ExtractionRun } from '@/api/extraction'
import { extractionApi } from '@/api/extraction'
import type { components } from '@/api/schema'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'
import { useAsyncData } from '@/composables/useAsyncData'

const { t, locale } = useI18n()
const route = useRoute()
const { toMessage } = useApiError()
const page = ref(1)
const { data, error, loading, reload } = useAsyncData((signal) =>
  extractionApi.list(page.value, signal),
)
const downloading = ref<number | null>(null)
const downloadError = ref('')
const showSummary = ref(false)
const selectedRun = ref<ExtractionRun | null>(null)
const selectedId = ref<number | null>(null)
const report = ref<components['schemas']['ExtractionRunExport'] | null>(null)
const reportError = ref('')
const reportLoading = ref(false)
let reportController: AbortController | undefined
const counts = computed(() => report.value?.counts ?? selectedRun.value?.counts ?? {})
const finishedAt = computed(() =>
  report.value ? report.value.finished_at : selectedRun.value?.finished_at,
)
const runStatus = computed(() =>
  finishedAt.value ? (report.value?.status ?? selectedRun.value?.status ?? '') : 'UNFINISHED',
)
const countKeys = ['entity_count', 'triple_count', 'quarantine_count'] as const
function countValue(key: string): string {
  return typeof counts.value[key] === 'number'
    ? new Intl.NumberFormat(locale.value).format(counts.value[key] as number)
    : t('extractionUi.notRecorded')
}
async function openSummary(id: number, run?: ExtractionRun): Promise<void> {
  reportController?.abort()
  const request = new AbortController()
  reportController = request
  selectedId.value = id
  selectedRun.value = run ?? null
  report.value = null
  reportError.value = ''
  reportLoading.value = true
  showSummary.value = true
  try {
    const blob = await extractionApi.exportRun(id, request.signal)
    const result = JSON.parse(await blob.text()) as components['schemas']['ExtractionRunExport']
    if (request.signal.aborted) return
    if (result.run_id !== id) throw { code: 'KG.INVALID_REQUEST' }
    report.value = result
  } catch (cause) {
    if (!request.signal.aborted) reportError.value = toMessage(cause)
  } finally {
    if (!request.signal.aborted) reportLoading.value = false
  }
}
watch(
  showSummary,
  (open) => {
    if (!open) reportController?.abort()
  },
  { flush: 'sync' },
)
watch(
  () => route?.query.run,
  (value) => {
    const id = Number(value)
    if (Number.isInteger(id) && id > 0) void openSummary(id)
  },
  { immediate: true },
)
const controller = new AbortController()
onBeforeUnmount(() => {
  controller.abort()
  reportController?.abort()
})
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
    <NAlert v-if="error" type="error"
      >{{ error
      }}<NButton :disabled="loading" @click="reload">{{ t('extractionUi.retry') }}</NButton></NAlert
    >
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
              <td>
                <NButton text type="primary" @click="openSummary(run.id, run)">{{
                  t('extractionUi.runTitle', { id: run.id })
                }}</NButton>
              </td>
              <td>{{ run.mapping_revision_id }}</td>
              <td>
                <NTag
                  :type="
                    run.finished_at && run.status === 'SUCCESS'
                      ? 'success'
                      : run.finished_at && run.status === 'FAILED'
                        ? 'error'
                        : 'default'
                  "
                  >{{
                    run.finished_at
                      ? t('runs.statuses.' + run.status, run.status)
                      : t('runs.unfinished')
                  }}</NTag
                >
              </td>
              <td>{{ formatTime(run.started_at) }}</td>
              <td>
                {{ run.finished_at ? formatTime(run.finished_at) : '-' }}
              </td>
              <td>
                <NButton text type="primary" @click="openSummary(run.id, run)">{{
                  t('extractionUi.summary')
                }}</NButton>
                <NButton
                  quaternary
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
    <NDrawer v-model:show="showSummary" :width="'min(640px, 100vw)'">
      <NDrawerContent :title="t('extractionUi.runTitle', { id: selectedId })" closable>
        <NSpin :show="reportLoading" :aria-busy="reportLoading">
          <div class="summary-content">
            <NAlert v-if="reportError" type="error"
              >{{ reportError
              }}<NButton
                :disabled="reportLoading"
                @click="openSummary(selectedId!, selectedRun ?? undefined)"
                >{{ t('extractionUi.retry') }}</NButton
              ></NAlert
            >
            <template v-if="report || selectedRun">
              <NTag
                :type="
                  runStatus === 'SUCCESS'
                    ? 'success'
                    : runStatus === 'FAILED'
                      ? 'error'
                      : runStatus === 'PARTIAL'
                        ? 'warning'
                        : 'default'
                "
                >{{
                  runStatus === 'UNFINISHED'
                    ? t('runs.unfinished')
                    : t(`runs.statuses.${runStatus}`, runStatus)
                }}</NTag
              >
              <NAlert v-if="['FAILED', 'CANCELLED'].includes(runStatus)" type="warning">{{
                t('extractionUi.resultProtected')
              }}</NAlert>
              <div class="count-grid">
                <div v-for="key in countKeys" :key="key" class="count">
                  <strong>{{ countValue(key) }}</strong
                  ><span>{{ t(`extractionUi.counts.${key}`) }}</span>
                </div>
              </div>
              <h3>{{ t('extractionUi.versionChain') }}</h3>
              <dl>
                <dt>{{ t('runs.mappingRevision') }}</dt>
                <dd>
                  {{
                    report?.mapping_revision_id ??
                    selectedRun?.mapping_revision_id ??
                    t('extractionUi.notRecorded')
                  }}
                </dd>
                <dt>{{ t('dataAccess.mapping.ontologyRevision') }}</dt>
                <dd>
                  {{
                    report?.ontology_revision ??
                    selectedRun?.cfg_snapshot?.onto_version ??
                    t('extractionUi.notRecorded')
                  }}
                </dd>
                <dt>{{ t('tasks.datasource') }}</dt>
                <dd>
                  {{
                    report?.datasource_id ??
                    selectedRun?.cfg_snapshot?.datasource_id ??
                    t('extractionUi.notRecorded')
                  }}
                </dd>
                <dt>{{ t('runs.startedAt') }}</dt>
                <dd>
                  {{
                    report?.started_at || selectedRun?.started_at
                      ? formatTime((report?.started_at ?? selectedRun?.started_at)!)
                      : t('extractionUi.notRecorded')
                  }}
                </dd>
                <dt>{{ t('runs.finishedAt') }}</dt>
                <dd>{{ finishedAt ? formatTime(finishedAt) : t('runs.unfinished') }}</dd>
              </dl>
              <h3>{{ t('extractionUi.publication') }}</h3>
              <div v-if="report?.publication" class="publication">
                <strong>{{
                  t('graph.resultSet', { id: report.publication.graph_revision_id })
                }}</strong>
                <time :datetime="report.publication.published_at">{{
                  formatTime(report.publication.published_at)
                }}</time>
              </div>
              <NAlert v-else-if="!reportLoading && !reportError" type="info">{{
                t('extractionUi.noPublication')
              }}</NAlert>
              <p class="hint">{{ t('extractionUi.reportScope') }}</p>
              <details v-if="report">
                <summary>{{ t('extractionUi.reportDetails') }}</summary>
                <pre>{{ JSON.stringify(report, null, 2) }}</pre>
              </details>
            </template>
          </div>
        </NSpin>
        <template #footer
          ><NButton
            :disabled="selectedId === null || downloading !== null"
            :loading="downloading === selectedId"
            @click="download(selectedId!)"
            >{{ t('runs.download') }}</NButton
          ></template
        >
      </NDrawerContent>
    </NDrawer>
  </section>
</template>

<style scoped>
.runs-page {
  display: grid;
  gap: 16px;
}
.table-scroll {
  overflow-x: auto;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-medium);
}
.summary-content {
  display: grid;
  gap: 16px;
}
.publication {
  display: grid;
  gap: 8px;
}
.summary-content > :deep(.n-tag) {
  justify-self: start;
}
.count-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.count {
  display: grid;
  gap: 8px;
  padding: 12px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-medium);
}
.count strong {
  font-size: 22px;
}
.count span,
dt,
.hint {
  color: var(--text-secondary);
}
h3 {
  margin: 0;
  font-size: 16px;
}
dl {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr);
  gap: 12px;
  margin: 0;
}
dd {
  margin: 0;
  overflow-wrap: anywhere;
}
pre {
  margin: 0;
  padding: 12px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font: 12px var(--font-mono);
  background: var(--bg-surface);
  border: 1px solid var(--border);
}
summary {
  cursor: pointer;
  color: var(--pri);
  margin-bottom: 12px;
}
</style>
