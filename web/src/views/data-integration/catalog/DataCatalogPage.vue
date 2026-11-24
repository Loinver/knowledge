<script setup lang="ts">
import '../integration.css'

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import type {
  DatasourceBrief,
  MetadataSnapshotBrief,
  MetadataSnapshotOut,
  TableReferenceResponse,
} from '@/api/datasources'
import { datasourcesApi, metadataApi } from '@/api/datasources'
import PageHeader from '@/components/PageHeader.vue'
import {
  FormField,
  SearchTable,
  UiAlert,
  UiButton,
  UiEmpty,
  UiSelect,
  UiSpin,
} from '@/components/ui'
import type { DataTableColumns } from '@/components/ui/tableTypes'
import { useApiError } from '@/composables/useApiError'
import { usePageIdentity } from '@/layout/navigation/usePageIdentity'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const canWrite = computed(() => ['ADMIN', 'EDITOR'].includes(auth.user?.role ?? ''))

type DiffKind = 'added' | 'removed' | 'modified'

interface CatalogColumn {
  name: string
  type: string
  nullable: boolean
  primary_key: boolean
  foreign_key: string | null
}

interface CatalogTable {
  name: string
  type: string
  columns: CatalogColumn[]
  diff?: DiffKind
}

interface CatalogSchema {
  name: string
  tables: CatalogTable[]
}

interface ColumnDiff {
  schema: string
  table: string
  column: string
  type: DiffKind
  details?: string
}

interface TableDiff {
  schema: string
  name: string
  type: DiffKind
}

interface CatalogDiff {
  tables: TableDiff[]
  columns: ColumnDiff[]
  summary: Record<string, number>
}

interface CatalogData {
  schemas: CatalogSchema[]
  table_count: number
  column_count: number
}

const { t, locale } = useI18n()
const { toMessage } = useApiError()
const route = useRoute()
const router = useRouter()
const datasources = ref<DatasourceBrief[]>([])
const datasourceId = ref<number | null>(null)
const snapshots = ref<MetadataSnapshotBrief[]>([])
const snapshotId = ref<number | null>(null)
const snapshot = ref<MetadataSnapshotOut | null>(null)
const catalog = ref<CatalogData>({ schemas: [], table_count: 0, column_count: 0 })
const diff = ref<CatalogDiff>({ tables: [], columns: [], summary: {} })
const selectedSchema = ref('')
const selectedTable = ref('')
const selectedColumn = ref('')
const expandedSchemas = ref(new Set<string>())
const references = ref<TableReferenceResponse | null>(null)
const loadingDatasources = ref(true)
const loadingCatalog = ref(false)
const capturing = ref(false)
const loadingReferences = ref(false)
const datasourceError = ref('')
const catalogError = ref('')
const referencesError = ref('')
const hasSnapshot = ref(false)

let catalogGeneration = 0
let referenceGeneration = 0
let datasourceController: AbortController | undefined
let referenceController: AbortController | undefined
let alive = true

const tableDiffs = computed(() => diff.value.tables)

const schemas = computed<CatalogSchema[]>(() => {
  const values = catalog.value.schemas.map((schema) => {
    const tables = schema.tables.map((table) => ({
      ...table,
      diff: tableDiffs.value.find((item) => item.schema === schema.name && item.name === table.name)
        ?.type,
    }))
    for (const item of tableDiffs.value) {
      if (
        item.schema === schema.name &&
        item.type === 'removed' &&
        !tables.some((table) => table.name === item.name)
      ) {
        tables.push({ name: item.name, type: 'table', columns: [], diff: 'removed' })
      }
    }
    return { ...schema, tables }
  })

  for (const item of tableDiffs.value) {
    if (item.type !== 'removed') continue
    const schema = values.find((schema) => schema.name === item.schema)
    if (!schema)
      values.push({
        name: item.schema,
        tables: [{ name: item.name, type: 'table', columns: [], diff: 'removed' }],
      })
    else if (!schema.tables.some((table) => table.name === item.name))
      schema.tables.push({ name: item.name, type: 'table', columns: [], diff: 'removed' })
  }
  return values
})

const activeSchema = computed(
  () => schemas.value.find((schema) => schema.name === selectedSchema.value) ?? null,
)

const activeTable = computed(
  () => activeSchema.value?.tables.find((table) => table.name === selectedTable.value) ?? null,
)

const visibleColumns = computed(() => {
  const table = activeTable.value
  if (!table) return []
  const current = table.columns.map((column) => ({
    ...column,
    diff: diff.value.columns.find(
      (item) =>
        item.schema === selectedSchema.value &&
        item.table === table.name &&
        item.column === column.name,
    ),
  }))
  for (const item of diff.value.columns) {
    if (
      item.schema === selectedSchema.value &&
      item.table === table.name &&
      item.type === 'removed' &&
      !current.some((column) => column.name === item.column)
    ) {
      current.push({
        name: item.column,
        type: '',
        nullable: false,
        primary_key: false,
        foreign_key: null,
        diff: item,
      })
    }
  }
  return current
})

const activeColumn = computed(
  () => visibleColumns.value.find((column) => column.name === selectedColumn.value) ?? null,
)

const summaryItems = computed(() => [
  { key: 'tables_added', label: 'tablesAdded', type: 'added' as const },
  { key: 'tables_removed', label: 'tablesRemoved', type: 'removed' as const },
  { key: 'columns_added', label: 'columnsAdded', type: 'added' as const },
  { key: 'columns_removed', label: 'columnsRemoved', type: 'removed' as const },
  { key: 'columns_modified', label: 'columnsModified', type: 'modified' as const },
])

const datasourceOptions = computed(() =>
  datasources.value.map((item) => ({ value: item.id, label: item.name })),
)
const snapshotOptions = computed(() =>
  snapshots.value.map((item) => ({
    value: item.id,
    label: `${t('dataAccess.catalog.snapshotRevision', { revision: formatNumber(item.revision) })} · ${formatDate(item.captured_at)}`,
  })),
)
type VisibleColumn = (typeof visibleColumns.value)[number]
const columnDefinitions = computed<DataTableColumns<VisibleColumn>>(() =>
  ['name', 'type', 'nullable', 'key', 'foreignKey', 'change'].map((key) => ({
    key,
    title: t(`dataAccess.catalog.columns.${key}`),
  })),
)

function formatNumber(value: number) {
  return new Intl.NumberFormat(locale.value).format(value)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseCatalog(value: Record<string, unknown>): CatalogData {
  const schemaValues = Array.isArray(value.schemas) ? value.schemas : []
  const parsedSchemas = schemaValues.flatMap((schemaValue) => {
    if (!isRecord(schemaValue) || typeof schemaValue.schema !== 'string') return []
    const tableValues = Array.isArray(schemaValue.tables) ? schemaValue.tables : []
    const parsedTables = tableValues.flatMap((tableValue) => {
      if (!isRecord(tableValue) || typeof tableValue.name !== 'string') return []
      const columnValues = Array.isArray(tableValue.columns) ? tableValue.columns : []
      const parsedColumns = columnValues.flatMap((columnValue) => {
        if (!isRecord(columnValue) || typeof columnValue.name !== 'string') return []
        return [
          {
            name: columnValue.name,
            type: typeof columnValue.type === 'string' ? columnValue.type : '',
            nullable: columnValue.nullable === true,
            primary_key: columnValue.primary_key === true,
            foreign_key:
              typeof columnValue.foreign_key === 'string' ? columnValue.foreign_key : null,
          },
        ]
      })
      return [
        {
          name: tableValue.name,
          type: typeof tableValue.type === 'string' ? tableValue.type : 'table',
          columns: parsedColumns,
        },
      ]
    })
    return [{ name: schemaValue.schema, tables: parsedTables }]
  })
  const columnCount = parsedSchemas.reduce(
    (count, schema) =>
      count + schema.tables.reduce((subtotal, table) => subtotal + table.columns.length, 0),
    0,
  )
  return {
    schemas: parsedSchemas,
    table_count: typeof value.table_count === 'number' ? value.table_count : 0,
    column_count: typeof value.column_count === 'number' ? value.column_count : columnCount,
  }
}

function parseDiff(value: Record<string, unknown> | null): CatalogDiff {
  if (!value) return { tables: [], columns: [], summary: {} }
  const tables = Array.isArray(value.tables)
    ? value.tables.flatMap((entry) => {
        if (!isRecord(entry) || typeof entry.name !== 'string') return []
        if (!isDiffKind(entry.type)) return []
        return [
          {
            schema: typeof entry.schema === 'string' ? entry.schema : 'main',
            name: entry.name,
            type: entry.type,
          },
        ]
      })
    : []
  const columns = Array.isArray(value.columns)
    ? value.columns.flatMap((entry) => {
        if (
          !isRecord(entry) ||
          typeof entry.table !== 'string' ||
          typeof entry.column !== 'string' ||
          !isDiffKind(entry.type)
        ) {
          return []
        }
        return [
          {
            schema: typeof entry.schema === 'string' ? entry.schema : 'main',
            table: entry.table,
            column: entry.column,
            type: entry.type,
            ...(typeof entry.details === 'string' ? { details: entry.details } : {}),
          },
        ]
      })
    : []
  const summary = isRecord(value.summary)
    ? Object.fromEntries(
        Object.entries(value.summary).filter(
          (entry): entry is [string, number] => typeof entry[1] === 'number',
        ),
      )
    : {}
  return { tables, columns, summary }
}

function isDiffKind(value: unknown): value is DiffKind {
  return value === 'added' || value === 'removed' || value === 'modified'
}

function asError(err: unknown) {
  return err as { code?: string; params?: Record<string, unknown> } | null
}

function noSnapshotError(err: unknown) {
  const error = asError(err)
  return error?.code === 'KG.RESOURCE_NOT_FOUND' && error.params?.reason === 'no_snapshot'
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(locale.value, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function diffLabel(kind: DiffKind) {
  return t(`dataAccess.catalog.diff.${kind}`)
}

function selectInitialTable() {
  const querySchema = typeof route.query.schema === 'string' ? route.query.schema : ''
  const queryTable = typeof route.query.table === 'string' ? route.query.table : ''
  const schema = schemas.value.find((item) => item.name === querySchema) ?? schemas.value[0]
  if (!schema) {
    selectedSchema.value = ''
    selectedTable.value = ''
    return
  }
  selectedSchema.value = schema.name
  const table = schema.tables.find((item) => item.name === queryTable) ?? schema.tables[0]
  selectedTable.value = table?.name ?? ''
  selectedColumn.value = ''
  expandedSchemas.value = new Set([schema.name])
  if (table) void loadReferences(table.name)
}

async function loadReferences(tableName: string) {
  const generation = ++referenceGeneration
  referenceController?.abort()
  referenceController = new AbortController()
  references.value = null
  referencesError.value = ''
  loadingReferences.value = true
  try {
    const result = await metadataApi.references(tableName, referenceController.signal)
    if (alive && generation === referenceGeneration) references.value = result
  } catch (err) {
    if (alive && generation === referenceGeneration) referencesError.value = toMessage(err)
  } finally {
    if (alive && generation === referenceGeneration) loadingReferences.value = false
  }
}

function chooseTable(schemaName: string, tableName: string) {
  selectedSchema.value = schemaName
  selectedTable.value = tableName
  selectedColumn.value = ''
  expandedSchemas.value = new Set([...expandedSchemas.value, schemaName])
  void loadReferences(tableName)
  void router.replace({
    query: {
      ...route.query,
      datasourceId: datasourceId.value,
      schema: schemaName,
      table: tableName,
    },
  })
}

function toggleSchema(schemaName: string) {
  const expanded = new Set(expandedSchemas.value)
  if (expanded.has(schemaName)) expanded.delete(schemaName)
  else expanded.add(schemaName)
  expandedSchemas.value = expanded
}

function selectSnapshot() {
  const id = snapshotId.value
  if (id === null || id === snapshot.value?.id) return
  void loadSnapshot(id)
}

async function loadSnapshot(id: number) {
  const generation = ++catalogGeneration
  referenceGeneration++
  referenceController?.abort()
  loadingReferences.value = false
  capturing.value = false
  loadingCatalog.value = true
  catalogError.value = ''
  hasSnapshot.value = false
  snapshot.value = null
  catalog.value = { schemas: [], table_count: 0, column_count: 0 }
  diff.value = { tables: [], columns: [], summary: {} }
  references.value = null
  referencesError.value = ''
  selectedSchema.value = ''
  selectedTable.value = ''
  selectedColumn.value = ''
  try {
    const result = await metadataApi.get(id)
    if (!alive || generation !== catalogGeneration) return
    snapshot.value = result
    hasSnapshot.value = true
    catalog.value = parseCatalog(result.catalog)
    diff.value = parseDiff(result.diff)
    selectInitialTable()
  } catch (err) {
    if (alive && generation === catalogGeneration) catalogError.value = toMessage(err)
  } finally {
    if (alive && generation === catalogGeneration) loadingCatalog.value = false
  }
}

async function loadDatasourceCatalog(id: number) {
  const generation = ++catalogGeneration
  referenceGeneration++
  referenceController?.abort()
  loadingReferences.value = false
  capturing.value = false
  loadingCatalog.value = true
  catalogError.value = ''
  referencesError.value = ''
  references.value = null
  snapshots.value = []
  snapshotId.value = null
  snapshot.value = null
  hasSnapshot.value = false
  catalog.value = { schemas: [], table_count: 0, column_count: 0 }
  diff.value = { tables: [], columns: [], summary: {} }
  selectedSchema.value = ''
  selectedTable.value = ''
  selectedColumn.value = ''
  try {
    const [snapshotItems, latestResult] = await Promise.all([
      metadataApi.snapshots(id),
      metadataApi.latest(id).catch((err: unknown) => {
        if (noSnapshotError(err)) return null
        throw err
      }),
    ])
    if (!alive || generation !== catalogGeneration) return
    snapshots.value = snapshotItems
    const requestedSnapshot = Number(route.query.snapshot)
    if (
      snapshotItems.some((item) => item.id === requestedSnapshot) &&
      requestedSnapshot !== latestResult?.id
    ) {
      const result = await metadataApi.get(requestedSnapshot)
      if (!alive || generation !== catalogGeneration) return
      snapshot.value = result
      snapshotId.value = result.id
      hasSnapshot.value = true
      catalog.value = parseCatalog(result.catalog)
      diff.value = parseDiff(result.diff)
      selectInitialTable()
      return
    }
    if (!latestResult) {
      snapshotId.value = snapshotItems[0]?.id ?? null
      if (snapshotItems[0]) {
        const result = await metadataApi.get(snapshotItems[0].id)
        if (!alive || generation !== catalogGeneration) return
        snapshot.value = result
        snapshotId.value = result.id
        hasSnapshot.value = true
        catalog.value = parseCatalog(result.catalog)
        diff.value = parseDiff(result.diff)
        selectInitialTable()
      }
      return
    }
    snapshot.value = latestResult
    snapshotId.value = latestResult.id
    hasSnapshot.value = true
    catalog.value = parseCatalog(latestResult.catalog)
    diff.value = parseDiff(latestResult.diff)
    selectInitialTable()
  } catch (err) {
    if (alive && generation === catalogGeneration) catalogError.value = toMessage(err)
  } finally {
    if (alive && generation === catalogGeneration) loadingCatalog.value = false
  }
}

async function captureMetadata() {
  if (!canWrite.value) return
  if (datasourceId.value === null || capturing.value || loadingCatalog.value) return
  const id = datasourceId.value
  const generation = ++catalogGeneration
  referenceGeneration++
  referenceController?.abort()
  references.value = null
  referencesError.value = ''
  loadingReferences.value = false
  capturing.value = true
  catalogError.value = ''
  try {
    const result = await metadataApi.capture(id)
    if (!alive || generation !== catalogGeneration || datasourceId.value !== id) return
    snapshot.value = result
    snapshotId.value = result.id
    hasSnapshot.value = true
    catalog.value = parseCatalog(result.catalog)
    diff.value = parseDiff(result.diff)
    snapshots.value = [
      {
        id: result.id,
        revision: result.revision,
        captured_at: result.captured_at,
      },
      ...snapshots.value.filter((item) => item.id !== result.id),
    ]
    selectInitialTable()
  } catch (err) {
    if (alive && generation === catalogGeneration) catalogError.value = toMessage(err)
  } finally {
    if (alive && generation === catalogGeneration) capturing.value = false
  }
}

async function loadDatasources() {
  datasourceController?.abort()
  const controller = new AbortController()
  datasourceController = controller
  loadingDatasources.value = true
  datasourceError.value = ''
  try {
    const result = await datasourcesApi.list({}, controller.signal)
    if (!alive || controller.signal.aborted || datasourceController !== controller) return
    datasources.value = result
    const routeId = Number(route.query.datasourceId)
    const initial = datasources.value.find((item) => item.id === routeId) ?? datasources.value[0]
    datasourceId.value = initial?.id ?? null
  } catch (err) {
    if (alive && datasourceController === controller && !controller.signal.aborted)
      datasourceError.value = toMessage(err)
  } finally {
    if (alive && datasourceController === controller && !controller.signal.aborted)
      loadingDatasources.value = false
  }
}

watch(
  datasourceId,
  (id) => {
    if (id !== null) void loadDatasourceCatalog(id)
    else {
      catalogGeneration++
      referenceGeneration++
      referenceController?.abort()
      loadingCatalog.value = false
      loadingReferences.value = false
      capturing.value = false
      snapshot.value = null
      snapshotId.value = null
      snapshots.value = []
      hasSnapshot.value = false
      catalogError.value = ''
      referencesError.value = ''
      references.value = null
      catalog.value = { schemas: [], table_count: 0, column_count: 0 }
      diff.value = { tables: [], columns: [], summary: {} }
      selectedSchema.value = ''
      selectedTable.value = ''
      selectedColumn.value = ''
    }
  },
  { flush: 'sync' },
)

watch(
  () => route.query.datasourceId,
  (value) => {
    const id = Number(value)
    if (Number.isSafeInteger(id) && datasources.value.some((item) => item.id === id)) {
      datasourceId.value = id
    }
  },
)

function retryCatalog() {
  if (datasourceId.value !== null) void loadDatasourceCatalog(datasourceId.value)
}

function openPreview() {
  if (
    datasourceId.value === null ||
    !activeSchema.value ||
    !activeTable.value ||
    activeTable.value.diff === 'removed'
  )
    return
  void router.push({
    name: 'sample-preview',
    query: {
      datasourceId: String(datasourceId.value),
      schema: activeSchema.value.name,
      table: activeTable.value.name,
      snapshot: snapshotId.value,
    },
  })
}

onMounted(() => void loadDatasources())

onBeforeUnmount(() => {
  alive = false
  catalogGeneration++
  referenceGeneration++
  datasourceController?.abort()
  referenceController?.abort()
})
usePageIdentity(() =>
  !loadingCatalog.value && snapshot.value
    ? datasources.value.find((item) => item.id === datasourceId.value)?.name
    : '',
)
</script>

<template>
  <section class="integration-page data-catalog">
    <PageHeader :title="t('page.dataCatalog')" :description="t('dataAccess.catalog.description')">
      <template #context
        ><span class="integration-caption"
          >{{ datasources.find((item) => item.id === datasourceId)?.name
          }}<template v-if="snapshot">
            ·
            {{
              t('dataAccess.catalog.snapshotRevision', {
                revision: formatNumber(snapshot.revision),
              })
            }}</template
          ></span
        ></template
      >
      <template #actions>
        <div class="toolbar">
          <FormField
            class="catalog-selector"
            label-for="catalog-datasource"
            :label="t('dataAccess.catalog.selectors.datasource')"
            :show-feedback="false"
          >
            <UiSelect
              v-model:value="datasourceId"
              :options="datasourceOptions"
              :loading="loadingDatasources"
              :placeholder="t('dataAccess.catalog.selectors.datasource')"
              :disabled="loadingDatasources || datasources.length === 0"
              filterable
            />
          </FormField>
          <FormField
            class="catalog-selector snapshot-selector"
            label-for="catalog-snapshot"
            :label="t('dataAccess.catalog.selectors.snapshot')"
            :show-feedback="false"
          >
            <UiSelect
              v-model:value="snapshotId"
              :options="snapshotOptions"
              :placeholder="t('dataAccess.catalog.selectors.snapshot')"
              :disabled="loadingCatalog || capturing || snapshots.length === 0"
              @change="selectSnapshot"
            />
          </FormField>
          <UiButton
            type="primary"
            :loading="capturing"
            :disabled="!canWrite || datasourceId === null || capturing || loadingCatalog"
            @click="captureMetadata"
          >
            {{
              capturing
                ? t('dataAccess.catalog.states.capturing')
                : t('dataAccess.catalog.actions.capture')
            }}
          </UiButton>
        </div>
      </template>
    </PageHeader>

    <UiAlert v-if="datasourceError" type="error" :title="t('dataAccess.catalog.states.errorTitle')">
      <p>{{ datasourceError }}</p>
      <UiButton @click="loadDatasources">
        {{ t('dataAccess.catalog.actions.retry') }}
      </UiButton>
    </UiAlert>

    <UiSpin
      v-else-if="loadingDatasources"
      show
      :description="t('dataAccess.catalog.states.loadingSources')"
      class="catalog-loading"
    />

    <UiEmpty
      v-else-if="datasources.length === 0"
      :description="t('dataAccess.catalog.states.noSources')"
    />

    <template v-else>
      <UiAlert v-if="catalogError" type="error" :title="t('dataAccess.catalog.states.errorTitle')">
        <p>{{ catalogError }}</p>
        <UiButton :disabled="loadingCatalog" @click="retryCatalog">
          {{ t('dataAccess.catalog.actions.retry') }}
        </UiButton>
      </UiAlert>

      <UiSpin
        v-else-if="loadingCatalog"
        show
        :description="t('dataAccess.catalog.states.loadingMetadata')"
        class="catalog-loading"
      />

      <UiEmpty v-else-if="!hasSnapshot" :description="t('dataAccess.catalog.states.noSnapshot')">
        <strong>{{ t('dataAccess.catalog.states.noSnapshot') }}</strong>
        <p>{{ t('dataAccess.catalog.states.noSnapshotHint') }}</p>
        <template #extra
          ><UiButton
            type="primary"
            :loading="capturing"
            :disabled="!canWrite || datasourceId === null || capturing || loadingCatalog"
            @click="captureMetadata"
          >
            {{
              capturing
                ? t('dataAccess.catalog.states.capturing')
                : t('dataAccess.catalog.actions.capture')
            }}
          </UiButton></template
        >
      </UiEmpty>

      <div v-else class="catalog-layout">
        <aside class="catalog-tree card">
          <div class="panel-heading">
            <h2>{{ t('dataAccess.catalog.tree.title') }}</h2>
            <span class="count mono">{{ formatNumber(catalog.table_count) }}</span>
          </div>
          <div v-if="schemas.length === 0" class="tree-empty">
            {{ t('dataAccess.catalog.states.noTables') }}
          </div>
          <ul v-else class="schema-list">
            <li v-for="schema in schemas" :key="schema.name">
              <UiButton
                quaternary
                size="small"
                class="schema-row"
                :aria-expanded="expandedSchemas.has(schema.name)"
                @click="toggleSchema(schema.name)"
              >
                <span
                  class="chevron"
                  :class="{ expanded: expandedSchemas.has(schema.name) }"
                  aria-hidden="true"
                ></span>
                <span class="schema-name mono">{{ schema.name }}</span>
                <span class="count mono">{{ formatNumber(schema.tables.length) }}</span>
              </UiButton>
              <ul v-if="expandedSchemas.has(schema.name)" class="table-list">
                <li v-for="table in schema.tables" :key="table.name">
                  <UiButton
                    quaternary
                    size="small"
                    class="table-row"
                    :aria-pressed="selectedSchema === schema.name && selectedTable === table.name"
                    :class="{
                      selected: selectedSchema === schema.name && selectedTable === table.name,
                      removed: table.diff === 'removed',
                    }"
                    @click="chooseTable(schema.name, table.name)"
                  >
                    <span
                      class="table-icon"
                      :class="{ view: table.type === 'view' }"
                      aria-hidden="true"
                    ></span>
                    <span class="table-name mono">{{ table.name }}</span>
                    <span v-if="table.diff" class="diff-badge" :class="'diff-' + table.diff">{{
                      diffLabel(table.diff)
                    }}</span>
                    <span v-else class="count mono">{{ formatNumber(table.columns.length) }}</span>
                  </UiButton>
                </li>
              </ul>
            </li>
          </ul>
        </aside>

        <main class="catalog-content">
          <section class="diff-summary card">
            <div class="summary-heading">
              <strong>{{ t('dataAccess.catalog.diff.title') }}</strong>
              <span v-if="snapshot" class="muted">
                {{
                  t('dataAccess.catalog.snapshotRevision', {
                    revision: formatNumber(snapshot.revision),
                  })
                }}
              </span>
            </div>
            <div
              v-if="Object.values(diff.summary).some((count) => count > 0)"
              class="summary-items"
            >
              <span
                v-for="item in summaryItems"
                v-show="(diff.summary[item.key] ?? 0) > 0"
                :key="item.key"
                class="diff-summary-item"
                :class="'diff-text-' + item.type"
              >
                {{ t('dataAccess.catalog.diff.' + item.label) }}
                <b>{{ formatNumber(diff.summary[item.key] ?? 0) }}</b>
              </span>
            </div>
            <p v-else class="muted no-diff">{{ t('dataAccess.catalog.diff.noChanges') }}</p>
            <p class="muted structure-note">{{ t('dataAccess.catalog.diff.structureOnly') }}</p>
          </section>

          <section v-if="activeTable" class="table-card card">
            <div class="panel-heading table-heading">
              <div class="table-title">
                <h2 class="mono">{{ activeTable.name }}</h2>
                <span class="type-badge">{{
                  t(
                    activeTable.type === 'view'
                      ? 'dataAccess.catalog.objectTypes.view'
                      : 'dataAccess.catalog.objectTypes.table',
                  )
                }}</span>
                <span class="muted mono">{{ selectedSchema }} / {{ activeTable.name }}</span>
              </div>
              <UiButton :disabled="activeTable.diff === 'removed'" @click="openPreview">
                {{ t('dataAccess.catalog.actions.samplePreview') }}
              </UiButton>
            </div>
            <SearchTable
              :rows="visibleColumns"
              :columns="columnDefinitions"
              row-key="name"
              mode="none"
              :searchable="false"
              :empty-text="t('dataAccess.catalog.states.noColumns')"
              :label="t('dataAccess.catalog.columns.name')"
              :row-props="(column) => ({ 'data-selected': selectedColumn === column.name })"
            >
              <template #toolbar><span /></template>
              <template #cell-name="{ row: column }">
                <UiButton
                  text
                  size="small"
                  class="column-link mono"
                  :aria-pressed="selectedColumn === column.name"
                  @click="selectedColumn = column.name"
                >
                  {{ column.name }}
                </UiButton>
              </template>
              <template #cell-type="{ row: column }"
                ><span class="column-type mono">{{
                  column.type || t('common.noneValue')
                }}</span></template
              >
              <template #cell-nullable="{ row: column }">{{
                column.diff?.type === 'removed'
                  ? t('common.noneValue')
                  : column.nullable
                    ? t('common.yes')
                    : t('common.no')
              }}</template>
              <template #cell-key="{ row: column }"
                ><span v-if="column.primary_key" class="key-mark">{{
                  t('dataAccess.catalog.keys.primary')
                }}</span
                ><span v-else>{{ t('common.noneValue') }}</span></template
              >
              <template #cell-foreignKey="{ row: column }"
                ><span class="foreign-key mono">{{
                  column.foreign_key ?? t('common.noneValue')
                }}</span></template
              >
              <template #cell-change="{ row: column }">
                <span v-if="column.diff" class="diff-badge" :class="'diff-' + column.diff.type">{{
                  diffLabel(column.diff.type)
                }}</span>
                <span v-if="column.diff?.details" class="diff-details">{{
                  column.diff.details
                }}</span>
                <span v-if="!column.diff" class="muted">{{ t('common.noneValue') }}</span>
              </template>
            </SearchTable>
            <div v-if="activeColumn" class="column-detail">
              <span class="muted">{{ t('dataAccess.catalog.selection.column') }}</span>
              <code>{{ activeColumn.name }}</code>
              <span class="column-type mono">{{ activeColumn.type }}</span>
            </div>
          </section>

          <section v-else class="card empty-table">
            {{ t('dataAccess.catalog.states.selectTable') }}
          </section>
        </main>
        <aside class="catalog-inspector" :aria-label="t('dataAccess.catalog.references.title')">
          <section class="card integration-inspector-facts">
            <h2>{{ t('dataAccess.catalog.selectors.snapshot') }}</h2>
            <dl class="integration-facts">
              <dt>{{ t('dataAccess.catalog.selectors.datasource') }}</dt>
              <dd>{{ datasources.find((item) => item.id === datasourceId)?.name }}</dd>
              <dt>{{ t('dataAccess.catalog.selectors.snapshot') }}</dt>
              <dd>
                {{
                  snapshot
                    ? t('dataAccess.catalog.snapshotRevision', {
                        revision: formatNumber(snapshot.revision),
                      })
                    : t('extractionUi.notRecorded')
                }}
              </dd>
              <dt>{{ t('dataAccess.catalog.tree.title') }}</dt>
              <dd>{{ formatNumber(catalog.table_count) }}</dd>
              <dt>{{ t('dataAccess.catalog.columns.name') }}</dt>
              <dd>{{ formatNumber(catalog.column_count) }}</dd>
              <template v-if="activeColumn"
                ><dt>{{ t('dataAccess.catalog.selection.column') }}</dt>
                <dd>
                  <code>{{ activeColumn.name }}</code> · {{ activeColumn.type }}
                </dd></template
              >
            </dl>
            <p class="integration-caption">{{ t('dataAccess.catalog.diff.structureOnly') }}</p>
          </section>
          <section v-if="activeTable" class="references-card card">
            <div class="panel-heading references-heading">
              <h2>{{ t('dataAccess.catalog.references.title') }}</h2>
              <span class="muted mono">{{ selectedSchema }} / {{ activeTable.name }}</span>
            </div>
            <UiSpin
              v-if="loadingReferences"
              show
              :description="t('dataAccess.catalog.references.loading')"
              class="catalog-loading"
            />
            <UiAlert v-else-if="referencesError" type="error">
              <span>{{ referencesError }}</span>
              <UiButton text @click="loadReferences(activeTable.name)">
                {{ t('dataAccess.catalog.actions.retry') }}
              </UiButton>
            </UiAlert>
            <UiEmpty
              v-else-if="!references?.references.length"
              :description="t('dataAccess.catalog.references.empty')"
            />
            <ul v-else class="reference-list">
              <li
                v-for="reference in references.references"
                :key="reference.mapping_id + ':' + reference.role"
              >
                <span
                  class="reference-dot"
                  :class="reference.role === 'entity' ? 'entity' : 'relation'"
                ></span>
                <span>{{ reference.mapping_name }}</span>
                <span class="type-badge">{{
                  t(
                    reference.role === 'entity'
                      ? 'dataAccess.catalog.references.entityMapping'
                      : 'dataAccess.catalog.references.relationMapping',
                  )
                }}</span>
                <span class="muted mono reference-target">{{ reference.role }}</span>
              </li>
            </ul>
            <p class="reference-hint">{{ t('dataAccess.catalog.references.changeWarning') }}</p>
          </section>
        </aside>
      </div>
    </template>
  </section>
</template>

<style scoped>
.data-catalog {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
  color: var(--foreground-primary);
}

.toolbar,
.panel-heading,
.summary-heading,
.summary-items,
.table-title,
.reference-list li,
.column-detail {
  display: flex;
  align-items: center;
}

.toolbar {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--space-2);
}

.card {
  min-width: 0;
  border: 1px solid var(--border-muted);
  border-radius: var(--radius-panel);
  background: var(--surface-panel);
  box-shadow: var(--shadow-low);
}

.catalog-layout {
  display: grid;
  grid-template-columns: minmax(220px, 262px) minmax(0, 1fr);
  align-items: start;
  gap: var(--space-4);
}

.catalog-tree {
  position: sticky;
  top: var(--space-4);
  padding: var(--space-3);
}

.panel-heading {
  justify-content: space-between;
  gap: var(--space-3);
  min-height: 38px;
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--border-muted);
}

.panel-heading h2,
.summary-heading strong {
  margin: 0;
  font-size: var(--font-small);
  font-weight: 500;
}

.catalog-tree > .panel-heading {
  padding: 0 0 var(--space-2);
}

.count,
.muted {
  color: var(--foreground-muted);
  font-size: var(--font-caption);
}

.schema-list,
.table-list,
.reference-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.schema-list {
  padding-top: var(--space-2);
}

.schema-row,
.table-row {
  display: flex;
  align-items: center;
  width: 100%;
  min-width: 0;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-2);
  border: 0;
  border-radius: var(--radius-small);
  color: var(--foreground-secondary);
  background: transparent;
  justify-content: flex-start;
  text-align: left;
  cursor: pointer;
}

.schema-row:hover,
.table-row:hover {
  background: var(--surface-hover);
}

.chevron {
  position: relative;
  width: 12px;
  height: 12px;
  color: var(--foreground-muted);
}

.chevron::before {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 5px;
  height: 5px;
  border-right: 1px solid currentColor;
  border-bottom: 1px solid currentColor;
  content: '';
  transform: rotate(-45deg);
}

.chevron.expanded::before {
  top: 1px;
  transform: rotate(45deg);
}

.schema-name,
.table-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.schema-row .count,
.table-row .count {
  margin-left: auto;
}

.table-list {
  padding-left: var(--space-5);
}

.table-row {
  color: var(--foreground-primary);
}

.table-row.selected {
  color: var(--action-primary);
  background: var(--action-soft);
}

.table-row.removed {
  opacity: 0.68;
}

.table-icon {
  position: relative;
  width: 12px;
  height: 12px;
  flex: none;
  border: 1px solid var(--graph-entity);
  border-radius: 2px;
}

.table-icon::after {
  position: absolute;
  top: 3px;
  left: 0;
  width: 100%;
  border-top: 1px solid var(--graph-entity);
  content: '';
}

.table-icon.view {
  width: 9px;
  height: 9px;
  margin: 1px;
  border-color: var(--graph-relation);
  transform: rotate(45deg);
}

.table-icon.view::after {
  border-color: var(--graph-relation);
}

.key-mark {
  color: var(--graph-entity);
}

.diff-badge,
.type-badge {
  display: inline-flex;
  flex: none;
  align-items: center;
  padding: calc(var(--space-1) / 4) var(--space-2);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  color: var(--foreground-secondary);
  font-size: var(--font-caption);
  white-space: nowrap;
}

.diff-added,
.diff-text-added {
  border-color: color-mix(in srgb, var(--status-pass) 45%, transparent);
  color: var(--status-pass);
}

.diff-removed,
.diff-text-removed {
  border-color: color-mix(in srgb, var(--status-violation) 45%, transparent);
  color: var(--status-violation);
}

.diff-modified,
.diff-text-modified {
  border-color: color-mix(in srgb, var(--status-not-run) 45%, transparent);
  color: var(--status-not-run);
}

.catalog-content {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: var(--space-4);
}

.diff-summary {
  padding: var(--space-3) var(--space-4);
}

.summary-heading {
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.summary-items {
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-4);
}

.diff-summary-item {
  font-size: var(--font-caption);
}

.diff-summary-item b {
  margin-left: var(--space-1);
}

.no-diff,
.structure-note {
  margin: 0;
  font-size: var(--font-caption);
}

.structure-note {
  margin-top: var(--space-2);
}

.table-card {
  overflow: hidden;
}

.table-heading {
  min-height: 52px;
}

.table-title {
  min-width: 0;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.table-title h2 {
  margin: 0;
  font-size: var(--font-h3);
  font-weight: 500;
}

.column-type {
  color: var(--graph-entity);
}

.foreign-key {
  color: var(--graph-relation);
}

.diff-details {
  display: inline-block;
  margin-left: var(--space-2);
  color: var(--foreground-muted);
  font-size: var(--font-caption);
}

.table-empty {
  padding: var(--space-5);
  color: var(--foreground-muted);
  text-align: center;
}

.column-detail {
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid var(--border-muted);
  font-size: var(--font-caption);
}

.column-detail code {
  color: var(--foreground-primary);
}

.empty-table,
.tree-empty {
  padding: var(--space-5);
  color: var(--foreground-muted);
  font-size: var(--font-caption);
  text-align: center;
}

.references-card {
  overflow: hidden;
}

.references-heading {
  justify-content: flex-start;
}

.references-state {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-4);
  font-size: var(--font-caption);
}

.references-error {
  color: var(--status-violation);
}

.reference-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4) 0;
}

.reference-list li {
  gap: var(--space-2);
  min-width: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-control);
  background: var(--surface-raised);
  font-size: var(--font-caption);
}

.reference-dot {
  width: 7px;
  height: 7px;
  flex: none;
  border-radius: 50%;
  background: var(--graph-entity);
}

.reference-dot.relation {
  background: var(--graph-relation);
}

.reference-target {
  margin-left: auto;
}

.reference-hint {
  margin: var(--space-3) var(--space-4) var(--space-4);
  color: var(--foreground-muted);
  font-size: var(--font-caption);
}

@media (max-width: 1050px) {
  .page-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .toolbar {
    justify-content: flex-start;
  }
}

@media (max-width: 760px) {
  .data-catalog {
    padding: var(--space-4);
  }

  .toolbar {
    display: grid;
    width: 100%;
    grid-template-columns: minmax(0, 1fr);
  }

  .toolbar > .ui-button {
    grid-column: 1;
    justify-self: start;
  }

  .catalog-selector,
  .snapshot-selector {
    width: 100%;
    max-width: none;
  }

  .catalog-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .catalog-tree {
    position: static;
  }

  .reference-list li {
    flex-wrap: wrap;
  }
}

.catalog-selector {
  width: min(100%, 220px);
}
.snapshot-selector {
  width: min(100%, 270px);
}
.catalog-loading {
  min-height: calc(var(--space-6) * 3);
}
.table-card :deep(tr[data-selected='true']) {
  background: var(--surface-selected);
}
</style>
