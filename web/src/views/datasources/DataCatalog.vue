<script setup lang="ts">
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
import { useApiError } from '@/composables/useApiError'

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
    if (item.type === 'removed' && !values.some((schema) => schema.name === item.schema)) {
      values.push({
        name: item.schema,
        tables: [{ name: item.name, type: 'table', columns: [], diff: 'removed' }],
      })
    }
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
  loadingCatalog.value = true
  catalogError.value = ''
  hasSnapshot.value = false
  snapshot.value = null
  catalog.value = { schemas: [], table_count: 0, column_count: 0 }
  diff.value = { tables: [], columns: [], summary: {} }
  references.value = null
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
  if (datasourceId.value === null) return
  const id = datasourceId.value
  const generation = ++catalogGeneration
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
  datasourceController = new AbortController()
  loadingDatasources.value = true
  datasourceError.value = ''
  try {
    datasources.value = await datasourcesApi.list({}, datasourceController.signal)
    if (!alive) return
    const routeId = Number(route.query.datasourceId)
    const initial = datasources.value.find((item) => item.id === routeId) ?? datasources.value[0]
    datasourceId.value = initial?.id ?? null
  } catch (err) {
    if (alive) datasourceError.value = toMessage(err)
  } finally {
    if (alive) loadingDatasources.value = false
  }
}

watch(datasourceId, (id) => {
  if (id !== null) void loadDatasourceCatalog(id)
})

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
  if (!activeSchema.value || !activeTable.value) return
  void router.push({
    name: 'sample-preview',
    query: {
      datasourceId: String(datasourceId.value),
      schema: activeSchema.value.name,
      table: activeTable.value.name,
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
</script>

<template>
  <section class="data-catalog">
    <PageHeader :title="t('page.dataCatalog')" :description="t('dataAccess.catalog.description')">
      <template #actions>
        <div class="toolbar">
          <label class="field-label" for="catalog-datasource">{{
            t('dataAccess.catalog.selectors.datasource')
          }}</label>
          <select
            id="catalog-datasource"
            v-model.number="datasourceId"
            class="select-control"
            :disabled="loadingDatasources || datasources.length === 0"
          >
            <option v-for="item in datasources" :key="item.id" :value="item.id">
              {{ item.name }}
            </option>
          </select>
          <label class="field-label" for="catalog-snapshot">{{
            t('dataAccess.catalog.selectors.snapshot')
          }}</label>
          <select
            id="catalog-snapshot"
            v-model.number="snapshotId"
            class="select-control snapshot-select"
            :disabled="loadingCatalog || capturing || snapshots.length === 0"
            @change="selectSnapshot"
          >
            <option v-for="item in snapshots" :key="item.id" :value="item.id">
              {{ t('dataAccess.catalog.snapshotRevision', { revision: item.revision }) }} ·
              {{ formatDate(item.captured_at) }}
            </option>
          </select>
          <button
            class="button button-primary"
            :disabled="datasourceId === null || capturing || loadingCatalog"
            @click="captureMetadata"
          >
            {{
              capturing
                ? t('dataAccess.catalog.states.capturing')
                : t('dataAccess.catalog.actions.capture')
            }}
          </button>
        </div>
      </template>
    </PageHeader>

    <div v-if="datasourceError" class="state-card state-error" role="alert">
      <div>
        <strong>{{ t('dataAccess.catalog.states.errorTitle') }}</strong>
        <p>{{ datasourceError }}</p>
      </div>
      <button class="button" @click="loadDatasources">
        {{ t('dataAccess.catalog.actions.retry') }}
      </button>
    </div>

    <div v-else-if="loadingDatasources" class="state-card" role="status">
      {{ t('dataAccess.catalog.states.loadingSources') }}
    </div>

    <div v-else-if="datasources.length === 0" class="state-card empty-state">
      <strong>{{ t('dataAccess.catalog.states.noSources') }}</strong>
    </div>

    <template v-else>
      <div v-if="catalogError" class="state-card state-error" role="alert">
        <div>
          <strong>{{ t('dataAccess.catalog.states.errorTitle') }}</strong>
          <p>{{ catalogError }}</p>
        </div>
        <button class="button" :disabled="loadingCatalog" @click="retryCatalog">
          {{ t('dataAccess.catalog.actions.retry') }}
        </button>
      </div>

      <div v-else-if="loadingCatalog" class="state-card" role="status">
        {{ t('dataAccess.catalog.states.loadingMetadata') }}
      </div>

      <div v-else-if="!hasSnapshot" class="state-card empty-state">
        <div>
          <strong>{{ t('dataAccess.catalog.states.noSnapshot') }}</strong>
          <p>{{ t('dataAccess.catalog.states.noSnapshotHint') }}</p>
        </div>
        <button
          class="button button-primary"
          :disabled="capturing || loadingCatalog"
          @click="captureMetadata"
        >
          {{
            capturing
              ? t('dataAccess.catalog.states.capturing')
              : t('dataAccess.catalog.actions.capture')
          }}
        </button>
      </div>

      <div v-else class="catalog-layout">
        <aside class="catalog-tree card">
          <div class="panel-heading">
            <h2>{{ t('dataAccess.catalog.tree.title') }}</h2>
            <span class="count mono">{{ catalog.table_count }}</span>
          </div>
          <div v-if="schemas.length === 0" class="tree-empty">
            {{ t('dataAccess.catalog.states.noTables') }}
          </div>
          <ul v-else class="schema-list">
            <li v-for="schema in schemas" :key="schema.name">
              <button
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
                <span class="count mono">{{ schema.tables.length }}</span>
              </button>
              <ul v-if="expandedSchemas.has(schema.name)" class="table-list">
                <li v-for="table in schema.tables" :key="table.name">
                  <button
                    class="table-row"
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
                    <span v-else class="count mono">{{ table.columns.length }}</span>
                  </button>
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
                {{ t('dataAccess.catalog.snapshotRevision', { revision: snapshot.revision }) }}
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
                <b>{{ diff.summary[item.key] }}</b>
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
              <button
                class="button"
                :disabled="activeTable.diff === 'removed'"
                @click="openPreview"
              >
                {{ t('dataAccess.catalog.actions.samplePreview') }}
              </button>
            </div>
            <div class="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{{ t('dataAccess.catalog.columns.name') }}</th>
                    <th>{{ t('dataAccess.catalog.columns.type') }}</th>
                    <th>{{ t('dataAccess.catalog.columns.nullable') }}</th>
                    <th>{{ t('dataAccess.catalog.columns.key') }}</th>
                    <th>{{ t('dataAccess.catalog.columns.foreignKey') }}</th>
                    <th>{{ t('dataAccess.catalog.columns.change') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="column in visibleColumns"
                    :key="column.name"
                    :class="{ selected: selectedColumn === column.name }"
                  >
                    <td>
                      <button class="column-link mono" @click="selectedColumn = column.name">
                        {{ column.name }}
                      </button>
                    </td>
                    <td class="column-type mono">{{ column.type || t('common.noneValue') }}</td>
                    <td>
                      {{
                        column.diff?.type === 'removed'
                          ? t('common.noneValue')
                          : column.nullable
                            ? t('common.yes')
                            : t('common.no')
                      }}
                    </td>
                    <td>
                      <span v-if="column.primary_key" class="key-mark">{{
                        t('dataAccess.catalog.keys.primary')
                      }}</span
                      ><span v-else>{{ t('common.noneValue') }}</span>
                    </td>
                    <td class="foreign-key mono">
                      {{ column.foreign_key || t('common.noneValue') }}
                    </td>
                    <td>
                      <span
                        v-if="column.diff"
                        class="diff-badge"
                        :class="'diff-' + column.diff.type"
                      >
                        {{ diffLabel(column.diff.type) }}
                      </span>
                      <span v-if="column.diff?.details" class="diff-details">{{
                        column.diff.details
                      }}</span>
                      <span v-if="!column.diff" class="muted">{{ t('common.noneValue') }}</span>
                    </td>
                  </tr>
                  <tr v-if="visibleColumns.length === 0">
                    <td colspan="6" class="table-empty">
                      {{ t('dataAccess.catalog.states.noColumns') }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-if="activeColumn" class="column-detail">
              <span class="muted">{{ t('dataAccess.catalog.selection.column') }}</span>
              <code>{{ activeColumn.name }}</code>
              <span class="column-type mono">{{ activeColumn.type }}</span>
            </div>
          </section>

          <section v-else class="card empty-table">
            {{ t('dataAccess.catalog.states.selectTable') }}
          </section>

          <section v-if="activeTable" class="references-card card">
            <div class="panel-heading references-heading">
              <h2>{{ t('dataAccess.catalog.references.title') }}</h2>
              <span class="muted mono">{{ selectedSchema }} / {{ activeTable.name }}</span>
            </div>
            <div v-if="loadingReferences" class="references-state" role="status">
              {{ t('dataAccess.catalog.references.loading') }}
            </div>
            <div v-else-if="referencesError" class="references-state references-error" role="alert">
              <span>{{ referencesError }}</span>
              <button class="text-button" @click="loadReferences(activeTable.name)">
                {{ t('dataAccess.catalog.actions.retry') }}
              </button>
            </div>
            <div v-else-if="!references?.references.length" class="references-state muted">
              {{ t('dataAccess.catalog.references.empty') }}
            </div>
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
        </main>
      </div>
    </template>
  </section>
</template>

<style scoped>
.data-catalog {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
  color: var(--text);
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
  gap: 8px;
}

.field-label {
  color: var(--text-tertiary);
  font-size: var(--font-caption);
}

.select-control,
.button {
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  color: var(--text);
  background: var(--bg-inset);
  font: inherit;
}

.select-control {
  max-width: 220px;
}

.snapshot-select {
  max-width: 270px;
}

.button {
  cursor: pointer;
  background: var(--bg-raised);
  white-space: nowrap;
}

.button:hover:not(:disabled) {
  border-color: var(--border-strong);
  background: var(--bg-hover);
}

.button-primary {
  border-color: transparent;
  color: var(--on-accent);
  background: var(--accent);
}

.button:disabled,
.select-control:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.card,
.state-card {
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-lg);
  background: var(--bg-surface);
  box-shadow: var(--elev-1);
}

.state-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px;
  color: var(--text-secondary);
}

.state-card p {
  margin: 4px 0 0;
}

.state-error {
  border-color: color-mix(in srgb, var(--danger) 36%, transparent);
  color: var(--danger);
}

.empty-state {
  min-height: 116px;
}

.empty-state strong {
  color: var(--text);
}

.catalog-layout {
  display: grid;
  grid-template-columns: minmax(220px, 262px) minmax(0, 1fr);
  align-items: start;
  gap: 14px;
}

.catalog-tree {
  position: sticky;
  top: 16px;
  padding: 12px;
}

.panel-heading {
  justify-content: space-between;
  gap: 10px;
  min-height: 38px;
  padding: 0 14px;
  border-bottom: 1px solid var(--border-subtle);
}

.panel-heading h2,
.summary-heading strong {
  margin: 0;
  font-size: var(--font-small);
  font-weight: 500;
}

.catalog-tree > .panel-heading {
  padding: 0 0 8px;
}

.count,
.muted {
  color: var(--text-tertiary);
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
  padding-top: 7px;
}

.schema-row,
.table-row {
  display: flex;
  align-items: center;
  width: 100%;
  min-width: 0;
  gap: 7px;
  padding: 6px 7px;
  border: 0;
  border-radius: var(--r-sm);
  color: var(--text-secondary);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.schema-row:hover,
.table-row:hover {
  background: var(--bg-hover);
}

.chevron {
  position: relative;
  width: 12px;
  height: 12px;
  color: var(--text-tertiary);
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
  padding-left: 18px;
}

.table-row {
  color: var(--text);
}

.table-row.selected {
  color: var(--accent);
  background: var(--accent-soft);
}

.table-row.removed {
  opacity: 0.68;
}

.table-icon {
  position: relative;
  width: 12px;
  height: 12px;
  flex: none;
  border: 1px solid var(--cyan);
  border-radius: 2px;
}

.table-icon::after {
  position: absolute;
  top: 3px;
  left: 0;
  width: 100%;
  border-top: 1px solid var(--cyan);
  content: '';
}

.table-icon.view {
  width: 9px;
  height: 9px;
  margin: 1px;
  border-color: var(--violet);
  transform: rotate(45deg);
}

.table-icon.view::after {
  border-color: var(--violet);
}

.key-mark {
  color: var(--cyan);
}

.diff-badge,
.type-badge {
  display: inline-flex;
  flex: none;
  align-items: center;
  padding: 1px 6px;
  border: 1px solid var(--border);
  border-radius: var(--r-pill);
  color: var(--text-secondary);
  font-size: 10px;
  white-space: nowrap;
}

.diff-added,
.diff-text-added {
  border-color: color-mix(in srgb, var(--s-pass) 45%, transparent);
  color: var(--s-pass);
}

.diff-removed,
.diff-text-removed {
  border-color: color-mix(in srgb, var(--s-violation) 45%, transparent);
  color: var(--s-violation);
}

.diff-modified,
.diff-text-modified {
  border-color: color-mix(in srgb, var(--s-notrun) 45%, transparent);
  color: var(--s-notrun);
}

.catalog-content {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 14px;
}

.diff-summary {
  padding: 12px 16px;
}

.summary-heading {
  gap: 10px;
  margin-bottom: 8px;
}

.summary-items {
  flex-wrap: wrap;
  gap: 7px 16px;
}

.diff-summary-item {
  font-size: var(--font-caption);
}

.diff-summary-item b {
  margin-left: 4px;
}

.no-diff,
.structure-note {
  margin: 0;
  font-size: var(--font-caption);
}

.structure-note {
  margin-top: 6px;
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
  gap: 8px;
}

.table-title h2 {
  margin: 0;
  font-size: var(--font-h3);
  font-weight: 500;
}

.table-scroll {
  overflow: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-caption);
  text-align: left;
}

th,
td {
  padding: 9px 12px;
  border-bottom: 1px solid var(--border-subtle);
  vertical-align: middle;
}

th {
  color: var(--text-tertiary);
  font-size: 11px;
  font-weight: 400;
  white-space: nowrap;
}

tbody tr:hover,
tbody tr.selected {
  background: var(--bg-hover);
}

tbody tr:last-child td {
  border-bottom: 0;
}

.column-link,
.text-button {
  padding: 0;
  border: 0;
  color: var(--text);
  background: transparent;
  cursor: pointer;
}

.column-link:hover,
.text-button:hover {
  color: var(--accent);
}

.column-type {
  color: var(--cyan);
}

.foreign-key {
  color: var(--violet);
}

.diff-details {
  display: inline-block;
  margin-left: 6px;
  color: var(--text-tertiary);
  font-size: 11px;
}

.table-empty {
  padding: 22px;
  color: var(--text-tertiary);
  text-align: center;
}

.column-detail {
  gap: 10px;
  padding: 10px 14px;
  border-top: 1px solid var(--border-subtle);
  font-size: var(--font-caption);
}

.column-detail code {
  color: var(--text);
}

.empty-table,
.tree-empty {
  padding: 18px;
  color: var(--text-tertiary);
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
  gap: 12px;
  padding: 14px 16px;
  font-size: var(--font-caption);
}

.references-error {
  color: var(--danger);
}

.reference-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 12px 14px 0;
}

.reference-list li {
  gap: 9px;
  min-width: 0;
  padding: 9px 11px;
  border-radius: var(--r-md);
  background: var(--bg-raised);
  font-size: var(--font-caption);
}

.reference-dot {
  width: 7px;
  height: 7px;
  flex: none;
  border-radius: 50%;
  background: var(--g-entity);
}

.reference-dot.relation {
  background: var(--g-relation);
}

.reference-target {
  margin-left: auto;
}

.reference-hint {
  margin: 10px 14px 14px;
  color: var(--text-tertiary);
  font-size: 11px;
}

.text-button {
  color: var(--accent);
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
    padding: 16px;
  }

  .toolbar {
    display: grid;
    width: 100%;
    grid-template-columns: auto minmax(0, 1fr);
  }

  .toolbar .button {
    grid-column: 2;
    justify-self: start;
  }

  .select-control,
  .snapshot-select {
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
</style>
