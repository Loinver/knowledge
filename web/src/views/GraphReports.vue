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
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { validationApi, type ValidationResultItem } from '@/api/validation'
import { useAsyncData } from '@/composables/useAsyncData'

const { t } = useI18n()
const selectedGraphId = ref<number | null>(null)
const reportId = ref<number | null>(null)
const resultsError = ref<string>('')

const revisions = useAsyncData((_signal) => validationApi.revisions())
const revisionOptions = computed(() =>
  (revisions.data.value ?? []).map((r) => ({
    value: r.id,
    label: `#${  r.id  }${r.is_current ? ` (${  t('graph.currentResult')  })` : ''}`,
  })),
)

const report = useAsyncData((_signal) => {
  if (reportId.value === null) return Promise.resolve(null)
  return validationApi.getReport(reportId.value)
})

const results = ref<ValidationResultItem[]>([])
const loadingResults = ref(false)

async function loadResults() {
  if (reportId.value === null) {
    results.value = []
    return
  }
  loadingResults.value = true
  resultsError.value = ''
  try {
    results.value = await validationApi.getResults(reportId.value)
  } catch (err: unknown) {
    resultsError.value =
      typeof err === 'object' && err && 'code' in err ? String(err.code) : ''
  } finally {
    loadingResults.value = false
  }
}

async function runValidation() {
  if (selectedGraphId.value === null) return
  resultsError.value = ''
  try {
    const rep = await validationApi.validateGraph(selectedGraphId.value)
    reportId.value = rep.report_id
    report.reload()
    await loadResults()
  } catch (err: unknown) {
    resultsError.value =
      typeof err === 'object' && err && 'code' in err ? String(err.code) : ''
  }
}

watch(reportId, () => {
  if (reportId.value !== null) loadResults()
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
    <h2>{{ t('report.title') }}</h2>

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
        <NButton type="primary" :disabled="selectedGraphId === null" @click="runValidation">
          {{ t('report.runValidation') }}
        </NButton>
      </NSpace>
    </NCard>

    <NAlert v-if="resultsError" type="error" :title="resultsError" class="error-alert" />

    <NSpin :show="loadingResults">
      <div v-if="report.data.value" class="report-summary">
        <h3>{{ t('report.summary') }}</h3>
        <div class="stat-grid">
          <NCard size="small" class="stat-card">
            <NStatistic :label="t('report.states.PASS')" :value="report.data.value.summary.pass" />
          </NCard>
          <NCard size="small" class="stat-card">
            <NStatistic :label="t('report.states.VIOLATION')" :value="report.data.value.summary.violation" />
          </NCard>
          <NCard size="small" class="stat-card">
            <NStatistic :label="t('report.states.NA')" :value="report.data.value.summary.na" />
          </NCard>
          <NCard size="small" class="stat-card">
            <NStatistic :label="t('report.states.NOT_RUN')" :value="report.data.value.summary.not_run" />
          </NCard>
        </div>
      </div>

      <div v-if="results.length" class="results-table">
        <h3>{{ t('report.results') }}</h3>
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
            <tr v-for="item in results" :key="item.check_code">
              <td>{{ t('report.checks.' + item.check_code, item.check_code) }}</td>
              <td>
                <NTag :type="stateTagType(item.state)" size="small">
                  {{ t('report.states.' + item.state, item.state) }}
                </NTag>
              </td>
              <td class="mono">{{ item.focus_node || '-' }}</td>
              <td>{{ item.message || '-' }}</td>
            </tr>
          </tbody>
        </NTable>
      </div>

      <NEmpty v-else-if="!loadingResults && reportId !== null" :description="t('report.noReport')" />
      <NEmpty v-else :description="t('report.chooseGraph')" />
    </NSpin>
  </section>
</template>

<style scoped>
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
