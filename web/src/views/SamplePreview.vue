<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import { NAlert, NButton, NCard, NDataTable, NEmpty, NSelect, NSpin, NTag } from 'naive-ui'
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import type {
  Datasource,
  MetadataSnapshot,
  PreviewResult,
} from '@/views/datasources/samplePreviewApi'
import { samplePreviewApi } from '@/views/datasources/samplePreviewApi'

interface CatalogColumn {
  name: string
  type: string
}

interface CatalogTable {
  name: string
  type: string
  columns: CatalogColumn[]
}

interface CatalogSchema {
  schema: string
  tables: CatalogTable[]
}

interface PreviewRow extends Record<string, unknown> {
  __rowNumber: number
}

const { t, locale } = useI18n()
const route = useRoute()
const datasources = ref<Datasource[]>([])
const datasourceId = ref<number | null>(null)
const snapshot = ref<MetadataSnapshot | null>(null)
const selectedSchema = ref('')
const selectedTable = ref('')
const limit = ref(20)
const offset = ref(0)
const result = ref<PreviewResult | null>(null)
const datasourcesLoading = ref(false)
const metadataLoading = ref(false)
const previewLoading = ref(false)
const datasourcesError = ref('')
const metadataError = ref('')
const previewError = ref('')
const noMetadata = ref(false)

let active = true
let metadataRequest = 0
let previewController: AbortController | undefined

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function readCatalogSchemas(catalog: Record<string, unknown> | undefined): CatalogSchema[] {
  const schemas = catalog?.schemas
  if (!Array.isArray(schemas)) return []

  return schemas.flatMap((schema): CatalogSchema[] => {
    if (!isRecord(schema) || typeof schema.schema !== 'string' || !Array.isArray(schema.tables)) {
      return []
    }
    const tables = schema.tables.flatMap((table): CatalogTable[] => {
      if (!isRecord(table) || typeof table.name !== 'string' || !Array.isArray(table.columns)) {
        return []
      }
      const columns = table.columns.flatMap((column): CatalogColumn[] =>
        isRecord(column) && typeof column.name === 'string'
          ? [{ name: column.name, type: typeof column.type === 'string' ? column.type : 'unknown' }]
          : [],
      )
      return [
        { name: table.name, type: typeof table.type === 'string' ? table.type : 'table', columns },
      ]
    })
    return [{ schema: schema.schema, tables }]
  })
}

const schemas = computed(() => readCatalogSchemas(snapshot.value?.catalog))
const tables = computed(
  () => schemas.value.find((schema) => schema.schema === selectedSchema.value)?.tables ?? [],
)
const schemaOptions = computed(() =>
  schemas.value.map((schema) => ({ label: schema.schema, value: schema.schema })),
)
const tableOptions = computed(() =>
  tables.value.map((table) => ({
    label: table.name,
    value: table.name,
    type: table.type,
  })),
)
const datasourceOptions = computed(() =>
  datasources.value.map((source) => ({
    label: source.name,
    value: source.id,
    type: source.kind,
  })),
)
const rowData = computed<PreviewRow[]>(() =>
  (result.value?.rows ?? []).map((row, index) => ({
    ...row,
    __rowNumber: offset.value + index + 1,
  })),
)
const tableColumns = computed<DataTableColumns<PreviewRow>>(() => {
  const columns = (result.value?.columns ?? []).map((column) => ({
    key: column.name,
    title: () =>
      h('div', { class: 'column-heading' }, [
        h('span', { class: 'mono' }, column.name),
        h('span', { class: 'column-type' }, column.type),
      ]),
    render: (row: PreviewRow) => renderCell(row[column.name]),
  }))
  return [
    {
      key: '__rowNumber',
      title: '#',
      width: 64,
      render: (row) => h('span', { class: 'row-number mono' }, String(row.__rowNumber)),
    },
    ...columns,
  ]
})
const rangeLabel = computed(() => {
  const count = result.value?.rows.length ?? 0
  if (!count) return t('dataAccess.preview.resultRows', { count: 0 })
  return t('dataAccess.preview.rowRange', {
    start: offset.value + 1,
    end: offset.value + count,
    count,
  })
})
const capturedAt = computed(() => {
  if (!snapshot.value) return ''
  const date = new Date(snapshot.value.captured_at)
  return Number.isNaN(date.getTime())
    ? snapshot.value.captured_at
    : new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(
        date,
      )
})
const canPreview = computed(
  () => datasourceId.value !== null && !!selectedSchema.value && !!selectedTable.value,
)

function renderCell(value: unknown) {
  if (value === null || value === undefined) {
    return h('span', { class: 'null-value' }, t('dataAccess.preview.nullValue'))
  }
  const text = typeof value === 'object' ? JSON.stringify(value) : String(value)
  return h('span', { class: typeof value === 'number' ? 'mono' : undefined, title: text }, text)
}

function errorCode(error: unknown): string {
  if (isRecord(error) && typeof error.code === 'string') return error.code
  return 'NETWORK_ERROR'
}

function isNoSnapshot(error: unknown): boolean {
  return (
    isRecord(error) &&
    error.code === 'KG.RESOURCE_NOT_FOUND' &&
    isRecord(error.params) &&
    error.params.reason === 'no_snapshot'
  )
}

function resetPreview() {
  previewController?.abort()
  previewLoading.value = false
  result.value = null
  previewError.value = ''
  offset.value = 0
}

function chooseInitialTable(preferredSchema = '', preferredTable = '') {
  const schema = schemas.value.find((item) => item.schema === preferredSchema) ?? schemas.value[0]
  selectedSchema.value = schema?.schema ?? ''
  const table = schema?.tables.find((item) => item.name === preferredTable) ?? schema?.tables[0]
  selectedTable.value = table?.name ?? ''
}

async function loadLatestMetadata() {
  if (datasourceId.value === null) return
  const requestId = ++metadataRequest
  metadataLoading.value = true
  metadataError.value = ''
  noMetadata.value = false
  snapshot.value = null
  selectedSchema.value = ''
  selectedTable.value = ''
  resetPreview()
  try {
    const current = await samplePreviewApi.latestMetadata(datasourceId.value)
    if (!active || requestId !== metadataRequest) return
    snapshot.value = current
    chooseInitialTable(queryString('schema'), queryString('table'))
  } catch (error) {
    if (!active || requestId !== metadataRequest) return
    if (isNoSnapshot(error)) noMetadata.value = true
    else metadataError.value = errorCode(error)
  } finally {
    if (active && requestId === metadataRequest) metadataLoading.value = false
  }
}

async function captureMetadata() {
  if (datasourceId.value === null) return
  const requestId = ++metadataRequest
  metadataLoading.value = true
  metadataError.value = ''
  noMetadata.value = false
  snapshot.value = null
  selectedSchema.value = ''
  selectedTable.value = ''
  resetPreview()
  try {
    const current = await samplePreviewApi.captureMetadata(datasourceId.value)
    if (!active || requestId !== metadataRequest) return
    snapshot.value = current
    chooseInitialTable(queryString('schema'), queryString('table'))
  } catch (error) {
    if (active && requestId === metadataRequest) metadataError.value = errorCode(error)
  } finally {
    if (active && requestId === metadataRequest) metadataLoading.value = false
  }
}

function queryString(key: string): string {
  const value = route.query[key]
  return typeof value === 'string' ? value : ''
}

async function loadDatasources() {
  datasourcesLoading.value = true
  datasourcesError.value = ''
  try {
    const sources = await samplePreviewApi.listDatasources()
    if (!active) return
    datasources.value = sources
    const routeId = Number(queryString('datasourceId'))
    datasourceId.value =
      datasources.value.find((item) => item.id === routeId)?.id ?? datasources.value[0]?.id ?? null
    if (queryString('datasourceId') && datasourceId.value !== null) await loadLatestMetadata()
  } catch (error) {
    if (active) datasourcesError.value = errorCode(error)
  } finally {
    if (active) datasourcesLoading.value = false
  }
}

async function runPreview(nextOffset = 0) {
  if (!canPreview.value || datasourceId.value === null || previewLoading.value) return
  previewController?.abort()
  const controller = new AbortController()
  previewController = controller
  previewLoading.value = true
  previewError.value = ''
  result.value = null
  offset.value = nextOffset
  try {
    const current = await samplePreviewApi.preview(
      {
        datasource_id: datasourceId.value,
        schema: selectedSchema.value,
        table: selectedTable.value,
        limit: limit.value,
        offset: nextOffset,
      },
      controller.signal,
    )
    if (active && !controller.signal.aborted) result.value = current
  } catch (error) {
    if (active && !controller.signal.aborted) previewError.value = errorCode(error)
  } finally {
    if (active && !controller.signal.aborted) previewLoading.value = false
  }
}

watch(
  datasourceId,
  () => {
    metadataRequest++
    snapshot.value = null
    selectedSchema.value = ''
    selectedTable.value = ''
    metadataError.value = ''
    noMetadata.value = false
    metadataLoading.value = false
    resetPreview()
  },
  { flush: 'sync' },
)

watch(selectedSchema, (schema) => {
  const schemaTables = schemas.value.find((item) => item.schema === schema)?.tables ?? []
  selectedTable.value = schemaTables.some((table) => table.name === selectedTable.value)
    ? selectedTable.value
    : (schemaTables[0]?.name ?? '')
  resetPreview()
})

watch(selectedTable, resetPreview)
watch(limit, resetPreview)

onMounted(loadDatasources)
onBeforeUnmount(() => {
  active = false
  metadataRequest++
  previewController?.abort()
})
</script>

<template>
  <section class="sample-preview-page">
    <header class="page-heading">
      <div>
        <h1>{{ t('dataAccess.preview.title') }}</h1>
        <p>{{ t('dataAccess.preview.description') }}</p>
      </div>
    </header>

    <NAlert type="warning" :show-icon="true">
      <div class="security-note">
        <strong>{{ t('dataAccess.preview.securityTitle') }}</strong>
        <span>{{ t('dataAccess.preview.securityNote') }}</span>
      </div>
    </NAlert>

    <NCard size="small" class="selector-card">
      <div class="selection-grid">
        <label class="field">
          <span>{{ t('dataAccess.preview.datasource') }}</span>
          <NSelect
            v-model:value="datasourceId"
            :options="datasourceOptions"
            :loading="datasourcesLoading"
            :placeholder="t('dataAccess.preview.chooseDatasource')"
            :disabled="datasourcesLoading || datasources.length === 0"
            filterable
          />
        </label>
        <label class="field">
          <span>{{ t('dataAccess.preview.schema') }}</span>
          <NSelect
            v-model:value="selectedSchema"
            :options="schemaOptions"
            :placeholder="t('dataAccess.preview.chooseSchema')"
            :disabled="!schemas.length || metadataLoading"
          />
        </label>
        <label class="field">
          <span>{{ t('dataAccess.preview.table') }}</span>
          <NSelect
            v-model:value="selectedTable"
            :options="tableOptions"
            :placeholder="t('dataAccess.preview.chooseTable')"
            :disabled="!tables.length || metadataLoading"
            filterable
          />
        </label>
        <label class="field limit-field">
          <span>{{ t('dataAccess.preview.limit') }}</span>
          <NSelect
            v-model:value="limit"
            :options="[
              { label: '20', value: 20 },
              { label: '50', value: 50 },
              { label: '100', value: 100 },
            ]"
            :disabled="previewLoading"
          />
        </label>
        <div class="actions">
          <NButton
            :disabled="datasourceId === null || metadataLoading"
            :loading="metadataLoading"
            @click="loadLatestMetadata"
          >
            {{ t('dataAccess.preview.loadLatest') }}
          </NButton>
          <NButton
            type="default"
            :disabled="datasourceId === null || metadataLoading"
            :loading="metadataLoading"
            @click="captureMetadata"
          >
            {{ t('dataAccess.preview.captureMetadata') }}
          </NButton>
          <NButton
            type="primary"
            :disabled="!canPreview || previewLoading"
            :loading="previewLoading"
            @click="runPreview()"
          >
            {{ t('dataAccess.preview.fetch') }}
          </NButton>
        </div>
      </div>
      <div class="metadata-caption">
        <span v-if="snapshot">{{
          t('dataAccess.preview.snapshotInfo', { revision: snapshot.revision, capturedAt })
        }}</span>
        <span v-else>{{ t('dataAccess.preview.metadataHint') }}</span>
        <span>{{ t('dataAccess.preview.limitNote', { limit: 100 }) }}</span>
      </div>
    </NCard>

    <NAlert v-if="datasourcesError" type="error" :title="t('dataAccess.preview.loadFailed')">
      {{ t('dataAccess.preview.errorCode', { code: datasourcesError }) }}
    </NAlert>
    <NAlert v-if="metadataError" type="error" :title="t('dataAccess.preview.loadFailed')">
      {{ t('dataAccess.preview.errorCode', { code: metadataError }) }}
    </NAlert>
    <NAlert v-if="previewError" type="error" :title="t('dataAccess.preview.previewFailed')">
      {{ t('dataAccess.preview.errorCode', { code: previewError }) }}
    </NAlert>

    <NCard v-if="noMetadata" size="small">
      <NEmpty :description="t('dataAccess.preview.noMetadata')" />
    </NCard>
    <NCard
      v-else-if="datasources.length === 0 && !datasourcesLoading && !datasourcesError"
      size="small"
    >
      <NEmpty :description="t('dataAccess.preview.noDatasources')" />
    </NCard>
    <NCard v-else-if="snapshot && !schemas.length" size="small">
      <NEmpty :description="t('dataAccess.preview.noTables')" />
    </NCard>

    <NCard v-if="result || previewLoading" size="small" class="result-card">
      <template #header>
        <div class="result-header">
          <div class="result-title">
            <h2>{{ t('dataAccess.preview.resultTitle') }}</h2>
            <span v-if="result" class="result-range">{{ rangeLabel }}</span>
            <NTag v-if="result?.truncated" type="warning" size="small">
              {{ t('dataAccess.preview.truncated') }}
            </NTag>
          </div>
          <span v-if="result" class="readonly-label">{{ t('dataAccess.preview.readOnly') }}</span>
        </div>
      </template>
      <NSpin :show="previewLoading">
        <NDataTable
          v-if="result?.rows.length"
          :columns="tableColumns"
          :data="rowData"
          :row-key="(row: PreviewRow) => row.__rowNumber"
          :scroll-x="Math.max(700, tableColumns.length * 180)"
          size="small"
          :bordered="false"
        />
        <NEmpty v-else-if="result" :description="t('dataAccess.preview.emptyResult')" />
        <div v-if="result" class="result-footer">
          <span>{{ rangeLabel }}</span>
          <div class="paging-actions">
            <NButton
              quaternary
              size="small"
              :disabled="previewLoading || offset === 0"
              @click="runPreview(Math.max(0, offset - limit))"
            >
              {{ t('dataAccess.preview.previous') }}
            </NButton>
            <NButton
              quaternary
              size="small"
              :disabled="previewLoading || !result.truncated || offset + limit > 10000"
              @click="runPreview(offset + limit)"
            >
              {{ t('dataAccess.preview.next') }}
            </NButton>
          </div>
        </div>
      </NSpin>
    </NCard>
  </section>
</template>

<style scoped>
.sample-preview-page {
  display: grid;
  gap: 16px;
  min-width: 0;
}

.page-heading h1,
.result-title h2 {
  margin: 0;
  color: var(--text);
  font-weight: 500;
}

.page-heading h1 {
  font-size: var(--font-h1);
}

.page-heading p {
  margin: 5px 0 0;
  color: var(--text-secondary);
}

.security-note {
  display: grid;
  gap: 2px;
}

.security-note strong {
  font-weight: 500;
}

.selection-grid {
  display: grid;
  grid-template-columns: minmax(180px, 1.1fr) minmax(140px, 0.8fr) minmax(180px, 1fr) 100px auto;
  align-items: end;
  gap: 12px;
}

.field {
  display: grid;
  gap: 6px;
  min-width: 0;
  color: var(--text-secondary);
  font-size: var(--font-caption);
}

.actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.metadata-caption {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 6px 16px;
  margin-top: 12px;
  color: var(--text-tertiary);
  font-size: var(--font-caption);
}

.result-card {
  min-width: 0;
  overflow: hidden;
}

.result-header,
.result-title,
.result-footer,
.paging-actions {
  display: flex;
  align-items: center;
}

.result-header {
  justify-content: space-between;
  gap: 12px;
}

.result-title {
  flex-wrap: wrap;
  gap: 10px;
}

.result-title h2 {
  font-size: var(--font-h3);
}

.result-range,
.readonly-label {
  color: var(--text-tertiary);
  font-size: var(--font-caption);
}

.result-footer {
  justify-content: space-between;
  gap: 12px;
  padding-top: 10px;
  margin-top: 8px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-tertiary);
  font-size: var(--font-caption);
}

.paging-actions {
  gap: 4px;
}

.column-heading {
  display: grid;
  gap: 2px;
  min-width: 80px;
}

.column-type {
  color: var(--cyan);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 400;
}

.row-number {
  color: var(--text-disabled);
}

.null-value {
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  font-style: italic;
}

.mono {
  font-family: var(--font-mono);
}

@media (max-width: 1100px) {
  .selection-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .actions {
    grid-column: 1 / -1;
    justify-content: flex-start;
  }
}

@media (max-width: 600px) {
  .selection-grid {
    grid-template-columns: 1fr;
  }

  .actions {
    grid-column: auto;
  }

  .actions :deep(.n-button) {
    flex: 1 1 auto;
  }

  .result-header,
  .result-footer {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
