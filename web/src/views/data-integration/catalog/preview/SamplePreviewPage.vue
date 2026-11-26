<script setup lang="ts">
import '../../integration.css'

import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'

import type { DatasourceBrief, MetadataSnapshot, PreviewResponse } from '@/api/datasources'
import { datasourcesApi, metadataApi } from '@/api/datasources'
import PageHeader from '@/components/PageHeader.vue'
import {
  FormField,
  SearchTable,
  UiAlert,
  UiButton,
  UiCard,
  UiEmpty,
  UiSelect,
  UiSpin,
  UiTag,
} from '@/components/ui'
import type { DataTableColumns } from '@/components/ui/tableTypes'
import { usePageIdentity } from '@/layout/navigation/usePageIdentity'
import { useAuthStore } from '@/stores/auth'

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

interface PreviewRow {
  row: Record<string, unknown>
  rowNumber: number
}

const { t, locale } = useI18n()
const route = useRoute()
const auth = useAuthStore()
const canWrite = computed(() => ['ADMIN', 'EDITOR'].includes(auth.user?.role ?? ''))
const datasources = ref<DatasourceBrief[]>([])
const datasourceId = ref<number | null>(null)
const snapshot = ref<MetadataSnapshot | null>(null)
const selectedSchema = ref('')
const selectedTable = ref('')
const limit = ref(20)
const offset = ref(0)
const result = ref<PreviewResponse | null>(null)
const datasourcesLoading = ref(false)
const metadataLoading = ref(false)
const previewLoading = ref(false)
const datasourcesError = ref('')
const metadataError = ref('')
const previewError = ref('')
const previewErrorMessage = computed(() =>
  previewError.value
    ? `${t('dataAccess.preview.previewFailed')} ${t('dataAccess.preview.errorCode', { code: previewError.value })}`
    : '',
)
const noMetadata = ref(false)

let active = true
let metadataRequest = 0
let datasourceController: AbortController | undefined
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
const limitOptions = computed(() =>
  [20, 50, 100].map((value) => ({ label: formatNumber(value), value })),
)
const rowData = computed<PreviewRow[]>(() =>
  (result.value?.rows ?? []).map((row, index) => ({
    row,
    rowNumber: offset.value + index + 1,
  })),
)
const tableColumns = computed<DataTableColumns<PreviewRow>>(() => {
  const columns = (result.value?.columns ?? []).map((column) => ({
    key: `sample-${column.name}`,
    title: () =>
      h('div', { class: 'column-heading' }, [
        h('span', { class: 'mono' }, column.name),
        h('span', { class: 'column-type' }, column.type),
      ]),
    render: (row: PreviewRow) => renderCell(row.row[column.name]),
  }))
  return [
    {
      key: 'rowNumber',
      title: () => t('dataAccess.preview.rowNumber'),
      width: 64,
      render: (row) => h('span', { class: 'row-number mono' }, formatNumber(row.rowNumber)),
    },
    ...columns,
  ]
})
const rangeLabel = computed(() => {
  const count = result.value?.rows.length ?? 0
  if (!count) return t('dataAccess.preview.resultRows', { count: formatNumber(0) })
  return t('dataAccess.preview.rowRange', {
    start: formatNumber(offset.value + 1),
    end: formatNumber(offset.value + count),
    count: formatNumber(count),
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
  if (value === undefined) return h('span', { class: 'null-value' }, t('extractionUi.notRecorded'))
  if (value === null) {
    return h('span', { class: 'null-value' }, t('dataAccess.preview.nullValue'))
  }
  // Sample values retain their round-trip precision; count formatting must not round source data.
  const text = typeof value === 'object' ? JSON.stringify(value) : String(value)
  return h('span', { class: typeof value === 'number' ? 'mono' : undefined, title: text }, text)
}

function formatNumber(value: number) {
  return new Intl.NumberFormat(locale.value).format(value)
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
    const current = await metadataApi.latest(datasourceId.value)
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
  if (!canWrite.value) return
  if (datasourceId.value === null || metadataLoading.value) return
  const requestId = ++metadataRequest
  metadataLoading.value = true
  metadataError.value = ''
  noMetadata.value = false
  snapshot.value = null
  selectedSchema.value = ''
  selectedTable.value = ''
  resetPreview()
  try {
    const current = await metadataApi.capture(datasourceId.value)
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
  datasourceController?.abort()
  const controller = new AbortController()
  datasourceController = controller
  datasourcesLoading.value = true
  datasourcesError.value = ''
  try {
    const sources = await datasourcesApi.list({}, controller.signal)
    if (!active || controller.signal.aborted || datasourceController !== controller) return
    datasources.value = sources
    // 无论带没带 URL 参数，选定数据源后都自动拉元数据：
    // 从菜单进入时也会默认选中第一个数据源，不拉取的话下拉一直是空的。
    const routeId = Number(queryString('datasourceId'))
    datasourceId.value =
      datasources.value.find((item) => item.id === routeId)?.id ?? datasources.value[0]?.id ?? null
    if (datasourceId.value !== null) await loadLatestMetadata()
  } catch (error) {
    if (active && !controller.signal.aborted && datasourceController === controller)
      datasourcesError.value = errorCode(error)
  } finally {
    if (active && !controller.signal.aborted && datasourceController === controller)
      datasourcesLoading.value = false
  }
}

async function runPreview(nextOffset = 0) {
  if (!canPreview.value || datasourceId.value === null || previewLoading.value) return
  if (
    !Number.isInteger(limit.value) ||
    limit.value < 1 ||
    limit.value > 100 ||
    !Number.isInteger(nextOffset) ||
    nextOffset < 0 ||
    nextOffset > 10000
  )
    return
  previewController?.abort()
  const controller = new AbortController()
  previewController = controller
  previewLoading.value = true
  previewError.value = ''
  result.value = null
  offset.value = nextOffset
  try {
    const current = await datasourcesApi.preview(
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

watch(
  selectedSchema,
  (schema) => {
    const schemaTables = schemas.value.find((item) => item.schema === schema)?.tables ?? []
    selectedTable.value = schemaTables.some((table) => table.name === selectedTable.value)
      ? selectedTable.value
      : (schemaTables[0]?.name ?? '')
    resetPreview()
  },
  { flush: 'sync' },
)

watch(selectedTable, resetPreview, { flush: 'sync' })
watch(limit, resetPreview, { flush: 'sync' })

onMounted(loadDatasources)
onBeforeUnmount(() => {
  active = false
  metadataRequest++
  datasourceController?.abort()
  previewController?.abort()
})
usePageIdentity(() => (!metadataLoading.value && snapshot.value ? selectedTable.value : ''))
</script>

<template>
  <section class="integration-page sample-preview-page">
    <PageHeader
      :title="t('dataAccess.preview.title')"
      :description="t('dataAccess.preview.description')"
      ><template #actions
        ><RouterLink
          :to="{
            name: 'data-catalog',
            query: {
              datasourceId,
              schema: selectedSchema,
              table: selectedTable,
              snapshot:
                datasourceId === Number(route.query.datasourceId)
                  ? route.query.snapshot
                  : undefined,
            },
          }"
          >{{ t('page.dataCatalog') }}</RouterLink
        ></template
      ></PageHeader
    >

    <div class="preview-workspace">
      <UiCard size="small" class="selector-card preview-inspector">
        <div class="selection-grid">
          <FormField
            :label="t('dataAccess.preview.datasource')"
            label-for="preview-datasource"
            :show-feedback="false"
          >
            <UiSelect
              v-model:value="datasourceId"
              :options="datasourceOptions"
              :loading="datasourcesLoading"
              :placeholder="t('dataAccess.preview.chooseDatasource')"
              :disabled="datasourcesLoading || datasources.length === 0"
              filterable
            />
          </FormField>
          <FormField
            :label="t('dataAccess.preview.schema')"
            label-for="preview-schema"
            :show-feedback="false"
          >
            <UiSelect
              v-model:value="selectedSchema"
              :options="schemaOptions"
              :placeholder="t('dataAccess.preview.chooseSchema')"
              :disabled="!schemas.length || metadataLoading"
            />
          </FormField>
          <FormField
            :label="t('dataAccess.preview.table')"
            label-for="preview-table"
            :show-feedback="false"
          >
            <UiSelect
              v-model:value="selectedTable"
              :options="tableOptions"
              :placeholder="t('dataAccess.preview.chooseTable')"
              :disabled="!tables.length || metadataLoading"
              filterable
            />
          </FormField>
          <FormField
            class="limit-field"
            :label="t('dataAccess.preview.limit')"
            label-for="preview-limit"
            :show-feedback="false"
          >
            <UiSelect
              v-model:value="limit"
              :options="limitOptions"
              :placeholder="t('dataAccess.preview.limit')"
              :disabled="previewLoading"
            />
          </FormField>
          <div class="actions">
            <UiButton
              :disabled="datasourceId === null || metadataLoading"
              :loading="metadataLoading"
              @click="loadLatestMetadata"
            >
              {{ t('dataAccess.preview.loadLatest') }}
            </UiButton>
            <UiButton
              type="default"
              :disabled="!canWrite || datasourceId === null || metadataLoading"
              :loading="metadataLoading"
              @click="captureMetadata"
            >
              {{ t('dataAccess.preview.captureMetadata') }}
            </UiButton>
            <UiButton
              type="primary"
              :disabled="!canPreview || previewLoading"
              :loading="previewLoading"
              @click="runPreview()"
            >
              {{ t('dataAccess.preview.fetch') }}
            </UiButton>
          </div>
        </div>
        <UiAlert type="warning" :show-icon="true">
          <div class="security-note">
            <strong>{{ t('dataAccess.preview.securityTitle') }}</strong>
            <span>{{ t('dataAccess.preview.securityNote') }}</span>
          </div>
        </UiAlert>
        <UiAlert v-if="route.query.snapshot" type="info">{{ t('ui.livePreviewContext') }}</UiAlert>

        <div class="metadata-caption">
          <span v-if="snapshot">{{
            t('dataAccess.preview.snapshotInfo', {
              revision: formatNumber(snapshot.revision),
              capturedAt,
            })
          }}</span>
          <span v-else>{{ t('dataAccess.preview.metadataHint') }}</span>
          <span>{{ t('dataAccess.preview.limitNote', { limit: formatNumber(100) }) }}</span>
        </div>
      </UiCard>
      <main class="preview-stage">
        <UiAlert v-if="datasourcesError" type="error" :title="t('dataAccess.preview.loadFailed')">
          {{ t('dataAccess.preview.errorCode', { code: datasourcesError }) }}
          <UiButton @click="loadDatasources">{{ t('ui.retry') }}</UiButton>
        </UiAlert>
        <UiAlert v-if="metadataError" type="error" :title="t('dataAccess.preview.loadFailed')">
          {{ t('dataAccess.preview.errorCode', { code: metadataError }) }}
          <UiButton @click="loadLatestMetadata">{{ t('ui.retry') }}</UiButton>
        </UiAlert>
        <UiSpin
          v-if="datasourcesLoading || metadataLoading"
          show
          :description="
            t(
              datasourcesLoading
                ? 'dataAccess.catalog.states.loadingSources'
                : 'dataAccess.catalog.states.loadingMetadata',
            )
          "
          class="preview-loading"
        />

        <UiCard v-else-if="noMetadata" size="small">
          <UiEmpty :description="t('dataAccess.preview.noMetadata')" />
        </UiCard>
        <UiCard
          v-else-if="datasources.length === 0 && !datasourcesLoading && !datasourcesError"
          size="small"
        >
          <UiEmpty :description="t('dataAccess.preview.noDatasources')" />
        </UiCard>
        <UiCard v-else-if="snapshot && (!schemas.length || !tables.length)" size="small">
          <UiEmpty :description="t('dataAccess.preview.noTables')" />
        </UiCard>

        <UiCard v-if="result || previewLoading || previewError" size="small" class="result-card">
          <template #header>
            <div class="result-header">
              <div class="result-title">
                <h2>{{ t('dataAccess.preview.resultTitle') }}</h2>
                <span v-if="result" class="result-range">{{ rangeLabel }}</span>
                <UiTag v-if="result?.truncated" type="warning" size="small">
                  {{ t('dataAccess.preview.truncated') }}
                </UiTag>
              </div>
              <span v-if="result" class="readonly-label">{{
                t('dataAccess.preview.readOnly')
              }}</span>
            </div>
          </template>
          <SearchTable
            :columns="tableColumns"
            :rows="rowData"
            row-key="rowNumber"
            mode="none"
            :searchable="false"
            :initialized="result !== null"
            :loading="previewLoading"
            :error="previewErrorMessage"
            :empty-text="t('dataAccess.preview.emptyResult')"
            :label="t('dataAccess.preview.resultTitle')"
            :scroll-x="Math.max(700, tableColumns.length * 180)"
            size="small"
            :bordered="false"
            @retry="runPreview(offset)"
          >
            <template #toolbar><span /></template>
          </SearchTable>
          <div v-if="result" class="result-footer">
            <span>{{ rangeLabel }}</span>
            <div class="paging-actions">
              <UiButton
                quaternary
                size="small"
                :disabled="previewLoading || offset === 0"
                @click="runPreview(Math.max(0, offset - limit))"
              >
                {{ t('dataAccess.preview.previous') }}
              </UiButton>
              <UiButton
                quaternary
                size="small"
                :disabled="previewLoading || !result.truncated || offset + limit > 10000"
                @click="runPreview(offset + limit)"
              >
                {{ t('dataAccess.preview.next') }}
              </UiButton>
            </div>
          </div>
        </UiCard>
        <section
          v-if="
            !result &&
            !previewLoading &&
            snapshot &&
            tables.length &&
            !previewError &&
            !metadataError &&
            !datasourcesError &&
            !metadataLoading &&
            !datasourcesLoading
          "
          class="integration-empty-stage"
        >
          <h2>{{ t('dataAccess.preview.resultTitle') }}</h2>
          <p>{{ t('dataAccess.preview.metadataHint') }}</p>
          <UiButton type="primary" :disabled="!canPreview" @click="runPreview()">{{
            t('dataAccess.preview.fetch')
          }}</UiButton>
        </section>
      </main>
    </div>
  </section>
</template>

<style scoped>
.sample-preview-page {
  display: grid;
  gap: var(--space-4);
  min-width: 0;
}

.result-title h2 {
  margin: 0;
  color: var(--foreground-primary);
  font-weight: 500;
}

.security-note {
  display: grid;
  gap: calc(var(--space-1) / 2);
}

.security-note strong {
  font-weight: 500;
}

.selection-grid {
  display: grid;

  grid-template-columns: minmax(0, 1fr);
  align-items: end;
  gap: var(--space-3);
}

.actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--space-2);
}

.metadata-caption {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: var(--space-2) var(--space-4);
  margin-top: var(--space-3);
  color: var(--foreground-muted);
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
  gap: var(--space-3);
}

.result-title {
  flex-wrap: wrap;
  gap: var(--space-3);
}

.result-title h2 {
  font-size: var(--font-h3);
}

.result-range,
.readonly-label {
  color: var(--foreground-muted);
  font-size: var(--font-caption);
}

.result-footer {
  justify-content: space-between;
  gap: var(--space-3);
  padding-top: var(--space-3);
  margin-top: var(--space-2);
  border-top: 1px solid var(--border-muted);
  color: var(--foreground-muted);
  font-size: var(--font-caption);
}

.paging-actions {
  gap: var(--space-1);
}

.column-heading {
  display: grid;
  gap: calc(var(--space-1) / 2);
  min-width: 80px;
}

.column-type {
  color: var(--graph-entity);
  font-family: var(--font-mono);
  font-size: var(--font-caption);
  font-weight: 400;
}

.row-number {
  color: var(--foreground-disabled);
}

.null-value {
  color: var(--foreground-muted);
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

  .actions :deep(.ui-button) {
    flex: 1 1 auto;
  }

  .result-header,
  .result-footer {
    align-items: flex-start;
    flex-direction: column;
  }
}
.preview-loading {
  min-height: calc(var(--space-6) * 3);
}
</style>
