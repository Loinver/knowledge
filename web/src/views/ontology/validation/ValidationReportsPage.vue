<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'

import { ontologyApi } from '@/api/ontology'
import { validationApi, type ValidationResultItem } from '@/api/validation'
import PageHeader from '@/components/PageHeader.vue'
import {
  UiAlert,
  UiButton,
  UiEmpty,
  UiInputNumber,
  UiRadioButton,
  UiRadioGroup,
  UiSelect,
  UiSpin,
  UiTable,
  UiTag,
} from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useAsyncData } from '@/composables/useAsyncData'
import { usePageIdentity } from '@/layout/navigation/usePageIdentity'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const route = useRoute()
const { toMessage } = useApiError()
const auth = useAuthStore()
const canWrite = computed(() => ['ADMIN', 'EDITOR'].includes(auth.user?.role ?? ''))
const running = ref(false)
const scope = ref<'GRAPH' | 'ONTOLOGY'>('GRAPH')
const selectedOntologyId = ref<number | null>(null)
const ontologyTarget = ref<'WORKING' | 'PUBLISHED'>('WORKING')
const ontologyRevision = ref<number | null>(null)
const selectedResult = ref<ValidationResultItem | null>(null)
const ontologies = useAsyncData(() =>
  scope.value === 'ONTOLOGY' ? ontologyApi.list() : Promise.resolve([]),
)
const ontologyOptions = computed(() =>
  (ontologies.data.value ?? []).map((item) => ({ label: item.name, value: item.id })),
)
const selectedOntology = computed(() =>
  ontologies.data.value?.find((item) => item.id === selectedOntologyId.value),
)
const canRun = computed(
  () =>
    canWrite.value &&
    !running.value &&
    (scope.value === 'GRAPH'
      ? selectedGraphId.value !== null
      : selectedOntologyId.value !== null &&
        (ontologyTarget.value === 'WORKING' || !!selectedOntology.value?.current_revision)),
)
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
usePageIdentity(() => (report.data.value ? `#${report.data.value.report_id}` : undefined))
const readouts = computed(() =>
  (['PASS', 'VIOLATION', 'NA', 'NOT_RUN'] as const).map((state) => ({
    state,
    count:
      report.data.value?.summary[state.toLowerCase() as 'pass' | 'violation' | 'na' | 'not_run'],
  })),
)

const results = ref<ValidationResultItem[]>([])
const loadingResults = ref(false)
let generation = 0
let resultsGeneration = 0

async function loadResults() {
  const read = ++resultsGeneration
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
    if (read === resultsGeneration && current === generation && id === reportId.value)
      results.value = next
  } catch (err: unknown) {
    // 按 code 走统一 i18n 码表，不把 KG.FORBIDDEN 之类的码直出到界面
    if (read === resultsGeneration && current === generation) resultsError.value = toMessage(err)
  } finally {
    if (read === resultsGeneration && current === generation) loadingResults.value = false
  }
}

async function runValidation() {
  if (!canRun.value) return
  const current = ++generation
  running.value = true
  const graphId = selectedGraphId.value
  const ontologyId = selectedOntologyId.value
  const target = ontologyTarget.value
  const revision = ontologyRevision.value ?? selectedOntology.value?.current_revision
  const validationScope = scope.value
  reportId.value = null
  results.value = []
  selectedResult.value = null
  await report.reload()
  if (current !== generation) return
  resultsError.value = ''
  running.value = true
  try {
    const rep =
      validationScope === 'GRAPH'
        ? await validationApi.validateGraph(graphId!)
        : await validationApi.validateOntology(ontologyId!, {
            target,
            ...(target === 'PUBLISHED' ? { revision } : {}),
          })
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
  [selectedGraphId, selectedOntologyId, scope, ontologyTarget, ontologyRevision],
  () => {
    generation += 1
    resultsGeneration += 1
    reportId.value = null
    results.value = []
    selectedResult.value = null
    stateFilter.value = null
    resultsError.value = ''
    loadingResults.value = false
    running.value = false
    void report.reload()
  },
  { flush: 'sync' },
)
watch(
  () => route.query.graph,
  (value) => {
    const id = Number(value)
    selectedGraphId.value = Number.isSafeInteger(id) && id > 0 ? id : null
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  generation += 1
  resultsGeneration += 1
})
watch(
  selectedOntologyId,
  () => {
    ontologyRevision.value = null
  },
  { flush: 'sync' },
)

const stateTagType = (state: string) => {
  if (state === 'PASS') return 'success'
  if (state === 'VIOLATION') return 'error'
  if (state === 'NOT_RUN') return 'warning'
  return 'default'
}
</script>

<template>
  <section class="reports-page">
    <PageHeader
      :title="t('page.graphReports')"
      :eyebrow="t('studio.validationLedger')"
      :identity="report.data.value ? `#${report.data.value.report_id}` : undefined"
      :description="t('studio.validationScope')"
    >
      <template #actions>
        <UiButton type="primary" :loading="running" :disabled="!canRun" @click="runValidation">
          {{ t(scope === 'GRAPH' ? 'report.runValidation' : 'designer.runValidation') }}
        </UiButton>
      </template>
    </PageHeader>
    <div class="validation-controls">
      <UiRadioGroup v-model:value="scope" :aria-label="t('studio.validationScopeLabel')">
        <UiRadioButton value="GRAPH">{{ t('page.graphBrowse') }}</UiRadioButton>
        <UiRadioButton value="ONTOLOGY">{{ t('page.ontologies') }}</UiRadioButton>
      </UiRadioGroup>
      <label v-if="scope === 'GRAPH'" class="target-field">
        <span>{{ t('report.selectGraph') }}</span>
        <UiSelect
          v-model:value="selectedGraphId"
          :options="revisionOptions"
          :loading="revisions.loading.value"
          :placeholder="t('report.selectGraph')"
          :aria-label="t('report.selectGraph')"
        />
      </label>
      <template v-else>
        <label class="target-field"
          ><span>{{ t('designer.selectOntology') }}</span>
          <UiSelect
            v-model:value="selectedOntologyId"
            :options="ontologyOptions"
            :loading="ontologies.loading.value"
            :placeholder="t('designer.selectOntology')"
            :aria-label="t('designer.selectOntology')"
        /></label>
        <UiSelect
          v-model:value="ontologyTarget"
          class="target-mode"
          :aria-label="t('designerUi.versionView')"
          :options="[
            { value: 'WORKING', label: t('designerUi.workingContent') },
            { value: 'PUBLISHED', label: t('designerUi.frozenContent') },
          ]"
        />
        <label v-if="ontologyTarget === 'PUBLISHED'" class="target-field revision-field">
          <span>{{ t('common.revision') }}</span>
          <UiInputNumber
            v-model:value="ontologyRevision"
            :min="1"
            :precision="0"
            :max="selectedOntology?.current_revision || undefined"
            :placeholder="String(selectedOntology?.current_revision || '')"
            :aria-label="t('common.revision')"
          />
        </label>
      </template>
    </div>
    <UiAlert v-if="!canWrite" type="info">{{ t('ui.readonly') }}</UiAlert>
    <UiAlert v-if="revisions.error.value && scope === 'GRAPH'" type="error">
      {{ revisions.error.value }}<UiButton @click="revisions.reload">{{ t('ui.retry') }}</UiButton>
    </UiAlert>
    <UiAlert v-if="ontologies.error.value && scope === 'ONTOLOGY'" type="error">
      {{ ontologies.error.value
      }}<UiButton @click="ontologies.reload">{{ t('ui.retry') }}</UiButton>
    </UiAlert>
    <UiAlert v-if="report.error.value" type="error">
      {{ report.error.value }}<UiButton @click="report.reload">{{ t('ui.retry') }}</UiButton>
    </UiAlert>
    <UiAlert v-if="resultsError" type="error" :title="resultsError">
      <UiButton @click="reportId ? loadResults() : runValidation()">{{ t('ui.retry') }}</UiButton>
    </UiAlert>
    <div class="report-readouts" :aria-label="t('report.summary')">
      <button
        v-for="entry in readouts"
        :key="entry.state"
        type="button"
        :class="`readout--${entry.state.toLowerCase()}`"
        :aria-pressed="stateFilter === entry.state"
        @click="stateFilter = stateFilter === entry.state ? null : entry.state"
      >
        <span class="state-code"
          ><svg
            v-if="entry.state === 'NOT_RUN'"
            viewBox="0 0 16 16"
            width="12"
            height="12"
            aria-hidden="true"
          >
            <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" />
            <path d="M8 4v4l3 2" fill="none" stroke="currentColor" /></svg
          >{{ entry.state }}</span
        >
        <strong>{{ entry.count ?? '—' }}</strong>
        <span>{{ t(`report.states.${entry.state}`) }}</span>
      </button>
    </div>
    <div v-if="report.data.value" class="report-binding">
      <span
        >{{ t('studio.identity') }} <code>{{ `#${report.data.value.target_id}` }}</code></span
      >
      <span
        >{{ t('common.revision') }} <code>{{ report.data.value.target_revision }}</code></span
      >
      <span v-if="report.data.value.binding">{{
        t(
          report.data.value.binding.target === 'WORKING'
            ? 'designerUi.workingContent'
            : 'designerUi.frozenContent',
        )
      }}</span>
      <code v-if="report.data.value.binding?.working_draft_id">{{
        report.data.value.binding.working_draft_id
      }}</code>
      <span v-if="report.data.value.binding?.edit_revision"
        >{{ t('common.revision') }} {{ report.data.value.binding.edit_revision }}</span
      >
    </div>
    <UiSpin
      :show="loadingResults || running || report.loading.value"
      :aria-busy="loadingResults || running"
    >
      <div class="report-workspace">
        <section class="results-table">
          <header class="results-head">
            <h2>{{ t(scope === 'GRAPH' ? 'report.title' : 'report.results') }}</h2>
            <UiSelect
              v-model:value="stateFilter"
              :options="stateOptions"
              clearable
              :placeholder="t('report.state')"
              :aria-label="t('report.state')"
              class="state-filter"
            />
          </header>
          <div v-if="results.length" class="table-scroll">
            <UiTable :bordered="false" :single-line="false" size="small">
              <thead>
                <tr>
                  <th>{{ t('report.checkCode') }}</th>
                  <th>{{ t('report.state') }}</th>
                  <th>{{ t('report.focusNode') }}</th>
                  <th>{{ t('report.message') }}</th>
                  <th>{{ t('common.actions') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(item, index) in filteredResults"
                  :key="`${item.check_code}-${item.focus_node ?? 'root'}-${index}`"
                  :class="{ selected: selectedResult === item }"
                >
                  <td>
                    <code>{{ item.check_code }}</code
                    ><br />{{ t('report.checks.' + item.check_code, item.check_code) }}
                  </td>
                  <td>
                    <UiTag :type="stateTagType(item.state)" size="small"
                      >{{ item.state }} · {{ t('report.states.' + item.state, item.state) }}</UiTag
                    >
                  </td>
                  <td class="mono">
                    <RouterLink
                      v-if="item.focus_node && scope === 'GRAPH'"
                      :to="{
                        name: 'graph-browse',
                        query: { graph: selectedGraphId, center: item.focus_node },
                      }"
                      >{{ item.focus_node }}</RouterLink
                    >
                    <span v-else>{{ item.focus_node || '—' }}</span>
                  </td>
                  <td>{{ item.message || '—' }}</td>
                  <td>
                    <UiButton size="small" quaternary @click="selectedResult = item">{{
                      t('graphUi.inspector')
                    }}</UiButton>
                  </td>
                </tr>
              </tbody>
            </UiTable>
            <UiEmpty v-if="!filteredResults.length" :description="t('ui.emptyFiltered')" />
          </div>
          <UiEmpty
            v-else-if="!loadingResults && !running && !resultsError"
            :description="t(reportId !== null ? 'report.noReport' : 'report.chooseGraph')"
          />
        </section>
        <aside class="report-inspector">
          <header>
            <h2>{{ t('graphUi.inspector') }}</h2>
            <UiButton
              v-if="selectedResult"
              size="small"
              quaternary
              @click="selectedResult = null"
              >{{ t('common.close') }}</UiButton
            >
          </header>
          <template v-if="selectedResult">
            <code>{{ selectedResult.check_code }}</code>
            <UiTag :type="stateTagType(selectedResult.state)"
              >{{ selectedResult.state }} · {{ t(`report.states.${selectedResult.state}`) }}</UiTag
            >
            <p>{{ selectedResult.message || '—' }}</p>
            <dl>
              <dt>{{ t('report.focusNode') }}</dt>
              <dd>{{ selectedResult.focus_node || '—' }}</dd>
              <dt>{{ t('studio.rule') }}</dt>
              <dd>{{ selectedResult.rule_id || '—' }}</dd>
            </dl>
            <pre v-if="selectedResult.detail">{{
              JSON.stringify(selectedResult.detail, null, 2)
            }}</pre>
          </template>
          <UiEmpty v-else :description="t('studio.selectCheck')" />
          <p class="capability-note">{{ t('studio.reportCapabilities') }}</p>
        </aside>
      </div>
    </UiSpin>
  </section>
</template>

<style scoped>
.reports-page {
  display: grid;
  gap: 16px;
  min-width: 0;
}
.validation-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 9px;
}
.target-field {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--text-secondary);
}
.target-field :deep(.ui-select) {
  width: 240px;
}
.target-mode {
  width: 180px;
}
.revision-field :deep(.ui-number-input) {
  width: 110px;
}
.report-readouts {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-panel);
  overflow: hidden;
}
.report-readouts button {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  padding: 16px;
  text-align: left;
  color: var(--text-secondary);
  background: transparent;
  border: 0;
  border-right: 1px solid var(--border);
  cursor: pointer;
  font: inherit;
}
.report-readouts button:last-child {
  border-right: 0;
}
.report-readouts button[aria-pressed='true'] {
  background: var(--bg-inset);
  box-shadow: inset 0 -2px var(--state);
}
.report-readouts strong {
  grid-row: span 2;
  font: 600 24px var(--font-mono, monospace);
  color: var(--state);
}
.state-code {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font: 600 12px var(--font-mono, monospace);
  color: var(--state);
}
.readout--pass {
  --state: var(--s-pass);
}
.readout--violation {
  --state: var(--s-violation);
}
.readout--na {
  --state: var(--s-na);
}
.readout--not_run {
  --state: var(--s-notrun);
}
.report-binding {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  padding: 10px 16px;
  background: var(--bg-inset);
  border-left: 2px solid var(--accent);
  color: var(--text-secondary);
  font-size: 12px;
  overflow-wrap: anywhere;
}
.report-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 16px;
}
.results-table,
.report-inspector {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-panel);
  overflow: hidden;
}
.results-head,
.report-inspector header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
h2 {
  margin: 0;
  font-size: 14px;
  color: var(--text-primary);
}
.state-filter {
  width: 160px;
}
.table-scroll {
  overflow: auto;
  max-height: 580px;
}
.table-scroll :deep(table) {
  min-width: 680px;
}
.table-scroll :deep(thead) {
  position: sticky;
  top: 0;
  z-index: 1;
}
.selected {
  background: var(--bg-inset);
}
.report-inspector {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 0 16px 16px;
}
.report-inspector header {
  margin-inline: -16px;
}
.report-inspector p {
  margin: 0;
  overflow-wrap: anywhere;
}
.report-inspector dl {
  display: grid;
  gap: 6px;
  font-size: 12px;
}
.report-inspector dt {
  color: var(--text-secondary);
}
.report-inspector dd {
  margin: 0 0 6px;
  overflow-wrap: anywhere;
}
.report-inspector pre {
  padding: 12px;
  max-height: 280px;
  overflow: auto;
  background: var(--bg-inset);
  font-size: 11px;
}
.capability-note {
  color: var(--text-secondary);
  font-size: 12px;
  border-top: 1px solid var(--border);
  padding-top: 12px;
}
.mono {
  font: 12px var(--font-mono, monospace);
  overflow-wrap: anywhere;
}
@media (max-width: 1024px) {
  .report-workspace {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 600px) {
  .report-readouts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .target-field {
    width: 100%;
  }
  .target-field :deep(.ui-select) {
    flex: 1;
    min-width: 0;
  }
}
</style>
