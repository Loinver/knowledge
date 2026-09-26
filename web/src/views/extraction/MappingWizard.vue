<script setup lang="ts">
import {
  NAlert,
  NButton,
  NCard,
  NEmpty,
  NInput,
  NInputNumber,
  NSelect,
  NSpin,
  NTag,
} from 'naive-ui'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { datasourcesApi, metadataApi } from '@/api/datasources'
import type { EntityType, EntityTypeBrief } from '@/api/entity-types'
import { entityTypesApi } from '@/api/entity-types'
import type { RunStartResponse } from '@/api/extraction'
import { extractionApi } from '@/api/extraction'
import type { Mapping, MappingPreview, MappingRevision } from '@/api/mappings'
import { mappingsApi } from '@/api/mappings'
import type { Ontology } from '@/api/ontology'
import { ontologyApi } from '@/api/ontology'
import type { RelationTypeBrief, RelationTypeDetail } from '@/api/relations'
import { relationsApi } from '@/api/relations'
import type { components } from '@/api/schema'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'

type S = components['schemas']
type Datasource = components['schemas']['DatasourceBrief']
type EntityBrief = EntityTypeBrief
type EntityDetail = EntityType
type RelationBrief = RelationTypeBrief
type RelationDetail = RelationTypeDetail
type FieldMap = S['FieldMap']
type TransformKind = S['TransformKind']
type NullPolicy = S['NullPolicy']
type RelationMode = S['RelMode']

interface CatalogColumn {
  name: string
  type: string
  nullable: boolean
  primary_key: boolean
  foreign_key?: string | null
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
interface Catalog {
  schemas: CatalogSchema[]
  table_count: number
  column_count: number
}
interface EntityDraft {
  localId: number
  entity_type: string
  table: string
  schema: string
  field_maps: FieldMap[]
  key_fields: string[]
  /** 跨表业务键：多表映射同一类型时按业务键值融合为同一稳定 IRI */
  match_keys: string[]
}
interface RelationAttributeMap {
  attr: string
  field: string
}
interface EndpointCandidate {
  field: string
  ref_table: string
  when: string
  ref_entity_type: string
}
interface RelationDraft {
  localId: number
  relation_type: string
  mode: RelationMode
  table: string
  schema: string
  fk_field: string
  source_field: string
  source_ref_table: string
  source_ref_field: string
  /** 多态端点：判别字段 + 候选列表（可二跳经由） */
  source_type_field: string
  source_candidates: EndpointCandidate[]
  source_via_table: string
  source_via_field: string
  source_via_ref_field: string
  target_field: string
  target_ref_table: string
  target_ref_field: string
  target_type_field: string
  target_candidates: EndpointCandidate[]
  target_via_table: string
  target_via_field: string
  target_via_ref_field: string
  attributes: RelationAttributeMap[]
}

const { t, locale } = useI18n()
const { toMessage: describeError } = useApiError()
const router = useRouter()
const step = ref(1)
const loading = ref(false)
const working = ref(false)
const loadError = ref('')
const actionError = ref('')
const notice = ref('')
const mappings = ref<Mapping[]>([])
const datasources = ref<Datasource[]>([])
const ontologies = ref<Ontology[]>([])
const entityBriefs = ref<EntityBrief[]>([])
const relationBriefs = ref<RelationBrief[]>([])
const selectedMappingId = ref<number | null>(null)
const selectedDatasourceId = ref<number | null>(null)
const selectedOntologyId = ref<number | null>(null)
const mappingName = ref('')
const catalog = ref<Catalog | null>(null)
const metadataRevision = ref<number | null>(null)
const entityTypes = ref<EntityDetail[]>([])
const relationTypes = ref<RelationDetail[]>([])
const ontologyRefs = ref<S['OntologyRefOut'][]>([])
const entityMaps = ref<EntityDraft[]>([])
const relationMaps = ref<RelationDraft[]>([])
const preview = ref<MappingPreview | null>(null)
const draftRevision = ref<MappingRevision | null>(null)
const publishedRevision = ref<MappingRevision | null>(null)
const runResult = ref<RunStartResponse | null>(null)
const samplePreview = ref<S['PreviewResponse'] | null>(null)
const selectedSampleTable = ref<string | null>(null)
const sampleLimit = ref<number>(20)
const namespace = ref('')
const viewMode = ref<'graph' | 'table'>('graph')
let selectionController: AbortController | undefined
let assetController: AbortController | undefined
let lifecycleController: AbortController | undefined
let selectionGeneration = 0
let nextLocalId = 1

const selectedMapping = computed(
  () => mappings.value.find((item) => item.id === selectedMappingId.value) ?? null,
)
const selectedOntology = computed(
  () => ontologies.value.find((item) => item.id === selectedOntologyId.value) ?? null,
)
const allTables = computed(() =>
  (catalog.value?.schemas ?? []).flatMap((schema) =>
    schema.tables.map((table) => ({ schema: schema.schema, ...table })),
  ),
)
const tableOptions = computed(() =>
  allTables.value.map((table) => ({
    value: tableValue(table.schema, table.name),
    label: `${table.schema}.${table.name}`,
  })),
)
const entityOptions = computed(() =>
  entityTypes.value.map((item) => ({ value: item.name, label: resourceLabel(item) })),
)
const relationOptions = computed(() =>
  relationTypes.value.map((item) => ({ value: item.name, label: resourceLabel(item) })),
)
const resultErrorCount = computed(() => {
  if (!preview.value) return 0
  const entityErrors = preview.value.entities.reduce((count, item) => count + item.errors.length, 0)
  const relationErrors = preview.value.relations.reduce(
    (count, item) => count + item.errors.length,
    0,
  )
  const cellErrors = preview.value.entities.reduce(
    (count, item) =>
      count +
      item.rows.reduce(
        (rowCount, row) => rowCount + row.cells.filter((cell) => cell.status === 'error').length,
        0,
      ),
    0,
  )
  return entityErrors + relationErrors + cellErrors
})
const canSaveDraft = computed(() => {
  if (!mappingName.value.trim() || !selectedOntologyId.value || entityMaps.value.length === 0)
    return false
  const entitiesComplete = entityMaps.value.every((map) => {
    const properties =
      entityTypes.value.find((item) => item.name === map.entity_type)?.data_props ?? []
    return (
      Boolean(getTable(map.schema, map.table)) &&
      map.field_maps.length > 0 &&
      map.field_maps.every((field) => Boolean(field.source_field)) &&
      properties.every((property) =>
        map.field_maps.some((field) => field.target_attr === property.name),
      ) &&
      map.field_maps.every(
        (field) => field.null_policy !== 'DEFAULT' || Boolean(field.default_value?.trim()),
      )
    )
  })
  const relationsComplete = relationMaps.value.every((map) => {
    if (!map.relation_type || !getTable(map.schema, map.table)) return false
    if (map.mode === 'FK') return Boolean(map.fk_field)
    const endpointOk = (side: {
      field: string
      ref_table: string
      ref_field: string
      type_field: string
      candidates: EndpointCandidate[]
      via_table: string
      via_field: string
    }) => {
      const single = Boolean(side.field && side.ref_table && side.ref_field)
      const candidatesOk =
        side.candidates.length > 0 &&
        side.candidates.every(
          (candidate) =>
            Boolean(candidate.field && candidate.ref_table) &&
            (!side.type_field || !!candidate.when),
        )
      const viaOk = !side.via_table || Boolean(side.via_field)
      return (single || candidatesOk) && viaOk
    }
    return (
      endpointOk({
        field: map.source_field,
        ref_table: map.source_ref_table,
        ref_field: map.source_ref_field,
        type_field: map.source_type_field,
        candidates: map.source_candidates,
        via_table: map.source_via_table,
        via_field: map.source_via_field,
      }) &&
      endpointOk({
        field: map.target_field,
        ref_table: map.target_ref_table,
        ref_field: map.target_ref_field,
        type_field: map.target_type_field,
        candidates: map.target_candidates,
        via_table: map.target_via_table,
        via_field: map.target_via_field,
      }) &&
      map.attributes.every((attribute) => Boolean(attribute.field))
    )
  })
  return entitiesComplete && relationsComplete
})
const currentPreviewIsClean = computed(() => Boolean(preview.value && resultErrorCount.value === 0))
const canPublish = computed(() =>
  Boolean(
    selectedMapping.value &&
    selectedMapping.value.status !== 'PUBLISHED' &&
    selectedOntology.value?.status === 'PUBLISHED' &&
    draftRevision.value &&
    canSaveDraft.value &&
    currentPreviewIsClean.value,
  ),
)
const canRun = computed(() => Boolean(selectedDatasourceId.value && publishedRevision.value))
const savedRevisionLabel = computed(() =>
  selectedMapping.value?.status === 'PUBLISHED'
    ? `rev.${selectedMapping.value.current_revision}`
    : draftRevision.value
      ? t('dataAccess.mapping.draft')
      : t('dataAccess.mapping.unsaved'),
)
const previewEntityRows = computed(() => preview.value?.entities ?? [])
const previewRelationRows = computed(() => preview.value?.relations ?? [])
const metadataTableCount = computed(() => catalog.value?.table_count ?? 0)
const metadataColumnCount = computed(() => catalog.value?.column_count ?? 0)

function errorCode(error: unknown): string {
  return typeof error === 'object' && error !== null && 'code' in error
    ? String(error.code)
    : 'NETWORK_ERROR'
}
function isCanceled(error: unknown): boolean {
  return errorCode(error) === 'ERR_CANCELED'
}
function resourceLabel(item: { name: string; label_i18n?: Record<string, string> | null }): string {
  return item.label_i18n?.[locale.value] || item.label_i18n?.['zh-CN'] || item.name
}
function tableValue(schema: string, table: string): string {
  return `${schema}::${table}`
}
function tableParts(value: string): { schema: string; table: string } {
  const splitAt = value.indexOf('::')
  return splitAt < 0
    ? { schema: 'main', table: value }
    : { schema: value.slice(0, splitAt), table: value.slice(splitAt + 2) }
}
function getTable(schema: string, table: string): CatalogTable | undefined {
  return catalog.value?.schemas
    .find((item) => item.schema === schema)
    ?.tables.find((item) => item.name === table)
}
function tableColumns(schema: string, table: string): CatalogColumn[] {
  return getTable(schema, table)?.columns ?? []
}
function fieldOptions(schema: string, table: string) {
  return tableColumns(schema, table).map((column) => ({
    label: `${column.name} · ${column.type}`,
    value: column.name,
  }))
}
function relationFieldOptions(map: RelationDraft) {
  return tableColumns(map.schema, map.table).map((column) => ({
    label: column.name,
    value: column.name,
  }))
}
function refTableOptions() {
  return allTables.value.map((table) => ({
    value: table.name,
    label: `${table.schema}.${table.name}`,
  }))
}
function invalidatePreview(): void {
  preview.value = null
  samplePreview.value = null
}
function setEntityTable(map: EntityDraft, value: string | null): void {
  const parsed = tableParts(value ?? '')
  map.schema = parsed.schema
  map.table = parsed.table
  map.key_fields = tableColumns(map.schema, map.table)
    .filter((column) => column.primary_key)
    .map((column) => column.name)
  invalidatePreview()
}
function setRelationTable(map: RelationDraft, value: string | null): void {
  const parsed = tableParts(value ?? '')
  map.schema = parsed.schema
  map.table = parsed.table
  map.fk_field = ''
  map.source_field = ''
  map.target_field = ''
  invalidatePreview()
}
function toggleKeyField(map: EntityDraft, field: string, checked: boolean): void {
  map.key_fields = checked
    ? [...new Set([...map.key_fields, field])]
    : map.key_fields.filter((item) => item !== field)
  invalidatePreview()
}
function toggleMatchKey(map: EntityDraft, field: string, checked: boolean): void {
  map.match_keys = checked
    ? [...new Set([...map.match_keys, field])]
    : map.match_keys.filter((item) => item !== field)
  invalidatePreview()
}
function addEndpointCandidate(map: RelationDraft, side: 'source' | 'target'): void {
  const list = side === 'source' ? map.source_candidates : map.target_candidates
  list.push({ field: '', ref_table: '', when: '', ref_entity_type: '' })
  invalidatePreview()
}
function removeEndpointCandidate(
  map: RelationDraft,
  side: 'source' | 'target',
  index: number,
): void {
  if (side === 'source') map.source_candidates.splice(index, 1)
  else map.target_candidates.splice(index, 1)
  invalidatePreview()
}
function candidateFieldOptions(map: RelationDraft, viaTable: string) {
  const schema = map.schema
  const columns = viaTable ? tableColumns(schema, viaTable) : relationFieldOptions(map)
  return columns.map((column) => ({
    value: 'name' in column ? column.name : String(column.value),
    label: 'name' in column ? column.name : String(column.label),
  }))
}
function newFieldMap(property: S['DataTypePropOut']): FieldMap {
  return {
    target_attr: property.name,
    source_field: '',
    transform: 'IDENTITY',
    transform_params: null,
    null_policy: property.nullable ? 'NULLABLE' : 'REQUIRED',
    default_value: property.default_value ?? null,
  }
}
function newEntityMap(typeName: string): EntityDraft {
  const type = entityTypes.value.find((item) => item.name === typeName)
  return {
    localId: nextLocalId++,
    entity_type: typeName,
    table: '',
    schema: 'main',
    field_maps: (type?.data_props ?? []).map(newFieldMap),
    key_fields: [],
    match_keys: [],
  }
}
function addEntityMap(): void {
  const next = entityTypes.value.find(
    (item) => !entityMaps.value.some((map) => map.entity_type === item.name),
  )
  if (next) entityMaps.value.push(newEntityMap(next.name))
  invalidatePreview()
}
function changeEntityType(map: EntityDraft, typeName: string | null): void {
  const replacement = newEntityMap(typeName ?? '')
  map.entity_type = replacement.entity_type
  map.field_maps = replacement.field_maps
  invalidatePreview()
}
function addRelationMap(): void {
  const next = relationTypes.value.find(
    (item) => !relationMaps.value.some((map) => map.relation_type === item.name),
  )
  if (!next) return
  relationMaps.value.push({
    localId: nextLocalId++,
    relation_type: next.name,
    mode: 'JUNCTION',
    table: '',
    schema: 'main',
    fk_field: '',
    source_field: '',
    source_ref_table: '',
    source_ref_field: 'id',
    source_type_field: '',
    source_candidates: [],
    source_via_table: '',
    source_via_field: '',
    source_via_ref_field: 'id',
    target_field: '',
    target_ref_table: '',
    target_ref_field: 'id',
    target_type_field: '',
    target_candidates: [],
    target_via_table: '',
    target_via_field: '',
    target_via_ref_field: 'id',
    attributes: (next.attribute_defs ?? []).map((item) => ({ attr: item.name, field: '' })),
  })
  invalidatePreview()
}
function changeRelationType(map: RelationDraft, typeName: string | null): void {
  map.relation_type = typeName ?? ''
  const type = relationTypes.value.find((item) => item.name === map.relation_type)
  map.attributes = (type?.attribute_defs ?? []).map((item) => ({ attr: item.name, field: '' }))
  invalidatePreview()
}
function removeEntityMap(localId: number): void {
  entityMaps.value = entityMaps.value.filter((item) => item.localId !== localId)
  invalidatePreview()
}
function removeRelationMap(localId: number): void {
  relationMaps.value = relationMaps.value.filter((item) => item.localId !== localId)
  invalidatePreview()
}
function loadCatalog(value: unknown): Catalog | null {
  if (typeof value !== 'object' || value === null || !('schemas' in value)) return null
  const candidate = value as { schemas?: unknown; table_count?: unknown; column_count?: unknown }
  if (!Array.isArray(candidate.schemas)) return null
  return {
    schemas: candidate.schemas as CatalogSchema[],
    table_count: Number(candidate.table_count ?? 0),
    column_count: Number(candidate.column_count ?? 0),
  }
}
function recordOf(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {}
}
function textOf(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}
function normalizeEntityMap(value: unknown): EntityDraft {
  const row = recordOf(value)
  const maps = Array.isArray(row.field_maps) ? row.field_maps : []
  const fields = maps.map((item): FieldMap => {
    const field = recordOf(item)
    return {
      target_attr: textOf(field.target_attr),
      source_field: textOf(field.source_field),
      transform: (field.transform ?? 'IDENTITY') as TransformKind,
      transform_params: (field.transform_params ?? null) as Record<string, unknown> | null,
      null_policy: (field.null_policy ?? 'NULLABLE') as NullPolicy,
      default_value: typeof field.default_value === 'string' ? field.default_value : null,
    }
  })
  const name = textOf(row.entity_type)
  const properties = entityTypes.value.find((item) => item.name === name)?.data_props ?? []
  for (const property of properties)
    if (!fields.some((item) => item.target_attr === property.name))
      fields.push(newFieldMap(property))
  return {
    localId: nextLocalId++,
    entity_type: name,
    table: textOf(row.table),
    schema: textOf(row.schema, 'main'),
    field_maps: fields,
    key_fields: Array.isArray(row.key_fields)
      ? row.key_fields.filter((item): item is string => typeof item === 'string')
      : [],
    match_keys: Array.isArray(row.match_keys)
      ? row.match_keys.filter((item): item is string => typeof item === 'string')
      : [],
  }
}
function normalizeRelationMap(value: unknown): RelationDraft {
  const row = recordOf(value)
  const source = recordOf(row.source)
  const target = recordOf(row.target)
  const attributes = Array.isArray(row.attributes)
    ? row.attributes.map((item) => ({
        attr: textOf(recordOf(item).attr),
        field: textOf(recordOf(item).field),
      }))
    : []
  return {
    localId: nextLocalId++,
    relation_type: textOf(row.relation_type),
    mode: (row.mode ?? 'JUNCTION') as RelationMode,
    table: textOf(row.table),
    schema: textOf(row.schema, 'main'),
    fk_field: textOf(row.fk_field),
    source_field: textOf(source.field),
    source_ref_table: textOf(source.ref_table),
    source_ref_field: textOf(source.ref_field, 'id'),
    source_type_field: textOf(source.type_field),
    source_candidates: parseCandidates(source.candidates),
    source_via_table: textOf(recordOf(source.via).table),
    source_via_field: textOf(recordOf(source.via).field),
    source_via_ref_field: textOf(recordOf(source.via).ref_field, 'id'),
    target_field: textOf(target.field),
    target_ref_table: textOf(target.ref_table),
    target_ref_field: textOf(target.ref_field, 'id'),
    target_type_field: textOf(target.type_field),
    target_candidates: parseCandidates(target.candidates),
    target_via_table: textOf(recordOf(target.via).table),
    target_via_field: textOf(recordOf(target.via).field),
    target_via_ref_field: textOf(recordOf(target.via).ref_field, 'id'),
    attributes,
  }
}
function parseCandidates(value: unknown): EndpointCandidate[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => {
    const row = recordOf(item)
    return {
      field: textOf(row.field),
      ref_table: textOf(row.ref_table),
      when: textOf(row.when),
      ref_entity_type: textOf(row.ref_entity_type),
    }
  })
}

async function loadInitial(): Promise<void> {
  loading.value = true
  lifecycleController = new AbortController()
  loadError.value = ''
  const signal = lifecycleController.signal
  try {
    const [mappingItems, datasourceItems, ontologyItems, entityItems, relationItems] =
      await Promise.all([
        mappingsApi.list(signal),
        datasourcesApi.list({}, signal),
        ontologyApi.list({ page: 1, page_size: 200 }, signal),
        entityTypesApi.list({ page: 1, page_size: 200 }, signal),
        relationsApi.list({ page: 1, page_size: 200 }, signal),
      ])
    mappings.value = mappingItems
    datasources.value = datasourceItems
    ontologies.value = ontologyItems
    entityBriefs.value = entityItems
    relationBriefs.value = relationItems
  } catch (error: unknown) {
    if (!isCanceled(error)) loadError.value = describeError(error)
  } finally {
    loading.value = false
  }
}
async function loadOntologyAssets(ontologyId: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return
  assetController?.abort()
  const controller = new AbortController()
  assetController = controller
  const abortListener = () => controller.abort()
  signal.addEventListener('abort', abortListener, { once: true })
  try {
    const refs = await ontologyApi.refs(ontologyId, controller.signal)
    if (controller.signal.aborted || assetController !== controller) return
    ontologyRefs.value = refs
    const ids = new Set(refs.map((item) => item.resource_id))
    const entityRefs = entityBriefs.value.filter((item) => ids.has(item.id))
    const relationRefs = relationBriefs.value.filter((item) => ids.has(item.id))
    const [entities, relations] = await Promise.all([
      Promise.all(entityRefs.map((item) => entityTypesApi.get(item.id, controller.signal))),
      Promise.all(relationRefs.map((item) => relationsApi.get(item.id, controller.signal))),
    ])
    if (controller.signal.aborted || assetController !== controller) return
    entityTypes.value = entities
    relationTypes.value = relations
  } finally {
    signal.removeEventListener('abort', abortListener)
  }
}
async function chooseOntology(value: number | null): Promise<void> {
  selectedOntologyId.value = value
  entityMaps.value = []
  relationMaps.value = []
  draftRevision.value = null
  preview.value = null
  if (!value) {
    entityTypes.value = []
    relationTypes.value = []
    ontologyRefs.value = []
    return
  }
  actionError.value = ''
  try {
    await loadOntologyAssets(value, lifecycleController?.signal ?? new AbortController().signal)
  } catch (error: unknown) {
    if (!isCanceled(error)) actionError.value = describeError(error)
  }
}
function newMapping(): void {
  selectionGeneration += 1
  working.value = false
  selectionController?.abort()
  assetController?.abort()
  selectedMappingId.value = null
  mappingName.value = ''
  selectedOntologyId.value = null
  entityTypes.value = []
  relationTypes.value = []
  ontologyRefs.value = []
  entityMaps.value = []
  relationMaps.value = []
  draftRevision.value = null
  publishedRevision.value = null
  preview.value = null
  runResult.value = null
  samplePreview.value = null
  step.value = 1
  notice.value = ''
  actionError.value = ''
}
async function selectMapping(value: number | null): Promise<void> {
  if (!value) {
    newMapping()
    return
  }
  selectionGeneration += 1
  working.value = false
  selectionController?.abort()
  assetController?.abort()
  const controller = new AbortController()
  selectionController = controller
  selectedMappingId.value = value
  actionError.value = ''
  notice.value = ''
  preview.value = null
  runResult.value = null
  samplePreview.value = null
  entityMaps.value = []
  relationMaps.value = []
  draftRevision.value = null
  publishedRevision.value = null
  try {
    const item = await mappingsApi.get(value, controller.signal)
    if (controller.signal.aborted || selectedMappingId.value !== value) return
    mappings.value = mappings.value.map((mapping) => (mapping.id === value ? item : mapping))
    mappingName.value = item.name
    selectedOntologyId.value = item.ontology_id
    await loadOntologyAssets(item.ontology_id, controller.signal)
    if (controller.signal.aborted || selectedMappingId.value !== value) return
    const revision =
      item.status === 'PUBLISHED'
        ? await mappingsApi.published(item.id, controller.signal)
        : await mappingsApi.draft(item.id, controller.signal)
    if (controller.signal.aborted || selectedMappingId.value !== value) return
    if (item.status === 'PUBLISHED') publishedRevision.value = revision
    else draftRevision.value = revision
    if (revision) {
      mappings.value = mappings.value.map((mapping) =>
        mapping.id === value ? { ...mapping, edit_revision: revision.edit_revision } : mapping,
      )
      entityMaps.value = revision.entity_maps.map(normalizeEntityMap)
      relationMaps.value = revision.rel_maps.map(normalizeRelationMap)
    }
    step.value = item.status === 'PUBLISHED' ? 5 : 3
  } catch (error: unknown) {
    if (!controller.signal.aborted && !isCanceled(error)) actionError.value = describeError(error)
  }
}
function serializeDraft(): S['MappingRevisionCreate'] {
  return {
    entity_maps: entityMaps.value.map((item) => ({
      entity_type: item.entity_type,
      table: item.table,
      schema: item.schema,
      field_maps: item.field_maps.map((field) => ({ ...field })),
      key_fields: [...item.key_fields],
      match_keys: [...item.match_keys],
    })),
    rel_maps: relationMaps.value.map((item) => ({
      relation_type: item.relation_type,
      mode: item.mode,
      table: item.table,
      schema: item.schema,
      fk_field: item.mode === 'FK' ? item.fk_field : null,
      source:
        item.mode === 'FK'
          ? null
          : {
              field: item.source_field,
              ref_table: item.source_ref_table,
              ref_field: item.source_ref_field,
              type_field: item.source_type_field || null,
              candidates: item.source_candidates.map((candidate) => ({ ...candidate })),
              via:
                item.source_via_table && item.source_via_field
                  ? {
                      table: item.source_via_table,
                      field: item.source_via_field,
                      ref_field: item.source_via_ref_field || 'id',
                    }
                  : null,
            },
      target:
        item.mode === 'FK'
          ? null
          : {
              field: item.target_field,
              ref_table: item.target_ref_table,
              ref_field: item.target_ref_field,
              type_field: item.target_type_field || null,
              candidates: item.target_candidates.map((candidate) => ({ ...candidate })),
              via:
                item.target_via_table && item.target_via_field
                  ? {
                      table: item.target_via_table,
                      field: item.target_via_field,
                      ref_field: item.target_via_ref_field || 'id',
                    }
                  : null,
            },
      attributes: item.mode === 'ASSOCIATIVE' ? item.attributes : [],
    })),
  }
}
async function saveDraft(): Promise<MappingRevision | null> {
  if (!canSaveDraft.value) {
    actionError.value = t('dataAccess.mapping.errors.incomplete')
    return null
  }
  const generation = selectionGeneration
  const draft = serializeDraft()
  let mapping = selectedMapping.value
  let revision: MappingRevision | null
  if (!mapping) {
    const ontologyId = selectedOntologyId.value
    if (ontologyId === null) return null
    const data = await mappingsApi.create({
      name: mappingName.value.trim(),
      ontology_id: ontologyId,
      draft,
    })
    if (generation !== selectionGeneration) return null
    mapping = data
    mappings.value = [data, ...mappings.value.filter((item) => item.id !== data.id)]
    selectedMappingId.value = data.id
    revision = await mappingsApi.draft(mapping.id)
    if (generation !== selectionGeneration) return null
    if (!revision) throw { code: 'KG.REVISION_NOT_FOUND' }
    if (revision.edit_revision !== mapping.edit_revision) {
      throw {
        code: 'KG.REVISION_CONFLICT',
        params: {
          resource: mapping.name,
          expected: mapping.edit_revision,
          actual: revision.edit_revision,
        },
      }
    }
  } else {
    revision = await mappingsApi.saveDraft(mapping.id, {
      draft,
      if_match: mapping.current_revision,
      if_edit_match: mapping.edit_revision,
    })
  }
  if (generation !== selectionGeneration) return null
  mappings.value = mappings.value.map((item) =>
    item.id === mapping.id ? { ...item, edit_revision: revision.edit_revision } : item,
  )
  draftRevision.value = revision
  notice.value = t('dataAccess.mapping.draftSaved')
  return revision
}
async function handleSaveDraft(): Promise<void> {
  if (working.value) return
  const generation = selectionGeneration
  working.value = true
  actionError.value = ''
  notice.value = ''
  try {
    await saveDraft()
  } catch (error: unknown) {
    if (generation === selectionGeneration && !isCanceled(error))
      actionError.value = describeError(error)
  } finally {
    if (generation === selectionGeneration) working.value = false
  }
}
async function loadLatestMetadata(datasourceId: number): Promise<void> {
  const generation = selectionGeneration
  const data = await metadataApi.latest(datasourceId, lifecycleController?.signal)
  if (generation !== selectionGeneration || selectedDatasourceId.value !== datasourceId) return
  catalog.value = loadCatalog(data.catalog)
  metadataRevision.value = data.revision
  selectedSampleTable.value = null
  samplePreview.value = null
}
async function captureMetadata(): Promise<void> {
  if (!selectedDatasourceId.value || working.value) return
  const generation = selectionGeneration
  const datasourceId = selectedDatasourceId.value
  working.value = true
  actionError.value = ''
  notice.value = ''
  try {
    await metadataApi.capture(datasourceId)
    if (generation !== selectionGeneration) return
    await loadLatestMetadata(datasourceId)
    if (generation !== selectionGeneration) return
    notice.value = t('dataAccess.mapping.metadataCaptured')
  } catch (error: unknown) {
    if (generation === selectionGeneration && !isCanceled(error))
      actionError.value = describeError(error)
  } finally {
    if (generation === selectionGeneration) working.value = false
  }
}
async function chooseDatasource(value: number | null): Promise<void> {
  const generation = selectionGeneration
  selectedDatasourceId.value = value
  catalog.value = null
  metadataRevision.value = null
  samplePreview.value = null
  entityMaps.value = entityMaps.value.map((item) => ({
    ...item,
    table: '',
    schema: 'main',
    key_fields: [],
    field_maps: item.field_maps.map((field) => ({ ...field, source_field: '' })),
  }))
  relationMaps.value = relationMaps.value.map((item) => ({
    ...item,
    table: '',
    schema: 'main',
    fk_field: '',
    source_field: '',
    source_ref_table: '',
    source_type_field: '',
    source_candidates: [],
    source_via_table: '',
    source_via_field: '',
    target_field: '',
    target_ref_table: '',
    target_type_field: '',
    target_candidates: [],
    target_via_table: '',
    target_via_field: '',
    attributes: item.attributes.map((attribute) => ({ ...attribute, field: '' })),
  }))
  invalidatePreview()
  if (!value) return
  working.value = true
  actionError.value = ''
  try {
    await loadLatestMetadata(value)
  } catch (error: unknown) {
    if (generation === selectionGeneration && !isCanceled(error)) {
      if (errorCode(error) === 'KG.RESOURCE_NOT_FOUND')
        notice.value = t('dataAccess.mapping.metadataMissing')
      else actionError.value = describeError(error)
    }
  } finally {
    if (generation === selectionGeneration) working.value = false
  }
}
async function fetchSamplePreview(): Promise<void> {
  if (!selectedDatasourceId.value || !selectedSampleTable.value || working.value) return
  const generation = selectionGeneration
  working.value = true
  actionError.value = ''
  try {
    const parsed = tableParts(selectedSampleTable.value)
    const result = await datasourcesApi.preview(
      {
        datasource_id: selectedDatasourceId.value,
        table: parsed.table,
        schema: parsed.schema,
        limit: 20,
        offset: 0,
      },
      lifecycleController?.signal,
    )
    if (generation !== selectionGeneration) return
    samplePreview.value = result
  } catch (error: unknown) {
    if (generation === selectionGeneration && !isCanceled(error))
      actionError.value = describeError(error)
  } finally {
    if (generation === selectionGeneration) working.value = false
  }
}
async function runCompile(): Promise<void> {
  if (!selectedDatasourceId.value || !canSaveDraft.value || working.value) return
  const generation = selectionGeneration
  const datasourceId = selectedDatasourceId.value
  working.value = true
  actionError.value = ''
  notice.value = ''
  preview.value = null
  try {
    if (selectedMapping.value?.status !== 'PUBLISHED' && !(await saveDraft())) return
    if (generation !== selectionGeneration || !selectedMapping.value) return
    const mapping = selectedMapping.value
    const result = await mappingsApi.compile(mapping.id, {
      datasource_id: datasourceId,
      limit: Math.max(1, Math.min(100, sampleLimit.value ?? 20)),
      use_draft: mapping.status !== 'PUBLISHED',
    })
    if (generation !== selectionGeneration) return
    preview.value = result
    step.value = 4
  } catch (error: unknown) {
    if (generation === selectionGeneration && !isCanceled(error))
      actionError.value = describeError(error)
  } finally {
    if (generation === selectionGeneration) working.value = false
  }
}
async function publishMapping(): Promise<void> {
  if (!canPublish.value || working.value || !selectedMapping.value) return
  const generation = selectionGeneration
  const mapping = selectedMapping.value
  working.value = true
  actionError.value = ''
  notice.value = ''
  try {
    const saved = await saveDraft()
    if (!saved || generation !== selectionGeneration) return
    const data = await mappingsApi.publish(saved.mapping_id, {
      if_match: mapping.current_revision,
      if_edit_match: saved.edit_revision,
    })
    if (generation !== selectionGeneration) return
    publishedRevision.value = data
    const published: Mapping = {
      ...mapping,
      status: 'PUBLISHED',
      current_revision: data.revision,
      edit_revision: data.edit_revision,
    }
    mappings.value = mappings.value.map((item) => (item.id === published.id ? published : item))
    step.value = 5
    notice.value = t('dataAccess.mapping.published')
  } catch (error: unknown) {
    if (generation === selectionGeneration && !isCanceled(error))
      actionError.value = describeError(error)
  } finally {
    if (generation === selectionGeneration) working.value = false
  }
}
async function startRun(): Promise<void> {
  if (!canRun.value || !selectedDatasourceId.value || !publishedRevision.value || working.value)
    return
  const generation = selectionGeneration
  working.value = true
  actionError.value = ''
  notice.value = ''
  try {
    const result = await extractionApi.start({
      mapping_revision_id: publishedRevision.value.id,
      datasource_id: selectedDatasourceId.value,
      namespace: namespace.value.trim() || selectedOntology.value?.iri || 'https://example.org/kg/',
    })
    if (generation !== selectionGeneration) return
    runResult.value = result
    notice.value = t('dataAccess.mapping.runStarted', { id: runResult.value.run.id })
  } catch (error: unknown) {
    if (generation === selectionGeneration && !isCanceled(error))
      actionError.value = describeError(error)
  } finally {
    if (generation === selectionGeneration) working.value = false
  }
}
function gotoStep(target: number): void {
  if (target === 1 || target <= step.value) step.value = target
  else if (target === 2 && selectedOntologyId.value) step.value = target
  else if (target === 3 && selectedOntologyId.value && selectedDatasourceId.value && catalog.value)
    step.value = target
  else if (target === 4 && preview.value) step.value = target
  else if (target === 5 && selectedMapping.value) step.value = target
}
function nextStep(): void {
  if (step.value === 1 && selectedOntologyId.value && mappingName.value.trim()) step.value = 2
  else if (step.value === 2 && selectedDatasourceId.value && catalog.value) step.value = 3
  else if (step.value === 3) void runCompile()
  else if (step.value === 4 && preview.value) step.value = 5
}
function previousStep(): void {
  if (step.value > 1) step.value -= 1
}
function displayCell(value: unknown): string {
  if (value === null || value === undefined) return t('dataAccess.mapping.nullValue')
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean')
    return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return t('dataAccess.mapping.unavailableValue')
  }
}
function statusLabel(status: string): string {
  const key = `dataAccess.mapping.cellStatus.${status}`
  const translated = t(key)
  return translated === key ? status : translated
}
function relationModeOptions() {
  return (['FK', 'JUNCTION', 'ASSOCIATIVE'] as RelationMode[]).map((value) => ({
    value,
    label: t(`dataAccess.mapping.relationModes.${value}`),
  }))
}
function transformOptions() {
  return (['IDENTITY', 'DATE', 'DECIMAL'] as TransformKind[]).map((value) => ({
    value,
    label: t(`dataAccess.mapping.transforms.${value}`),
  }))
}
function nullPolicyOptions() {
  return (['REQUIRED', 'NULLABLE', 'DEFAULT', 'SKIP'] as NullPolicy[]).map((value) => ({
    value,
    label: t(`dataAccess.mapping.nullPolicies.${value}`),
  }))
}
function ontologyOption(item: Ontology) {
  return { label: `${resourceLabel(item)} · ${item.name}`, value: item.id }
}
function datasourceOption(item: Datasource) {
  return { label: `${item.name} · ${item.kind}`, value: item.id }
}
function mappingOption(item: Mapping) {
  return { label: `${item.name} · ${t(`resourceStatus.${item.status}`)}`, value: item.id }
}
function previewTitle(name: string, table: string) {
  return `${name} · ${table}`
}
watch(
  [entityMaps, relationMaps],
  () => {
    preview.value = null
  },
  { deep: true },
)
onMounted(() => void loadInitial())
onBeforeUnmount(() => {
  selectionGeneration += 1
  lifecycleController?.abort()
  selectionController?.abort()
  assetController?.abort()
})
</script>

<template>
  <section class="mapping-page">
    <PageHeader :title="t('page.mappingWizard')" :description="t('dataAccess.mapping.description')">
      <template #actions>
        <n-select
          :value="selectedMappingId"
          :options="[
            ...mappings.map(mappingOption),
            { label: t('dataAccess.mapping.newMapping'), value: 0 },
          ]"
          :placeholder="t('dataAccess.mapping.selectMapping')"
          clearable
          class="mapping-picker"
          @update:value="selectMapping"
        />
        <n-button secondary :disabled="working" @click="newMapping">{{
          t('dataAccess.mapping.newMapping')
        }}</n-button>
        <n-button
          v-if="selectedMapping && selectedMapping.status !== 'PUBLISHED'"
          :disabled="!canSaveDraft || working"
          :loading="working"
          @click="handleSaveDraft"
          >{{ t('dataAccess.mapping.saveDraft') }}</n-button
        >
      </template>
    </PageHeader>

    <n-alert v-if="loadError" type="error" :show-icon="true">{{ loadError }}</n-alert>
    <n-alert v-if="actionError" type="error" :show-icon="true">{{ actionError }}</n-alert>
    <n-alert v-if="notice" type="info" :show-icon="true">{{ notice }}</n-alert>

    <n-spin :show="loading">
      <div class="wizard-shell">
        <div class="wizard-heading">
          <div class="wizard-title">
            <h3>
              {{ selectedMapping?.name ?? (mappingName || t('dataAccess.mapping.newMapping')) }}
            </h3>
            <n-tag
              size="small"
              :type="selectedMapping?.status === 'PUBLISHED' ? 'success' : 'warning'"
              >{{ savedRevisionLabel }}</n-tag
            >
          </div>
          <div class="wizard-steps" role="list">
            <button
              v-for="number in [1, 2, 3, 4, 5]"
              :key="number"
              type="button"
              class="wizard-step"
              :class="{ active: step === number, completed: step > number }"
              :disabled="number > step + 1"
              @click="gotoStep(number)"
            >
              <span class="step-number">{{ number }}</span
              ><span>{{ t('dataAccess.mapping.steps.' + number) }}</span>
            </button>
          </div>
          <div v-if="selectedOntology" class="ontology-version">
            {{ t('dataAccess.mapping.ontology') }}: {{ resourceLabel(selectedOntology) }}
            <span class="mono">{{ selectedOntology.current_revision }}</span>
            <span v-if="selectedOntology.status === 'PUBLISHED'"
              >· {{ t('dataAccess.mapping.publishedStatus') }}</span
            >
            <span v-else>· {{ t('dataAccess.mapping.ontologyNotPublished') }}</span>
          </div>
        </div>

        <div v-if="step === 1" class="step-content">
          <n-card :title="t('dataAccess.mapping.targetOntology')" size="small">
            <div class="form-grid">
              <label class="field-group"
                ><span>{{ t('dataAccess.mapping.mappingName') }}</span
                ><n-input
                  v-model:value="mappingName"
                  :disabled="Boolean(selectedMapping)"
                  :placeholder="t('dataAccess.mapping.mappingNamePlaceholder')"
              /></label>
              <label class="field-group"
                ><span>{{ t('dataAccess.mapping.ontologySelector') }}</span>
                <n-select
                  :value="selectedOntologyId"
                  :options="ontologies.map(ontologyOption)"
                  :placeholder="t('dataAccess.mapping.chooseOntology')"
                  :disabled="Boolean(selectedMapping)"
                  filterable
                  @update:value="chooseOntology"
                />
              </label>
            </div>
            <div
              v-if="selectedOntologyId && !entityTypes.length && !relationTypes.length"
              class="inline-empty"
            >
              <n-empty :description="t('dataAccess.mapping.noOntologyResources')" size="small" />
            </div>
            <div v-else-if="selectedOntologyId" class="resource-summary">
              <span>{{
                t('dataAccess.mapping.entityResources', { count: entityTypes.length })
              }}</span>
              <span>{{
                t('dataAccess.mapping.relationResources', { count: relationTypes.length })
              }}</span>
              <span v-if="selectedOntology?.status !== 'PUBLISHED'" class="warning-copy">{{
                t('dataAccess.mapping.publishOntologyFirst')
              }}</span>
            </div>
          </n-card>
          <n-empty
            v-if="!loading && ontologies.length === 0"
            class="page-empty"
            :description="t('dataAccess.mapping.noOntologies')"
          />
        </div>

        <div v-else-if="step === 2" class="step-content">
          <n-card :title="t('dataAccess.mapping.sourceDatasource')" size="small">
            <div class="form-grid datasource-form">
              <label class="field-group"
                ><span>{{ t('dataAccess.mapping.datasourceSelector') }}</span>
                <n-select
                  :value="selectedDatasourceId"
                  :options="datasources.map(datasourceOption)"
                  :placeholder="t('dataAccess.mapping.chooseDatasource')"
                  :disabled="working"
                  filterable
                  @update:value="chooseDatasource"
                />
              </label>
              <div class="field-group">
                <span>{{ t('dataAccess.mapping.metadataSnapshot') }}</span>
                <div class="inline-actions">
                  <n-tag v-if="metadataRevision !== null" type="success" size="small">{{
                    t('dataAccess.mapping.snapshotRevision', { revision: metadataRevision })
                  }}</n-tag>
                  <span v-else class="muted-copy">{{
                    t('dataAccess.mapping.metadataMissing')
                  }}</span>
                  <n-button
                    size="small"
                    :disabled="!selectedDatasourceId || working"
                    :loading="working"
                    @click="captureMetadata"
                    >{{ t('dataAccess.mapping.captureMetadata') }}</n-button
                  >
                </div>
              </div>
            </div>
            <div v-if="catalog" class="catalog-summary">
              <span>{{ t('dataAccess.mapping.catalogTables', { count: metadataTableCount }) }}</span
              ><span>{{
                t('dataAccess.mapping.catalogColumns', { count: metadataColumnCount })
              }}</span>
            </div>
            <n-empty
              v-else-if="!loading && selectedDatasourceId && !working"
              class="inline-empty"
              :description="t('dataAccess.mapping.captureRequired')"
            />
            <n-empty
              v-else-if="!loading && datasources.length === 0"
              class="inline-empty"
              :description="t('dataAccess.mapping.noDatasources')"
            />
          </n-card>
          <n-card v-if="catalog" :title="t('dataAccess.mapping.sampleTable')" size="small">
            <div class="sample-toolbar">
              <n-select
                v-model:value="selectedSampleTable"
                :options="tableOptions"
                :placeholder="t('dataAccess.mapping.chooseTable')"
                filterable
              /><n-button
                :disabled="!selectedSampleTable || working"
                :loading="working"
                @click="fetchSamplePreview"
                >{{ t('dataAccess.mapping.previewSource') }}</n-button
              >
            </div>
            <div v-if="samplePreview" class="table-scroll sample-table">
              <table>
                <thead>
                  <tr>
                    <th v-for="column in samplePreview.columns" :key="column.name">
                      {{ column.name }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, rowIndex) in samplePreview.rows" :key="rowIndex">
                    <td v-for="column in samplePreview.columns" :key="column.name">
                      {{ displayCell(row[column.name]) }}
                    </td>
                  </tr>
                </tbody>
              </table>
              <div v-if="samplePreview.truncated" class="table-footnote">
                {{ t('dataAccess.mapping.sampleTruncated') }}
              </div>
            </div>
          </n-card>
        </div>

        <div v-else-if="step === 3" class="step-content">
          <n-card size="small">
            <template #header
              ><div class="card-heading">
                <div>
                  <h4>{{ t('dataAccess.mapping.designTitle') }}</h4>
                  <p>{{ t('dataAccess.mapping.designHint') }}</p>
                </div>
                <div
                  class="view-switch"
                  role="group"
                  :aria-label="t('dataAccess.mapping.designViews')"
                >
                  <n-button
                    size="small"
                    :type="viewMode === 'graph' ? 'primary' : 'default'"
                    @click="viewMode = 'graph'"
                    >{{ t('dataAccess.mapping.graphView') }}</n-button
                  ><n-button
                    size="small"
                    :type="viewMode === 'table' ? 'primary' : 'default'"
                    @click="viewMode = 'table'"
                    >{{ t('dataAccess.mapping.tableView') }}</n-button
                  >
                </div>
              </div></template
            >
            <div v-if="viewMode === 'graph' && entityMaps.length" class="map-overview">
              <div v-for="map in entityMaps" :key="'flow-' + map.localId" class="map-flow">
                <div class="flow-node source-node">
                  <span class="node-kicker">{{ t('dataAccess.mapping.sourceTable') }}</span
                  ><strong>{{
                    map.table ? map.schema + '.' + map.table : t('dataAccess.mapping.unselected')
                  }}</strong>
                </div>
                <svg class="flow-arrow" viewBox="0 0 92 28" aria-hidden="true">
                  <path d="M2 14h80m-8-7 8 7-8 7" />
                </svg>
                <div class="flow-node target-node">
                  <span class="node-kicker">{{ t('dataAccess.mapping.targetType') }}</span
                  ><strong>{{ map.entity_type }}</strong>
                </div>
                <n-tag
                  size="small"
                  :type="
                    map.field_maps.every((field) => field.source_field) ? 'success' : 'warning'
                  "
                  >{{
                    t('dataAccess.mapping.configuredFields', {
                      ready: map.field_maps.filter((field) => field.source_field).length,
                      total: map.field_maps.length,
                    })
                  }}</n-tag
                >
              </div>
              <div v-if="relationMaps.length" class="relation-overview">
                <span class="node-kicker">{{ t('dataAccess.mapping.relationMappings') }}</span
                ><n-tag
                  v-for="map in relationMaps"
                  :key="map.localId"
                  size="small"
                  :type="map.table ? 'success' : 'warning'"
                  >{{ map.relation_type }} ·
                  {{ map.table || t('dataAccess.mapping.unconfigured') }}</n-tag
                >
              </div>
              <div v-else-if="relationTypes.length" class="pending-relations">
                <span class="node-kicker">{{ t('dataAccess.mapping.unmappedRelations') }}</span
                ><span>{{ relationTypes.map((item) => item.name).join(' · ') }}</span>
              </div>
            </div>
            <n-empty
              v-if="!entityMaps.length"
              class="inline-empty"
              :description="t('dataAccess.mapping.noEntityMaps')"
              size="small"
            />
            <div v-else-if="viewMode === 'table'" class="table-scroll overview-table">
              <table>
                <thead>
                  <tr>
                    <th>{{ t('dataAccess.mapping.targetType') }}</th>
                    <th>{{ t('dataAccess.mapping.sourceTable') }}</th>
                    <th>{{ t('dataAccess.mapping.mappingProgress') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="map in entityMaps" :key="'overview-' + map.localId">
                    <td>{{ map.entity_type }}</td>
                    <td>
                      {{
                        map.table
                          ? map.schema + '.' + map.table
                          : t('dataAccess.mapping.unselected')
                      }}
                    </td>
                    <td>
                      {{
                        t('dataAccess.mapping.configuredFields', {
                          ready: map.field_maps.filter((field) => field.source_field).length,
                          total: map.field_maps.length,
                        })
                      }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </n-card>

          <n-card :title="t('dataAccess.mapping.entityMappings')" size="small">
            <n-empty
              v-if="entityTypes.length === 0"
              :description="t('dataAccess.mapping.noEntityResources')"
              size="small"
            />
            <div v-else class="editors">
              <section v-for="map in entityMaps" :key="map.localId" class="editor-card">
                <div class="editor-heading">
                  <div>
                    <strong>{{
                      t('dataAccess.mapping.entityTarget', { name: map.entity_type })
                    }}</strong
                    ><span class="subtle-copy">{{
                      entityTypes.find((item) => item.name === map.entity_type)?.iri
                    }}</span>
                  </div>
                  <n-button
                    v-if="selectedMapping?.status !== 'PUBLISHED'"
                    size="small"
                    quaternary
                    type="error"
                    @click="removeEntityMap(map.localId)"
                    >{{ t('common.delete') }}</n-button
                  >
                </div>
                <div class="map-selectors">
                  <label class="field-group"
                    ><span>{{ t('dataAccess.mapping.targetType') }}</span
                    ><n-select
                      :value="map.entity_type"
                      :options="entityOptions"
                      :disabled="selectedMapping?.status === 'PUBLISHED'"
                      @update:value="(value) => changeEntityType(map, value)"
                  /></label>
                  <label class="field-group"
                    ><span>{{ t('dataAccess.mapping.sourceTable') }}</span
                    ><n-select
                      :value="tableValue(map.schema, map.table)"
                      :options="tableOptions"
                      :disabled="selectedMapping?.status === 'PUBLISHED'"
                      :placeholder="t('dataAccess.mapping.chooseTable')"
                      filterable
                      @update:value="(value) => setEntityTable(map, value)"
                  /></label>
                </div>
                <div v-if="getTable(map.schema, map.table)" class="table-scroll field-table">
                  <table>
                    <thead>
                      <tr>
                        <th>{{ t('dataAccess.mapping.targetAttribute') }}</th>
                        <th>{{ t('dataAccess.mapping.sourceField') }}</th>
                        <th>{{ t('dataAccess.mapping.transform') }}</th>
                        <th>{{ t('dataAccess.mapping.nullPolicy') }}</th>
                        <th>{{ t('dataAccess.mapping.defaultValue') }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="field in map.field_maps" :key="field.target_attr">
                        <td>
                          <span class="mono">{{ field.target_attr }}</span>
                        </td>
                        <td>
                          <n-select
                            v-model:value="field.source_field"
                            :options="fieldOptions(map.schema, map.table)"
                            :disabled="selectedMapping?.status === 'PUBLISHED'"
                            :placeholder="t('dataAccess.mapping.chooseSourceField')"
                            clearable
                            filterable
                            @update:value="invalidatePreview"
                          />
                        </td>
                        <td>
                          <n-select
                            v-model:value="field.transform"
                            :options="transformOptions()"
                            :disabled="selectedMapping?.status === 'PUBLISHED'"
                            @update:value="invalidatePreview"
                          />
                        </td>
                        <td>
                          <n-select
                            v-model:value="field.null_policy"
                            :options="nullPolicyOptions()"
                            :disabled="selectedMapping?.status === 'PUBLISHED'"
                            @update:value="invalidatePreview"
                          />
                        </td>
                        <td>
                          <n-input
                            v-if="field.null_policy === 'DEFAULT'"
                            v-model:value="field.default_value"
                            :disabled="selectedMapping?.status === 'PUBLISHED'"
                            :placeholder="t('dataAccess.mapping.defaultValue')"
                            @update:value="invalidatePreview"
                          /><span v-else class="muted-copy">{{
                            t('dataAccess.mapping.notApplicable')
                          }}</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-if="getTable(map.schema, map.table)" class="key-fields">
                  <span>{{ t('dataAccess.mapping.keyFields') }}</span
                  ><label
                    v-for="column in tableColumns(map.schema, map.table)"
                    :key="column.name"
                    class="key-option"
                    ><input
                      type="checkbox"
                      :checked="map.key_fields.includes(column.name)"
                      :disabled="selectedMapping?.status === 'PUBLISHED'"
                      @change="
                        toggleKeyField(
                          map,
                          column.name,
                          ($event.target as HTMLInputElement).checked,
                        )
                      "
                    /><span class="mono">{{ column.name }}</span
                    ><span v-if="column.primary_key" class="muted-copy">{{
                      t('dataAccess.mapping.primaryKey')
                    }}</span></label
                  ><span v-if="map.key_fields.length === 0" class="warning-copy">{{
                    t('dataAccess.mapping.noStableKey')
                  }}</span>
                </div>
                <div v-if="getTable(map.schema, map.table)" class="key-fields">
                  <span>{{ t('dataAccess.mapping.matchKeys') }}</span
                  ><label
                    v-for="column in tableColumns(map.schema, map.table)"
                    :key="'mk-' + column.name"
                    class="key-option"
                    ><input
                      type="checkbox"
                      :checked="map.match_keys.includes(column.name)"
                      :disabled="selectedMapping?.status === 'PUBLISHED'"
                      @change="
                        toggleMatchKey(
                          map,
                          column.name,
                          ($event.target as HTMLInputElement).checked,
                        )
                      "
                    /><span class="mono">{{ column.name }}</span></label
                  ><span v-if="map.match_keys.length" class="muted-copy">{{
                    t('dataAccess.mapping.matchKeysHint')
                  }}</span>
                </div>
              </section>
            </div>
            <n-button
              v-if="entityTypes.length && selectedMapping?.status !== 'PUBLISHED'"
              secondary
              :disabled="entityMaps.length >= entityTypes.length"
              @click="addEntityMap"
              >{{ t('dataAccess.mapping.addEntityMapping') }}</n-button
            >
          </n-card>

          <n-card :title="t('dataAccess.mapping.relationMappings')" size="small">
            <n-empty
              v-if="relationTypes.length === 0"
              :description="t('dataAccess.mapping.noRelationResources')"
              size="small"
            />
            <div v-else class="editors">
              <section
                v-for="map in relationMaps"
                :key="map.localId"
                class="editor-card relation-editor"
              >
                <div class="editor-heading">
                  <strong>{{
                    t('dataAccess.mapping.relationTarget', { name: map.relation_type })
                  }}</strong
                  ><n-button
                    v-if="selectedMapping?.status !== 'PUBLISHED'"
                    size="small"
                    quaternary
                    type="error"
                    @click="removeRelationMap(map.localId)"
                    >{{ t('common.delete') }}</n-button
                  >
                </div>
                <div class="map-selectors three-columns">
                  <label class="field-group"
                    ><span>{{ t('dataAccess.mapping.relationType') }}</span
                    ><n-select
                      :value="map.relation_type"
                      :options="relationOptions"
                      :disabled="selectedMapping?.status === 'PUBLISHED'"
                      @update:value="(value) => changeRelationType(map, value)"
                  /></label>
                  <label class="field-group"
                    ><span>{{ t('dataAccess.mapping.relationMode') }}</span
                    ><n-select
                      :value="map.mode"
                      :options="relationModeOptions()"
                      :disabled="selectedMapping?.status === 'PUBLISHED'"
                      @update:value="
                        (value) => {
                          map.mode = value
                          invalidatePreview()
                        }
                      "
                  /></label>
                  <label class="field-group"
                    ><span>{{ t('dataAccess.mapping.sourceTable') }}</span
                    ><n-select
                      :value="tableValue(map.schema, map.table)"
                      :options="tableOptions"
                      :disabled="selectedMapping?.status === 'PUBLISHED'"
                      :placeholder="t('dataAccess.mapping.chooseTable')"
                      filterable
                      @update:value="(value) => setRelationTable(map, value)"
                  /></label>
                </div>
                <div v-if="map.mode === 'FK'" class="endpoint-grid">
                  <label class="field-group"
                    ><span>{{ t('dataAccess.mapping.foreignKeyField') }}</span
                    ><n-select
                      v-model:value="map.fk_field"
                      :options="relationFieldOptions(map)"
                      :disabled="selectedMapping?.status === 'PUBLISHED'"
                      :placeholder="t('dataAccess.mapping.chooseSourceField')"
                      clearable
                      @update:value="invalidatePreview"
                  /></label>
                </div>
                <div v-else class="endpoint-grid">
                  <div class="endpoint-card">
                    <strong>{{ t('dataAccess.mapping.sourceEndpoint') }}</strong
                    ><label class="field-group"
                      ><span>{{ t('dataAccess.mapping.endpointField') }}</span
                      ><n-select
                        v-model:value="map.source_field"
                        :options="relationFieldOptions(map)"
                        :disabled="selectedMapping?.status === 'PUBLISHED'"
                        :placeholder="t('dataAccess.mapping.chooseSourceField')"
                        clearable
                        @update:value="invalidatePreview" /></label
                    ><label class="field-group"
                      ><span>{{ t('dataAccess.mapping.referencedTable') }}</span
                      ><n-select
                        v-model:value="map.source_ref_table"
                        :options="refTableOptions()"
                        :disabled="selectedMapping?.status === 'PUBLISHED'"
                        filterable
                        @update:value="invalidatePreview" /></label
                    ><label class="field-group"
                      ><span>{{ t('dataAccess.mapping.referencedField') }}</span
                      ><n-input
                        v-model:value="map.source_ref_field"
                        :disabled="selectedMapping?.status === 'PUBLISHED'"
                        @update:value="invalidatePreview"
                    /></label>
                    <details class="poly-editor">
                      <summary>{{ t('dataAccess.mapping.polyEndpoint') }}</summary>
                      <label class="field-group"
                        ><span>{{ t('dataAccess.mapping.discriminator') }}</span
                        ><n-input
                          v-model:value="map.source_type_field"
                          :disabled="selectedMapping?.status === 'PUBLISHED'"
                          :placeholder="t('dataAccess.mapping.discriminatorHint')"
                          @update:value="invalidatePreview"
                      /></label>
                      <label class="field-group"
                        ><span>{{ t('dataAccess.mapping.viaTable') }}</span
                        ><n-select
                          v-model:value="map.source_via_table"
                          :options="refTableOptions()"
                          :disabled="selectedMapping?.status === 'PUBLISHED'"
                          clearable
                          filterable
                          @update:value="invalidatePreview" /></label
                      ><label class="field-group"
                        ><span>{{ t('dataAccess.mapping.viaField') }}</span
                        ><n-input
                          v-model:value="map.source_via_field"
                          :disabled="
                            selectedMapping?.status === 'PUBLISHED' || !map.source_via_table
                          "
                          @update:value="invalidatePreview"
                      /></label>
                      <div class="candidate-rows">
                        <span>{{ t('dataAccess.mapping.candidates') }}</span>
                        <div
                          v-for="(candidate, candidateIndex) in map.source_candidates"
                          :key="candidateIndex"
                          class="candidate-row"
                        >
                          <n-select
                            v-model:value="candidate.field"
                            :options="candidateFieldOptions(map, map.source_via_table)"
                            :disabled="selectedMapping?.status === 'PUBLISHED'"
                            :placeholder="t('dataAccess.mapping.endpointField')"
                            @update:value="invalidatePreview"
                          />
                          <n-select
                            v-model:value="candidate.ref_table"
                            :options="refTableOptions()"
                            :disabled="selectedMapping?.status === 'PUBLISHED'"
                            :placeholder="t('dataAccess.mapping.referencedTable')"
                            filterable
                            @update:value="invalidatePreview"
                          />
                          <n-input
                            v-model:value="candidate.when"
                            :disabled="selectedMapping?.status === 'PUBLISHED'"
                            :placeholder="t('dataAccess.mapping.whenValue')"
                            @update:value="invalidatePreview"
                          />
                          <n-button
                            quaternary
                            size="tiny"
                            :disabled="selectedMapping?.status === 'PUBLISHED'"
                            @click="removeEndpointCandidate(map, 'source', candidateIndex)"
                            >{{ t('dataAccess.mapping.removeCandidate') }}</n-button
                          >
                        </div>
                        <n-button
                          size="tiny"
                          secondary
                          :disabled="selectedMapping?.status === 'PUBLISHED'"
                          @click="addEndpointCandidate(map, 'source')"
                          >{{ t('dataAccess.mapping.addCandidate') }}</n-button
                        >
                      </div>
                    </details>
                  </div>
                  <div class="endpoint-card">
                    <strong>{{ t('dataAccess.mapping.targetEndpoint') }}</strong
                    ><label class="field-group"
                      ><span>{{ t('dataAccess.mapping.endpointField') }}</span
                      ><n-select
                        v-model:value="map.target_field"
                        :options="relationFieldOptions(map)"
                        :disabled="selectedMapping?.status === 'PUBLISHED'"
                        :placeholder="t('dataAccess.mapping.chooseSourceField')"
                        clearable
                        @update:value="invalidatePreview" /></label
                    ><label class="field-group"
                      ><span>{{ t('dataAccess.mapping.referencedTable') }}</span
                      ><n-select
                        v-model:value="map.target_ref_table"
                        :options="refTableOptions()"
                        :disabled="selectedMapping?.status === 'PUBLISHED'"
                        filterable
                        @update:value="invalidatePreview" /></label
                    ><label class="field-group"
                      ><span>{{ t('dataAccess.mapping.referencedField') }}</span
                      ><n-input
                        v-model:value="map.target_ref_field"
                        :disabled="selectedMapping?.status === 'PUBLISHED'"
                        @update:value="invalidatePreview"
                    /></label>
                    <details class="poly-editor">
                      <summary>{{ t('dataAccess.mapping.polyEndpoint') }}</summary>
                      <label class="field-group"
                        ><span>{{ t('dataAccess.mapping.discriminator') }}</span
                        ><n-input
                          v-model:value="map.target_type_field"
                          :disabled="selectedMapping?.status === 'PUBLISHED'"
                          :placeholder="t('dataAccess.mapping.discriminatorHint')"
                          @update:value="invalidatePreview"
                      /></label>
                      <label class="field-group"
                        ><span>{{ t('dataAccess.mapping.viaTable') }}</span
                        ><n-select
                          v-model:value="map.target_via_table"
                          :options="refTableOptions()"
                          :disabled="selectedMapping?.status === 'PUBLISHED'"
                          clearable
                          filterable
                          @update:value="invalidatePreview" /></label
                      ><label class="field-group"
                        ><span>{{ t('dataAccess.mapping.viaField') }}</span
                        ><n-input
                          v-model:value="map.target_via_field"
                          :disabled="
                            selectedMapping?.status === 'PUBLISHED' || !map.target_via_table
                          "
                          @update:value="invalidatePreview"
                      /></label>
                      <div class="candidate-rows">
                        <span>{{ t('dataAccess.mapping.candidates') }}</span>
                        <div
                          v-for="(candidate, candidateIndex) in map.target_candidates"
                          :key="candidateIndex"
                          class="candidate-row"
                        >
                          <n-select
                            v-model:value="candidate.field"
                            :options="candidateFieldOptions(map, map.target_via_table)"
                            :disabled="selectedMapping?.status === 'PUBLISHED'"
                            :placeholder="t('dataAccess.mapping.endpointField')"
                            @update:value="invalidatePreview"
                          />
                          <n-select
                            v-model:value="candidate.ref_table"
                            :options="refTableOptions()"
                            :disabled="selectedMapping?.status === 'PUBLISHED'"
                            :placeholder="t('dataAccess.mapping.referencedTable')"
                            filterable
                            @update:value="invalidatePreview"
                          />
                          <n-input
                            v-model:value="candidate.when"
                            :disabled="selectedMapping?.status === 'PUBLISHED'"
                            :placeholder="t('dataAccess.mapping.whenValue')"
                            @update:value="invalidatePreview"
                          />
                          <n-button
                            quaternary
                            size="tiny"
                            :disabled="selectedMapping?.status === 'PUBLISHED'"
                            @click="removeEndpointCandidate(map, 'target', candidateIndex)"
                            >{{ t('dataAccess.mapping.removeCandidate') }}</n-button
                          >
                        </div>
                        <n-button
                          size="tiny"
                          secondary
                          :disabled="selectedMapping?.status === 'PUBLISHED'"
                          @click="addEndpointCandidate(map, 'target')"
                          >{{ t('dataAccess.mapping.addCandidate') }}</n-button
                        >
                      </div>
                    </details>
                  </div>
                </div>
                <div
                  v-if="map.mode === 'ASSOCIATIVE' && map.attributes.length"
                  class="attribute-maps"
                >
                  <span class="node-kicker">{{
                    t('dataAccess.mapping.associativeAttributes')
                  }}</span
                  ><label
                    v-for="attribute in map.attributes"
                    :key="attribute.attr"
                    class="field-group attribute-row"
                    ><span class="mono">{{ attribute.attr }}</span
                    ><n-select
                      :value="attribute.field || null"
                      :options="relationFieldOptions(map)"
                      :disabled="selectedMapping?.status === 'PUBLISHED'"
                      :placeholder="t('dataAccess.mapping.chooseSourceField')"
                      clearable
                      @update:value="
                        (value) => {
                          attribute.field = value ?? ''
                          invalidatePreview()
                        }
                      "
                  /></label>
                </div>
              </section>
            </div>
            <n-button
              v-if="relationTypes.length && selectedMapping?.status !== 'PUBLISHED'"
              secondary
              :disabled="relationMaps.length >= relationTypes.length"
              @click="addRelationMap"
              >{{ t('dataAccess.mapping.addRelationMapping') }}</n-button
            >
          </n-card>
        </div>

        <div v-else-if="step === 4" class="step-content">
          <div class="preview-toolbar">
            <div>
              <h3>{{ t('dataAccess.mapping.previewTitle') }}</h3>
              <p>{{ t('dataAccess.mapping.previewHint') }}</p>
            </div>
            <div class="inline-actions">
              <label class="limit-input"
                ><span>{{ t('dataAccess.mapping.sampleLimit') }}</span
                ><n-input-number v-model:value="sampleLimit" :min="1" :max="100" /></label
              ><n-button
                type="primary"
                :disabled="!canSaveDraft || !selectedDatasourceId || working"
                :loading="working"
                @click="runCompile"
                >{{ t('dataAccess.mapping.runPreview') }}</n-button
              >
            </div>
          </div>
          <div v-if="preview" class="stats-grid">
            <div class="stat-card">
              <strong>{{ preview.summary.entity_count ?? preview.entities.length }}</strong
              ><span>{{ t('dataAccess.mapping.entityMaps') }}</span>
            </div>
            <div class="stat-card">
              <strong>{{ preview.summary.relation_count ?? preview.relations.length }}</strong
              ><span>{{ t('dataAccess.mapping.relationMaps') }}</span>
            </div>
            <div class="stat-card" :class="resultErrorCount ? 'bad' : 'good'">
              <strong>{{ resultErrorCount }}</strong
              ><span>{{ t('dataAccess.mapping.fieldErrors') }}</span>
            </div>
            <div class="stat-card">
              <strong>{{ preview.onto_version }}</strong
              ><span>{{ t('dataAccess.mapping.ontologyRevision') }}</span>
            </div>
          </div>
          <n-alert
            v-if="preview"
            :type="resultErrorCount ? 'warning' : 'success'"
            :show-icon="true"
            >{{
              resultErrorCount
                ? t('dataAccess.mapping.previewHasErrors', { count: resultErrorCount })
                : t('dataAccess.mapping.previewPassed')
            }}</n-alert
          >
          <n-empty
            v-if="!preview"
            class="page-empty"
            :description="t('dataAccess.mapping.previewNotRun')"
          />
          <n-card
            v-for="entity in previewEntityRows"
            :key="entity.entity_type + entity.table"
            :title="previewTitle(entity.entity_type, entity.table)"
            size="small"
            class="preview-card"
          >
            <div class="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{{ t('dataAccess.mapping.rowIndex') }}</th>
                    <th>{{ t('dataAccess.mapping.sourceKey') }}</th>
                    <th v-for="cell in entity.rows[0]?.cells ?? []" :key="cell.target_attr">
                      {{ cell.target_attr }}<small>{{ cell.source_field }}</small>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in entity.rows" :key="row.row_index">
                    <td>{{ row.row_index + 1 }}</td>
                    <td class="mono">{{ row.source_key ?? t('dataAccess.mapping.nullValue') }}</td>
                    <td
                      v-for="cell in row.cells"
                      :key="cell.target_attr"
                      :class="'cell-' + cell.status"
                      :title="statusLabel(cell.status)"
                    >
                      {{ displayCell(cell.value) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-if="entity.errors.length" class="error-list">
              <div v-for="(item, index) in entity.errors" :key="index">
                <n-tag type="error" size="small">{{
                  recordOf(item).code ?? t('dataAccess.mapping.fieldError')
                }}</n-tag
                ><span>{{
                  recordOf(item).field ?? recordOf(item).level ?? entity.entity_type
                }}</span>
              </div>
            </div>
          </n-card>
          <n-card
            v-for="relation in previewRelationRows"
            :key="relation.relation_type + relation.table"
            :title="previewTitle(relation.relation_type, relation.table)"
            size="small"
            class="preview-card"
            ><div class="relation-result">
              <n-tag size="small">{{
                t('dataAccess.mapping.relationModes.' + relation.mode)
              }}</n-tag
              ><span>{{
                t('dataAccess.mapping.previewRows', { count: relation.rows.length })
              }}</span
              ><span v-if="relation.errors.length" class="warning-copy">{{
                t('dataAccess.mapping.previewErrorCount', { count: relation.errors.length })
              }}</span>
            </div></n-card
          >
        </div>

        <div v-else class="step-content">
          <n-card :title="t('dataAccess.mapping.publishAndRun')" size="small">
            <div v-if="selectedMapping?.status !== 'PUBLISHED'" class="publish-panel">
              <p>{{ t('dataAccess.mapping.publishHint') }}</p>
              <div class="publish-facts">
                <span>{{
                  t('dataAccess.mapping.configuredEntityCount', { count: entityMaps.length })
                }}</span
                ><span>{{
                  t('dataAccess.mapping.configuredRelationCount', { count: relationMaps.length })
                }}</span
                ><span>{{
                  t('dataAccess.mapping.previewErrorCount', { count: resultErrorCount })
                }}</span
                ><span v-if="selectedOntology">{{
                  t('dataAccess.mapping.ontologyRevisionToFreeze', {
                    revision: selectedOntology.current_revision,
                  })
                }}</span>
              </div>
              <n-alert
                v-if="selectedOntology?.status !== 'PUBLISHED'"
                type="warning"
                :show-icon="true"
                >{{ t('dataAccess.mapping.publishOntologyFirst') }}</n-alert
              >
              <n-alert v-else-if="!preview" type="info" :show-icon="true">{{
                t('dataAccess.mapping.previewBeforePublish')
              }}</n-alert>
              <n-alert v-else-if="!currentPreviewIsClean" type="warning" :show-icon="true">{{
                t('dataAccess.mapping.fixErrorsBeforePublish')
              }}</n-alert>
              <n-button
                type="primary"
                :disabled="!canPublish || working"
                :loading="working"
                @click="publishMapping"
                >{{ t('dataAccess.mapping.publishMapping') }}</n-button
              >
            </div>
            <div v-else class="publish-panel">
              <n-alert type="success" :show-icon="true">{{
                t('dataAccess.mapping.mappingPublished', {
                  revision: publishedRevision?.revision ?? selectedMapping.current_revision,
                  ontologyRevision:
                    publishedRevision?.onto_version ?? selectedOntology?.current_revision ?? 0,
                })
              }}</n-alert>
              <p>{{ t('dataAccess.mapping.publishedImmutable') }}</p>
              <label class="field-group namespace-field"
                ><span>{{ t('dataAccess.mapping.runNamespace') }}</span
                ><n-input v-model:value="namespace" :placeholder="selectedOntology?.iri"
              /></label>
              <div class="inline-actions">
                <n-button
                  type="primary"
                  :disabled="!canRun || working"
                  :loading="working"
                  @click="startRun"
                  >{{ t('dataAccess.mapping.startRun') }}</n-button
                ><n-button
                  v-if="runResult"
                  secondary
                  @click="router.push({ name: 'extraction-runs' })"
                  >{{ t('dataAccess.mapping.viewRunHistory') }}</n-button
                >
              </div>
              <div v-if="runResult" class="run-result">
                <strong>{{ t('dataAccess.mapping.runCreated', { id: runResult.run.id }) }}</strong
                ><span>{{
                  t('dataAccess.mapping.runStatus', {
                    status: t('runs.statuses.' + runResult.run.status, runResult.run.status),
                  })
                }}</span
                ><span>{{
                  t('dataAccess.mapping.graphRevision', {
                    revision:
                      runResult.graph_revision?.id ?? t('dataAccess.mapping.noGraphRevision'),
                  })
                }}</span>
              </div>
            </div>
          </n-card>
        </div>

        <div class="wizard-footer">
          <n-button :disabled="step === 1 || working" @click="previousStep">{{
            t('dataAccess.mapping.previous')
          }}</n-button>
          <div class="footer-progress">
            <span>{{ t('dataAccess.mapping.progress', { step, total: 5 }) }}</span
            ><n-button
              v-if="step < 5"
              type="primary"
              :disabled="
                (step === 1 && (!selectedOntologyId || !mappingName.trim())) ||
                (step === 2 && (!selectedDatasourceId || !catalog)) ||
                (step === 3 && (!canSaveDraft || !selectedMappingId || working)) ||
                (step === 4 && !preview)
              "
              :loading="step === 3 && working"
              @click="nextStep"
              >{{
                step === 3 ? t('dataAccess.mapping.saveAndPreview') : t('dataAccess.mapping.next')
              }}</n-button
            >
          </div>
        </div>
      </div>
    </n-spin>
  </section>
</template>

<style scoped>
.mapping-page {
  display: grid;
  gap: var(--space-4);
}
.mapping-picker {
  width: 260px;
}
.wizard-shell {
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--r-xl);
  background: var(--bg-base);
  box-shadow: var(--elev-2);
}
.wizard-heading {
  display: grid;
  gap: var(--space-4);
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-surface);
}
.wizard-title,
.card-heading,
.editor-heading,
.inline-actions,
.sample-toolbar,
.preview-toolbar,
.wizard-footer,
.footer-progress,
.resource-summary,
.catalog-summary,
.relation-result {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.wizard-title h3,
.card-heading h4,
.preview-toolbar h3 {
  margin: 0;
  color: var(--text);
  font-size: var(--font-h2);
  font-weight: 550;
}
.wizard-steps {
  display: flex;
  align-items: center;
  gap: clamp(8px, 2vw, 26px);
  overflow-x: auto;
}
.wizard-step {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 8px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  font: inherit;
  font-size: var(--font-small);
}
.wizard-step:disabled {
  cursor: default;
  opacity: 0.55;
}
.step-number {
  display: grid;
  width: 24px;
  height: 24px;
  flex: none;
  place-items: center;
  border: 1px solid var(--border);
  border-radius: 50%;
  font-family: var(--mono);
  font-size: 11px;
}
.wizard-step.active {
  color: var(--text);
}
.wizard-step.active .step-number {
  border-color: transparent;
  background: var(--accent);
  color: white;
}
.wizard-step.completed .step-number {
  border-color: rgba(52, 211, 153, 0.5);
  background: rgba(52, 211, 153, 0.14);
  color: var(--s-pass);
}
.ontology-version {
  color: var(--text-secondary);
  font-size: var(--font-small);
}
.step-content {
  display: grid;
  gap: var(--space-4);
  min-height: 340px;
  padding: var(--space-5);
}
.form-grid,
.map-selectors {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}
.three-columns {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.field-group {
  display: grid;
  min-width: 0;
  gap: var(--space-1);
  color: var(--text-secondary);
  font-size: var(--font-small);
}
.field-group > span {
  color: var(--text-secondary);
}
.resource-summary,
.catalog-summary {
  flex-wrap: wrap;
  margin-top: var(--space-4);
  color: var(--text-secondary);
  font-size: var(--font-small);
}
.warning-copy {
  color: var(--s-notrun);
}
.muted-copy,
.subtle-copy,
.table-footnote {
  color: var(--text-tertiary);
  font-size: var(--font-small);
}
.inline-empty,
.page-empty {
  padding: var(--space-5);
}
.inline-actions {
  flex-wrap: wrap;
}
.datasource-form {
  align-items: end;
}
.sample-toolbar {
  justify-content: space-between;
}
.sample-toolbar :deep(.n-select) {
  width: min(460px, 100%);
}
.table-scroll {
  width: 100%;
  overflow: auto;
}
.sample-table {
  max-height: 380px;
  margin-top: var(--space-4);
}
.table-scroll table {
  width: 100%;
  border-collapse: collapse;
  color: var(--text);
  font-size: var(--font-small);
  white-space: nowrap;
}
.table-scroll th,
.table-scroll td {
  padding: 9px 12px;
  border-bottom: 1px solid var(--border-subtle);
  text-align: left;
  vertical-align: top;
}
.table-scroll th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--bg-surface);
  color: var(--text-tertiary);
  font-size: 11px;
  font-weight: 500;
}
.table-scroll th small {
  display: block;
  color: var(--text-disabled);
  font-family: var(--mono);
  font-weight: 400;
}
.table-scroll tbody tr:hover {
  background: var(--bg-hover);
}
.table-footnote {
  padding: var(--space-2) var(--space-3);
}
.card-heading {
  justify-content: space-between;
}
.card-heading p,
.preview-toolbar p,
.publish-panel p {
  margin: var(--space-1) 0 0;
  color: var(--text-secondary);
  font-size: var(--font-small);
}
.view-switch {
  display: flex;
  flex: none;
  gap: 4px;
}
.map-overview {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-lg);
  background: var(--bg-inset);
}
.map-flow {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
}
.flow-node {
  display: grid;
  min-width: 160px;
  gap: 4px;
  padding: 10px 13px;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--bg-raised);
}
.flow-node strong {
  overflow: hidden;
  color: var(--text);
  font-size: var(--font-small);
  text-overflow: ellipsis;
}
.node-kicker {
  color: var(--text-tertiary);
  font-size: 11px;
}
.source-node {
  border-color: rgba(34, 211, 238, 0.35);
}
.target-node {
  border-color: rgba(79, 141, 247, 0.45);
}
.flow-arrow {
  width: 70px;
  flex: none;
  overflow: visible;
}
.flow-arrow path {
  fill: none;
  stroke: var(--g-relation);
  stroke-width: 1.6;
}
.relation-overview,
.pending-relations {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  color: var(--text-secondary);
  font-size: var(--font-small);
}
.overview-table {
  margin-top: var(--space-4);
}
.editors {
  display: grid;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}
.editor-card {
  display: grid;
  gap: var(--space-4);
  padding: var(--space-4);
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-lg);
  background: var(--bg-base);
}
.editor-heading {
  justify-content: space-between;
}
.editor-heading > div {
  display: grid;
  gap: 4px;
}
.editor-heading strong {
  color: var(--text);
  font-size: var(--font-body);
  font-weight: 550;
}
.subtle-copy {
  overflow-wrap: anywhere;
  font-family: var(--mono);
}
.field-table {
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-md);
}
.field-table :deep(.n-select),
.field-table :deep(.n-input) {
  min-width: 150px;
}
.mono {
  font-family: var(--mono);
}
.key-fields {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--text-secondary);
  font-size: var(--font-small);
}
.key-option {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--text);
}
.key-option input {
  accent-color: var(--accent);
}
.relation-editor {
  border-color: rgba(34, 211, 238, 0.2);
}
.endpoint-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}
.endpoint-card {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-md);
  background: var(--bg-surface);
}
.endpoint-card > strong {
  color: var(--text);
  font-size: var(--font-small);
  font-weight: 550;
}
.poly-editor {
  display: grid;
  gap: 8px;
  border: 1px dashed var(--border);
  border-radius: 8px;
  padding: 8px;
}
.poly-editor summary {
  cursor: pointer;
  color: var(--text-secondary);
}
.candidate-rows {
  display: grid;
  gap: 6px;
  color: var(--text-secondary);
  font-size: var(--font-caption);
}
.candidate-row {
  display: grid;
  grid-template-columns: 1fr 1fr 0.8fr auto;
  gap: 6px;
  align-items: center;
}
.attribute-maps {
  display: grid;
  gap: var(--space-2);
}
.attribute-row {
  grid-template-columns: minmax(120px, 1fr) minmax(220px, 2fr);
  align-items: center;
}
.preview-toolbar {
  justify-content: space-between;
  flex-wrap: wrap;
}
.preview-toolbar > div:first-child {
  min-width: 230px;
}
.limit-input {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--text-secondary);
  font-size: var(--font-small);
}
.limit-input :deep(.n-input-number) {
  width: 100px;
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-3);
}
.stat-card {
  display: grid;
  gap: 4px;
  padding: 14px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-md);
  background: var(--bg-surface);
}
.stat-card strong {
  color: var(--text);
  font-family: var(--mono);
  font-size: 20px;
  font-weight: 500;
}
.stat-card span {
  color: var(--text-tertiary);
  font-size: var(--font-small);
}
.stat-card.good strong {
  color: var(--s-pass);
}
.stat-card.bad strong {
  color: var(--s-violation);
}
.preview-card :deep(.n-card__content) {
  padding-top: 0;
}
.cell-error {
  color: var(--s-violation);
  background: rgba(248, 113, 113, 0.1);
}
.cell-empty {
  color: var(--text-tertiary);
  font-style: italic;
}
.error-list {
  display: grid;
  gap: var(--space-2);
  padding-top: var(--space-3);
}
.error-list > div {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--text-secondary);
  font-size: var(--font-small);
}
.relation-result {
  color: var(--text-secondary);
  font-size: var(--font-small);
}
.publish-panel {
  display: grid;
  justify-items: start;
  gap: var(--space-4);
  max-width: 760px;
}
.publish-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  color: var(--text-secondary);
  font-size: var(--font-small);
}
.namespace-field {
  width: min(520px, 100%);
}
.run-result {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  color: var(--text-secondary);
  font-size: var(--font-small);
}
.run-result strong {
  color: var(--s-pass);
}
.wizard-footer {
  justify-content: space-between;
  padding: var(--space-4) var(--space-5);
  border-top: 1px solid var(--border-subtle);
  background: var(--bg-surface);
}
.footer-progress {
  color: var(--text-tertiary);
  font-size: var(--font-small);
}
@media (max-width: 900px) {
  .step-content,
  .wizard-heading {
    padding: var(--space-3);
  }
  .form-grid,
  .three-columns,
  .endpoint-grid {
    grid-template-columns: 1fr;
  }
  .mapping-page > :deep(.page-header) {
    flex-wrap: wrap;
  }
  .mapping-picker {
    width: 100%;
  }
  .map-flow {
    flex-wrap: wrap;
  }
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
