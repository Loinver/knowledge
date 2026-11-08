<script setup lang="ts">
import {
  NAlert,
  NButton,
  NCard,
  NEmpty,
  NSelect,
  NSpace,
  NSpin,
  NStatistic,
  NTable,
  NTag,
} from 'naive-ui'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { validationApi, type ValidationResultItem } from '@/api/validation'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'
import { useAsyncData } from '@/composables/useAsyncData'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const { toMessage } = useApiError()
const auth = useAuthStore()
const canWrite = computed(() => ['ADMIN', 'EDITOR'].includes(auth.user?.role ?? ''))
const running = ref(false)
const stateFilter = ref<ValidationResultItem['state'] | null>(null)
const filteredResults = computed(() =>
  stateFilter.value
    ? results.value.filter((item) => item.state === stateFilter.value)
    : results.value,
)
const stateOptions = computed(() =>
  ['PASS', 'VIOLATION', 'NA', 'NOT_RUN'].map((value) => ({
    value,
    label: t(`report.states.${value}`),
  })),
)
const selectedGraphId = ref<number | null>(null)
const reportId = ref<number | null>(null)
const resultsError = ref<string>('')

const revisions = useAsyncData((_signal) => validationApi.revisions())
const revisionOptions = computed(() =>
  (revisions.data.value ?? []).map((r) => ({
    value: r.id,
    label: `#${r.id}${r.is_current ? ` (${t('graph.currentResult')})` : ''}`,
  })),
)

const report = useAsyncData((_signal) => {
  if (reportId.value === null) return Promise.resolve(null)
  return validationApi.getReport(reportId.value)
})

const results = ref<ValidationResultItem[]>([])
const loadingResults = ref(false)
let generation = 0

async function loadResults() {
  const current = generation
  const id = reportId.value
  if (reportId.value === null) {
    results.value = []
    return
  }
  loadingResults.value = true
  resultsError.value = ''
  try {
    const next = await validationApi.getResults(reportId.value)
    if (current === generation && id === reportId.value) results.value = next
  } catch (err: unknown) {
    // 按 code 走统一 i18n 码表，不把 KG.FORBIDDEN 之类的码直出到界面
    if (current === generation) resultsError.value = toMessage(err)
  } finally {
    if (current === generation) loadingResults.value = false
  }
}

async function runValidation() {
  if (selectedGraphId.value === null || running.value || !canWrite.value) return
  const current = ++generation
  reportId.value = null
  results.value = []
  await report.reload()
  if (current !== generation) return
  resultsError.value = ''
  running.value = true
  try {
    const rep = await validationApi.validateGraph(selectedGraphId.value)
    if (current !== generation) return
    reportId.value = rep.report_id
    report.reload()
    await loadResults()
  } catch (err: unknown) {
    // 按 code 走统一 i18n 码表，不把 KG.FORBIDDEN 之类的码直出到界面
    if (current === generation) resultsError.value = toMessage(err)
  } finally {
    if (current === generation) running.value = false
  }
}

watch(
  selectedGraphId,
  () => {
    generation += 1
    reportId.value = null
    results.value = []
    resultsError.value = ''
    loadingResults.value = false
    running.value = false
    void report.reload()
  },
  { flush: 'sync' },
)
onBeforeUnmount(() => {
  generation += 1
})

const stateTagType = (state: string) => {
  if (state === 'PASS') return 'success'
  if (state === 'VIOLATION') return 'error'
  if (state === 'NOT_RUN') return 'warning'
  return 'default'
}
</script>

<template>
  <section class="reports-page">
    <PageHeader :title="t('report.title')" />

    <NCard size="small" class="control-card">
      <NSpace align="center">
        <span>{{ t('report.selectGraph') }}</span>
        <NSelect
          v-model:value="selectedGraphId"
          :options="revisionOptions"
          :loading="revisions.loading.value"
          :placeholder="t('report.selectGraph')"
          style="width: 240px"
        />
        <NButton
          type="primary"
          :loading="running"
          :disabled="selectedGraphId === null || !canWrite"
          @click="runValidation"
        >
          {{ t('report.runValidation') }}
        </NButton>
      </NSpace>
    </NCard>
    <NAlert v-if="!canWrite" type="info" class="error-alert">{{ t('ui.readonly') }}</NAlert>
    <NAlert v-if="revisions.error.value" type="error" class="error-alert"
      >{{ revisions.error.value }}
      <NButton @click="revisions.reload">{{ t('ui.retry') }}</NButton></NAlert
    >
    <NAlert v-if="report.error.value" type="error" class="error-alert"
      >{{ report.error.value }}
      <NButton @click="report.reload">{{ t('ui.retry') }}</NButton></NAlert
    >

    <NAlert v-if="resultsError" type="error" :title="resultsError" class="error-alert"
      ><NButton @click="reportId ? loadResults() : runValidation()">{{
        t('ui.retry')
      }}</NButton></NAlert
    >

    <NSpin
      :show="loadingResults || running || report.loading.value"
      :aria-busy="loadingResults || running"
    >
      <div v-if="report.data.value" class="report-summary">
        <h3>{{ t('report.summary') }}</h3>
        <div class="stat-grid">
          <NCard size="small" class="stat-card">
            <NStatistic :label="t('report.states.PASS')" :value="report.data.value.summary.pass" />
          </NCard>
          <NCard size="small" class="stat-card">
            <NStatistic
              :label="t('report.states.VIOLATION')"
              :value="report.data.value.summary.violation"
            />
          </NCard>
          <NCard size="small" class="stat-card">
            <NStatistic :label="t('report.states.NA')" :value="report.data.value.summary.na" />
          </NCard>
          <NCard size="small" class="stat-card">
            <NStatistic
              :label="t('report.states.NOT_RUN')"
              :value="report.data.value.summary.not_run"
            />
          </NCard>
        </div>
      </div>

      <div v-if="results.length" class="results-table">
        <h3>{{ t('report.results') }}</h3>
        <NSelect
          v-model:value="stateFilter"
          :options="stateOptions"
          clearable
          :placeholder="t('report.state')"
          :aria-label="t('report.state')"
          class="state-filter"
        />
        <NTable :bordered="true" :single-line="false" size="small">
          <thead>
            <tr>
              <th>{{ t('report.checkCode') }}</th>
              <th>{{ t('report.state') }}</th>
              <th>{{ t('report.focusNode') }}</th>
              <th>{{ t('report.message') }}</th>
            </tr>
          </thead>
          <tbody>
            <!-- 同一检查项会对多个 focus_node 各出一行，key 必须带上焦点节点 -->
            <tr
              v-for="(item, index) in filteredResults"
              :key="`${item.check_code}-${item.focus_node ?? 'root'}-${index}`"
            >
              <td>{{ t('report.checks.' + item.check_code, item.check_code) }}</td>
              <td>
                <NTag :type="stateTagType(item.state)" size="small">
                  {{ t('report.states.' + item.state, item.state) }}
                </NTag>
              </td>
              <td class="mono">
                <RouterLink
                  v-if="item.focus_node"
                  :to="{
                    name: 'graph-browse',
                    query: { graph: selectedGraphId, center: item.focus_node },
                  }"
                  >{{ item.focus_node }}</RouterLink
                >
                <span v-else>-</span>
              </td>
              <td>{{ item.message || '-' }}</td>
            </tr>
          </tbody>
        </NTable>
      </div>

      <NEmpty
        v-else-if="!loadingResults && !running && !resultsError && reportId !== null"
        :description="t('report.noReport')"
      />
      <NEmpty
        v-else-if="!loadingResults && !running && !resultsError"
        :description="t('report.chooseGraph')"
      />
    </NSpin>
  </section>
</template>

<style scoped>
.state-filter {
  max-width: 240px;
  margin-bottom: 12px;
}
.reports-page {
  padding: 0 0 24px;
}
h2,
h3 {
  color: var(--text);
  margin: 0 0 16px;
}
.control-card {
  margin-bottom: 24px;
}
.error-alert {
  margin-bottom: 16px;
}
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}
.stat-card {
  text-align: center;
}
.results-table {
  margin-top: 24px;
}
.mono {
  font-family: monospace;
  font-size: 12px;
  word-break: break-all;
}
</style>
