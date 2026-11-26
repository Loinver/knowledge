<script setup lang="ts">
import { computed, h, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'

import type {
  DataTypeProp,
  DataTypePropInput,
  EntityType,
  EntityTypeBrief,
  EntityTypeUpdate,
  EntityTypeUsages,
  TypeRelationUsage,
  TypeRuleUsage,
} from '@/api/entity-types'
import { entityTypesApi } from '@/api/entity-types'
import type { EnumDictionary } from '@/api/enum-dictionaries'
import { enumDictionariesApi } from '@/api/enum-dictionaries'
import PageHeader from '@/components/PageHeader.vue'
import type { FormInst, FormRules } from '@/components/ui'
import {
  FormContainer,
  FormField,
  UiAlert,
  UiButton,
  UiDataTable,
  UiDescriptions,
  UiDescriptionsItem,
  UiDrawer,
  UiDrawerContent,
  UiEmpty,
  UiInput,
  UiModal,
  UiPopconfirm,
  UiSelect,
  UiSpace,
  UiSpin,
  UiSwitch,
  UiTabPane,
  UiTabs,
  UiTag,
} from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useDraftGuard } from '@/composables/useDraftGuard'
import { usePageIdentity } from '@/layout/navigation/usePageIdentity'
import { useAuthStore } from '@/stores/auth'

import AssetIdentity from '../components/AssetIdentity.vue'
import type { PropertyDraft } from './propertyValidation'
import { propertyErrors, propertyPayload, propertyRules } from './propertyValidation'

const { t, locale } = useI18n()
const { toMessage } = useApiError()
const route = useRoute()
const auth = useAuthStore()
const canWrite = computed(() => auth.user?.role === 'ADMIN' || auth.user?.role === 'EDITOR')
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const data = ref<EntityType | null>(null)
/** 关联关系 / 规则 / 引用与版本：一次请求取全，三个页签共用。 */
const usages = ref<EntityTypeUsages | null>(null)
const usagesLoading = ref(false)
/** 父类型 id → 标签，用于把继承链显示成名字而不是裸 id。 */
const typeList = ref<EntityTypeBrief[]>([])
const typeListLoading = ref(false)
const typeListError = ref('')
const typeLabels = computed(() =>
  Object.fromEntries(typeList.value.map((item) => [item.id, localized(item.label_i18n)])),
)
const showEditor = ref(false)
const editorError = ref('')
const editingName = ref<string | null>(null)
const form = ref<PropertyDraft>(emptyProperty())
const propertyFormRef = ref<FormInst | null>(null)
const propertyValidating = ref(false)
const dictionaries = ref<EnumDictionary[]>([])
const dictionaryLoading = ref(false)
const dictionaryError = ref('')
const versions = ref<EnumDictionary[]>([])
const versionsLoading = ref(false)
const versionsError = ref('')
let operationGeneration = 0
let loadGeneration = 0
let editorGeneration = 0
let propertyInputGeneration = 0
const propertySession = ref(0)
let dictionaryController: AbortController | undefined
let versionController: AbortController | undefined
let alive = true

/**
 * 基本信息（标签 / 定义）的编辑态。
 *
 * 机读名 name 是资源的身份，创建后不可改，表单里只读展示；IRI 由
 * namespace + name 推导，同样不在这里改。其余可编辑字段与后端
 * `EntityTypeUpdate` 一致：标签、定义与父类，不碰 data_props。
 */
const showBasicEditor = ref(false)
const basicError = ref('')
const basicFormRef = ref<FormInst | null>(null)
const basicForm = ref({
  labelZh: '',
  labelEn: '',
  definitionZh: '',
  definitionEn: '',
  parentIds: [] as number[],
})
let basicEditorGeneration = 0
const basicSession = ref(0)
const parentOptions = computed(() => {
  const options = typeList.value
    .filter((item) => item.id !== data.value?.id)
    .map((item) => ({ value: item.id, label: `${item.name} · ${localized(item.label_i18n)}` }))
  for (const id of basicForm.value.parentIds) {
    if (!options.some((item) => item.value === id) && id !== data.value?.id) {
      options.push({ value: id, label: `#${id}` })
    }
  }
  return options
})

const basicRules = computed<FormRules>(() => ({
  labelZh: {
    required: true,
    message: t('entityType.basicIncomplete'),
    trigger: ['blur', 'input'],
  },
}))

function emptyProperty() {
  return {
    name: '',
    label_i18n: { 'zh-CN': '', 'en-US': '' },
    definition_i18n: { 'zh-CN': '', 'en-US': '' },
    datatype: 'string',
    enum_dict_id: null as number | null,
    enum_dict_revision: null as number | null,
    nullable: true,
    default_value: null as string | null,
    min_cardinality: null as number | null,
    max_cardinality: null as number | null,
    min_value: null as string | null,
    max_value: null as string | null,
    source_clause_ref: null as string | null,
  }
}

function localized(labels: Record<string, string> | null | undefined) {
  return labels?.[locale.value]?.trim() || t('enumDictionaries.untranslated')
}

function failure(err: unknown) {
  if ((err as { code?: string })?.code === 'KG.REVISION_CONFLICT') return t('entityProps.conflict')
  return toMessage(err)
}

async function loadDetail() {
  operationGeneration++
  busy.value = false
  const generation = ++loadGeneration
  editorGeneration++
  showEditor.value = false
  showBasicEditor.value = false
  showRename.value = false
  usages.value = null
  versionController?.abort()
  dictionaryController?.abort()
  data.value = null
  error.value = ''
  notice.value = ''
  const id = Number(route.params.id)
  if (!Number.isSafeInteger(id) || id <= 0) {
    error.value = t('graph.notFound')
    loading.value = false
    return
  }
  loading.value = true
  try {
    const result = await entityTypesApi.get(id)
    if (alive && generation === loadGeneration) data.value = result
  } catch (err) {
    if (alive && generation === loadGeneration) error.value = failure(err)
  } finally {
    if (alive && generation === loadGeneration) loading.value = false
  }
  if (alive && generation === loadGeneration) void loadUsages(id, generation)
}

/** 三个页签的数据独立加载：取不到不影响基本信息与数据属性。 */
async function loadUsages(id: number, generation: number) {
  usagesLoading.value = true
  usages.value = null
  try {
    const result = await entityTypesApi.usages(id)
    if (alive && generation === loadGeneration) usages.value = result
  } catch {
    if (alive && generation === loadGeneration) usages.value = null
  } finally {
    if (alive && generation === loadGeneration) usagesLoading.value = false
  }
}

/** 父类型只给了 id，列表拿一次标签做映射，继承链才能显示名字。 */
async function loadTypeLabels() {
  typeListLoading.value = true
  typeListError.value = ''
  try {
    const list = await entityTypesApi.list({ page_size: 200 })
    if (alive) typeList.value = list
  } catch (cause) {
    if (alive) typeListError.value = toMessage(cause)
  } finally {
    if (alive) typeListLoading.value = false
  }
}

async function handlePublish() {
  if (!canWrite.value || !data.value || data.value.status !== 'DRAFT' || busy.value) return
  const generation = loadGeneration
  const operation = ++operationGeneration
  busy.value = true
  error.value = ''
  try {
    await entityTypesApi.publish(data.value.id)
    if (alive && generation === loadGeneration) await loadDetail()
  } catch (err) {
    if (alive && generation === loadGeneration) error.value = failure(err)
  } finally {
    if (alive && operation === operationGeneration) busy.value = false
  }
}

async function startRevision() {
  if (!canWrite.value || data.value?.status !== 'PUBLISHED' || busy.value) return
  const generation = loadGeneration
  const operation = ++operationGeneration
  busy.value = true
  error.value = ''
  try {
    await entityTypesApi.unpublish(data.value.id)
    if (alive && generation === loadGeneration) await loadDetail()
  } catch (err) {
    if (alive && generation === loadGeneration) error.value = failure(err)
  } finally {
    if (alive && operation === operationGeneration) busy.value = false
  }
}

const showRename = ref(false)
const renameSession = ref(0)
const renameValue = ref('')

function openRename() {
  if (!canWrite.value || !data.value || data.value.status !== 'DRAFT' || busy.value) return
  renameSession.value++
  renameValue.value = ''
  showRename.value = true
}

async function submitRename() {
  if (!canWrite.value || !data.value || !renameValue.value.trim() || busy.value) return false
  const generation = loadGeneration
  const operation = ++operationGeneration
  busy.value = true
  error.value = ''
  try {
    await entityTypesApi.rename(data.value.id, renameValue.value.trim())
    if (alive && generation === loadGeneration) {
      showRename.value = false
      await loadDetail()
    }
  } catch (err) {
    if (alive && generation === loadGeneration) error.value = failure(err)
  } finally {
    if (alive && operation === operationGeneration) busy.value = false
  }
  return false
}

/**
 * 打开基本信息编辑抽屉。只允许在草稿态编辑——已发布/已归档的资源是冻结快照。
 */
function openBasicEditor() {
  if (!canWrite.value || !data.value || data.value.status !== 'DRAFT' || busy.value) return
  basicSession.value++
  basicEditorGeneration++
  basicForm.value = {
    labelZh: data.value.label_i18n?.['zh-CN'] ?? '',
    labelEn: data.value.label_i18n?.['en-US'] ?? '',
    definitionZh: data.value.definition_i18n?.['zh-CN'] ?? '',
    definitionEn: data.value.definition_i18n?.['en-US'] ?? '',
    parentIds: [...(data.value.parent_ids ?? [])],
  }
  basicError.value = ''
  showBasicEditor.value = true
}

/** 中文标签必填；英文缺失保持未翻译，父类整体更新但不改数据属性。 */
function collectBasicPayload(): Pick<
  EntityTypeUpdate,
  'label_i18n' | 'definition_i18n' | 'parent_ids'
> {
  const f = basicForm.value
  const labelZh = f.labelZh.trim()
  const label: Record<string, string> = { 'zh-CN': labelZh }
  if (f.labelEn.trim()) label['en-US'] = f.labelEn.trim()

  const definition: Record<string, string> = {}
  if (f.definitionZh.trim()) definition['zh-CN'] = f.definitionZh.trim()
  if (f.definitionEn.trim()) definition['en-US'] = f.definitionEn.trim()
  return { label_i18n: label, definition_i18n: definition, parent_ids: [...new Set(f.parentIds)] }
}

async function saveBasic() {
  const entity = data.value
  if (
    !canWrite.value ||
    !entity ||
    entity.status !== 'DRAFT' ||
    busy.value ||
    !showBasicEditor.value
  )
    return
  const generation = loadGeneration
  const editor = basicEditorGeneration
  const payload = collectBasicPayload()
  if (
    !basicForm.value.labelZh.trim() ||
    basicForm.value.parentIds.some((id) => id === entity.id || !Number.isSafeInteger(id) || id <= 0)
  ) {
    basicError.value = t('entityType.basicOrParentsInvalid')
    return
  }
  try {
    await basicFormRef.value?.validate()
  } catch {
    return
  }
  if (
    !canWrite.value ||
    busy.value ||
    !alive ||
    generation !== loadGeneration ||
    editor !== basicEditorGeneration ||
    !showBasicEditor.value
  )
    return
  const operation = ++operationGeneration
  busy.value = true
  basicError.value = ''
  error.value = ''
  notice.value = ''
  try {
    const result = await entityTypesApi.update(entity.id, {
      ...payload,
      if_match: entity.current_revision,
      edit_revision: entity.edit_revision,
    })
    if (!alive || generation !== loadGeneration || editor !== basicEditorGeneration) return
    data.value = result
    notice.value = t('entityType.basicSaved')
    showBasicEditor.value = false
  } catch (err) {
    if (!alive || generation !== loadGeneration || editor !== basicEditorGeneration) return
    basicError.value = failure(err)
  } finally {
    if (alive && operation === operationGeneration) busy.value = false
  }
}

async function loadDictionaries(q = '') {
  dictionaryController?.abort()
  const controller = new AbortController()
  dictionaryController = controller
  dictionaryLoading.value = true
  dictionaryError.value = ''
  try {
    const result = await enumDictionariesApi.list(
      { page: 1, page_size: 100, q, sort: 'name' },
      controller.signal,
    )
    if (!controller.signal.aborted && alive) dictionaries.value = result.items
  } catch (err) {
    if (!controller.signal.aborted && alive) dictionaryError.value = failure(err)
  } finally {
    if (!controller.signal.aborted && alive) dictionaryLoading.value = false
  }
}

async function loadVersions(id: number) {
  versionController?.abort()
  const controller = new AbortController()
  versionController = controller
  versions.value = []
  versionsLoading.value = true
  versionsError.value = ''
  try {
    const history = await enumDictionariesApi.revisions(id, controller.signal)
    if (!controller.signal.aborted && alive) versions.value = history
  } catch (err) {
    if (!controller.signal.aborted && alive) versionsError.value = failure(err)
  } finally {
    if (!controller.signal.aborted && alive) versionsLoading.value = false
  }
}

function changeDictionary(id: number | null) {
  form.value.enum_dict_id = id
  form.value.enum_dict_revision = null
  versions.value = []
  versionController?.abort()
  form.value.default_value = null
  versionsLoading.value = false
  versionsError.value = ''
  if (id !== null) void loadVersions(id)
}

function changeDatatype(value: string) {
  form.value.datatype = value
  changeDictionary(null)
}

function openProperty(prop?: DataTypeProp) {
  if (!canWrite.value || data.value?.status !== 'DRAFT' || busy.value || propertyValidating.value)
    return
  propertySession.value++
  editorGeneration++
  editingName.value = prop?.name ?? null
  form.value = prop
    ? {
        name: prop.name,
        label_i18n: {
          'zh-CN': prop.label_i18n?.['zh-CN'] ?? '',
          'en-US': prop.label_i18n?.['en-US'] ?? '',
        },
        definition_i18n: {
          'zh-CN': prop.definition_i18n?.['zh-CN'] ?? '',
          'en-US': prop.definition_i18n?.['en-US'] ?? '',
        },
        datatype: prop.datatype,
        enum_dict_id: prop.enum_dict_id ?? null,
        enum_dict_revision: prop.enum_dict_revision ?? null,
        nullable: prop.nullable,
        default_value: prop.default_value ?? null,
        min_cardinality: prop.min_cardinality ?? null,
        max_cardinality: prop.max_cardinality ?? null,
        min_value: prop.min_value ?? null,
        max_value: prop.max_value ?? null,
        source_clause_ref: prop.source_clause_ref ?? null,
      }
    : emptyProperty()
  editorError.value = ''
  versionsError.value = ''
  versions.value = []
  versionsLoading.value = false
  versionController?.abort()
  showEditor.value = true
  void loadDictionaries()
  if (form.value.enum_dict_id !== null) void loadVersions(form.value.enum_dict_id)
}

function propertyInput(prop: DataTypeProp): DataTypePropInput {
  return {
    name: prop.name,
    label_i18n: prop.label_i18n,
    definition_i18n: prop.definition_i18n,
    datatype: prop.datatype,
    enum_dict_id: prop.enum_dict_id,
    enum_dict_revision: prop.enum_dict_revision,
    nullable: prop.nullable,
    default_value: prop.default_value,
    min_cardinality: prop.min_cardinality,
    max_cardinality: prop.max_cardinality,
    min_value: prop.min_value,
    max_value: prop.max_value,
    source_clause_ref: prop.source_clause_ref,
  }
}

async function saveProperties(props: DataTypePropInput[], editor = false) {
  const entity = data.value
  if (!canWrite.value || !entity || entity.status !== 'DRAFT' || busy.value) return
  const generation = loadGeneration
  const edit = editorGeneration
  const operation = ++operationGeneration
  busy.value = true
  error.value = ''
  editorError.value = ''
  notice.value = ''
  try {
    const result = await entityTypesApi.update(entity.id, {
      data_props: props,
      if_match: entity.current_revision,
      edit_revision: entity.edit_revision,
    })
    if (!alive || generation !== loadGeneration || (editor && edit !== editorGeneration)) return
    data.value = result
    notice.value = t('entityProps.saved')
    if (editor && edit === editorGeneration) showEditor.value = false
  } catch (err) {
    if (!alive || generation !== loadGeneration || (editor && edit !== editorGeneration)) return
    if (editor && edit === editorGeneration) editorError.value = failure(err)
    else error.value = failure(err)
  } finally {
    if (alive && operation === operationGeneration) busy.value = false
  }
}

async function submitProperty() {
  const entity = data.value
  if (
    !alive ||
    !canWrite.value ||
    !entity ||
    entity.status !== 'DRAFT' ||
    !showEditor.value ||
    busy.value ||
    propertyValidating.value ||
    versionsLoading.value
  )
    return
  const generation = loadGeneration
  const editor = editorGeneration
  const inputGeneration = propertyInputGeneration
  const operation = operationGeneration
  const name = editingName.value
  const input: PropertyDraft = {
    ...form.value,
    label_i18n: { ...form.value.label_i18n },
    definition_i18n: { ...form.value.definition_i18n },
  }
  const context = {
    editingName: name,
    names: (entity.data_props ?? []).map((prop) => prop.name),
    version: selectedVersion.value,
  }
  const invalid = propertyErrors(input, context)
  const formInstance = propertyFormRef.value
  propertyValidating.value = true
  editorError.value = ''
  try {
    try {
      await formInstance?.validate()
    } catch {
      return
    }
    if (
      !alive ||
      !canWrite.value ||
      busy.value ||
      versionsLoading.value ||
      generation !== loadGeneration ||
      editor !== editorGeneration ||
      inputGeneration !== propertyInputGeneration ||
      operation !== operationGeneration ||
      data.value !== entity ||
      !showEditor.value
    )
      return
    if (Object.keys(invalid).length) {
      if (!formInstance) editorError.value = t(Object.values(invalid)[0])
      return
    }
    const props = (entity.data_props ?? []).map(propertyInput)
    const replacement = propertyPayload(input)
    if (name === null) props.push(replacement)
    else {
      const index = props.findIndex((prop) => prop.name === name)
      if (index < 0) return
      props[index] = replacement
    }
    await saveProperties(props, true)
  } finally {
    if (alive && generation === loadGeneration && editor === editorGeneration)
      propertyValidating.value = false
  }
}

function removeProperty(prop: DataTypeProp) {
  const props = (data.value?.data_props ?? [])
    .filter((item) => item.name !== prop.name)
    .map(propertyInput)
  void saveProperties(props)
}

usePageIdentity(() => data.value?.name)

const isDraft = computed(() => canWrite.value && data.value?.status === 'DRAFT')
const selectedVersion = computed(() =>
  versions.value.find(
    (item) =>
      item.id === form.value.enum_dict_id && item.revision === form.value.enum_dict_revision,
  ),
)
const propertyFormRules = computed<FormRules>(() =>
  propertyRules(
    form.value,
    {
      editingName: editingName.value,
      names: (data.value?.data_props ?? []).map((prop) => prop.name),
      version: selectedVersion.value,
    },
    t,
  ),
)
const newerVersion = computed(() => Math.max(0, ...versions.value.map((item) => item.revision)))
const datatypeOptions = computed(() =>
  ['string', 'integer', 'decimal', 'boolean', 'date', 'enum'].map((value) => ({
    value,
    label: t(`entityProps.datatypes.${value}`),
  })),
)
const dictionaryOptions = computed(() => {
  const options = dictionaries.value.map((item) => ({
    value: item.id,
    label: `${item.name} · ${localized(item.label_i18n)}`,
  }))
  const id = form.value.enum_dict_id
  if (id !== null && !options.some((item) => item.value === id)) {
    options.push({
      value: id,
      label: versions.value[0]?.name ?? t('entityProps.dictionaryId', { id }),
    })
  }
  return options
})
const versionOptions = computed(() =>
  versions.value.map((item) => ({
    value: item.revision,
    label: t('enumDictionaries.revisionLabel', { revision: item.revision }),
  })),
)
const defaultOptions = computed(() =>
  (selectedVersion.value?.entries ?? []).map((entry) => ({
    value: entry.value,
    label: `${entry.value} · ${localized(entry.label_i18n)}`,
  })),
)
const propColumns = computed(() => [
  { title: t('common.name'), key: 'name' },
  {
    title: t('common.iri'),
    key: 'iri',
    render: (prop: DataTypeProp) => prop.iri ?? '—',
  },
  {
    title: t('common.label'),
    key: 'label_i18n',
    render: (prop: DataTypeProp) => localized(prop.label_i18n),
  },
  {
    title: t('common.datatype'),
    key: 'datatype',
    render: (prop: DataTypeProp) => t(`entityProps.datatypes.${prop.datatype}`),
  },
  {
    title: t('entityProps.dictionary'),
    key: 'enum_dict_id',
    render: (prop: DataTypeProp) =>
      prop.enum_dict_id == null ? '—' : t('entityProps.dictionaryId', { id: prop.enum_dict_id }),
  },
  {
    title: t('enumDictionaries.pinnedRevision'),
    key: 'enum_dict_revision',
    render: (prop: DataTypeProp) => prop.enum_dict_revision ?? '—',
  },
  {
    title: t('entityProps.defaultValue'),
    key: 'default_value',
    render: (prop: DataTypeProp) => prop.default_value ?? '—',
  },
  {
    title: t('common.nullable'),
    key: 'nullable',
    render: (prop: DataTypeProp) => t(prop.nullable ? 'common.yes' : 'common.no'),
  },
  {
    title: t('entityProps.minCardinality'),
    key: 'min_cardinality',
    render: (prop: DataTypeProp) => prop.min_cardinality ?? '—',
  },
  {
    title: t('entityProps.maxCardinality'),
    key: 'max_cardinality',
    render: (prop: DataTypeProp) => prop.max_cardinality ?? '—',
  },
  {
    title: t('entityProps.minValue'),
    key: 'min_value',
    render: (prop: DataTypeProp) => prop.min_value ?? '—',
  },
  {
    title: t('entityProps.maxValue'),
    key: 'max_value',
    render: (prop: DataTypeProp) => prop.max_value ?? '—',
  },
  {
    title: t('entityProps.sourceClauseRef'),
    key: 'source_clause_ref',
    render: (prop: DataTypeProp) => prop.source_clause_ref ?? '—',
  },
  ...(isDraft.value
    ? [
        {
          title: t('common.actions'),
          key: 'actions',
          fixed: 'right' as const,
          render: (prop: DataTypeProp) =>
            h(UiSpace, {}, () => [
              h(
                UiButton,
                { size: 'small', disabled: busy.value, onClick: () => openProperty(prop) },
                () => t('common.edit'),
              ),
              h(
                UiPopconfirm,
                { onPositiveClick: () => removeProperty(prop) },
                {
                  trigger: () =>
                    h(UiButton, { size: 'small', type: 'error', disabled: busy.value }, () =>
                      t('common.delete'),
                    ),
                  default: () => t('entityProps.confirmRemove', { name: prop.name }),
                },
              ),
            ]),
        },
      ]
    : []),
])

/** 关联关系页签：自己在哪一端 + 另一端的类型。 */
const relationColumns = computed(() => [
  {
    title: t('relation.list'),
    key: 'name',
    minWidth: 160,
    render: (row: TypeRelationUsage) =>
      h('div', { class: 'cell-name' }, [
        h('span', { class: 'cell-primary' }, localized(row.label_i18n)),
        h('span', { class: 'cell-sub mono' }, row.name),
      ]),
  },
  {
    title: t('entityType.role'),
    key: 'role',
    width: 100,
    render: (row: TypeRelationUsage) =>
      t(row.role === 'domain' ? 'entityType.asDomain' : 'entityType.asRange'),
  },
  {
    title: t('entityType.otherEnd'),
    key: 'other',
    minWidth: 140,
    render: (row: TypeRelationUsage) =>
      row.other_type_id === null ? t('common.noneValue') : localized(row.other_label_i18n),
  },
  {
    title: t('common.status'),
    key: 'status',
    width: 100,
    render: (row: TypeRelationUsage) =>
      h(UiTag, { size: 'small', type: row.status === 'PUBLISHED' ? 'success' : 'default' }, () =>
        t(`resourceStatus.${row.status}`),
      ),
  },
])

/** 规则页签：按目标 IRI 命中的治理规则。 */
const ruleColumns = computed(() => [
  {
    title: t('rules.identifier'),
    key: 'identifier',
    minWidth: 160,
    render: (row: TypeRuleUsage) => h('span', { class: 'mono' }, row.identifier),
  },
  {
    title: t('common.label'),
    key: 'name_i18n',
    minWidth: 160,
    render: (row: TypeRuleUsage) => localized(row.name_i18n),
  },
  {
    title: t('rules.severity'),
    key: 'severity',
    width: 110,
    render: (row: TypeRuleUsage) => t(`rules.severities.${row.severity}`),
  },
])

const VALIDATION_VAR: Record<string, string> = {
  PASS: 'var(--s-pass)',
  VIOLATION: 'var(--s-violation)',
  NA: 'var(--s-na)',
  NOT_RUN: 'var(--s-notrun)',
}

/** 继承链：把 parent_ids 映射成名字，未知 id 原样显示。 */
const parentChain = computed(() =>
  (data.value?.parent_ids ?? []).map((id) => typeLabels.value[id] ?? `#${id}`),
)

watch(
  () => route.params.id,
  () => {
    void loadDetail()
    void loadTypeLabels()
  },
  { immediate: true },
)
watch(
  form,
  () => {
    propertyInputGeneration++
  },
  { deep: true, flush: 'sync' },
)
watch(
  showEditor,
  (show) => {
    if (!show) {
      editorGeneration++
      propertyValidating.value = false
      dictionaryController?.abort()
      versionController?.abort()
    }
  },
  { flush: 'sync' },
)
onBeforeUnmount(() => {
  alive = false
  loadGeneration++
  dictionaryController?.abort()
  versionController?.abort()
})
const basicVisible = useDraftGuard(
  showBasicEditor,
  () => basicForm.value,
  () => true,
  () => basicSession.value,
)
watch(
  showBasicEditor,
  (show) => {
    if (!show) basicEditorGeneration++
  },
  { flush: 'sync' },
)
const propertyVisible = useDraftGuard(
  showEditor,
  () => form.value,
  () => true,
  () => propertySession.value,
)
const renameVisible = useDraftGuard(
  showRename,
  () => renameValue.value,
  () => true,
  () => renameSession.value,
)
</script>

<template>
  <div class="asset-page asset-detail-page">
    <PageHeader
      :title="t('page.entityDetail')"
      :eyebrow="t('page.entityTypes')"
      :identity="data?.name"
    >
      <template #context>
        <strong v-if="data" class="detail-object-label">{{ localized(data.label_i18n) }}</strong>
        <AssetIdentity
          v-if="data"
          :name="data.name"
          :iri="data.iri"
          :revision="data.current_revision"
          :status="data.status"
      /></template>
      <template #actions>
        <UiPopconfirm v-if="data?.status === 'PUBLISHED'" @positive-click="startRevision">
          <template #trigger
            ><UiButton :disabled="busy || !canWrite">{{
              t('common.startRevision')
            }}</UiButton></template
          >
          {{ t('common.startRevisionHint') }}
        </UiPopconfirm>
        <UiButton v-if="data && isDraft" :disabled="busy" @click="openBasicEditor">
          {{ t('common.edit') }}
        </UiButton>
        <UiButton v-if="data && isDraft" :disabled="busy" @click="openRename">
          {{ t('common.rename') }}
        </UiButton>
        <UiButton
          v-if="data && isDraft"
          type="primary"
          :disabled="busy"
          :loading="busy"
          @click="handlePublish"
        >
          {{ t('common.publish') }}
        </UiButton>
      </template>
    </PageHeader>
    <div class="object-context">
      <RouterLink :to="{ name: 'entity-types', query: route.query }">{{
        t('ui.backList')
      }}</RouterLink>
    </div>
    <UiAlert v-if="!canWrite" type="info" class="feedback">{{ t('ui.readonly') }}</UiAlert>
    <UiAlert v-else-if="data?.status === 'PUBLISHED'" type="info" class="feedback">{{
      t('ui.frozen')
    }}</UiAlert>
    <UiModal
      v-model:show="renameVisible"
      preset="dialog"
      :title="t('entityType.renameTitle')"
      :positive-text="t('common.save')"
      :negative-text="t('common.cancel')"
      :positive-button-props="{ loading: busy, disabled: !renameValue.trim() }"
      @positive-click="submitRename"
    >
      <UiSpace vertical>
        <UiAlert v-if="error" type="error">{{ error }}</UiAlert>
        <p>{{ t('entityType.renameHint', { current: data?.name }) }}</p>
        <UiInput
          v-model:value="renameValue"
          :placeholder="t('entityType.renamePlaceholder')"
          @keyup.enter="submitRename"
        />
      </UiSpace>
    </UiModal>
    <UiAlert v-if="error" type="error" class="feedback"
      >{{ error }}
      <UiButton size="small" :disabled="busy" @click="loadDetail">{{
        t('enumDictionaries.retry')
      }}</UiButton></UiAlert
    >
    <UiAlert v-if="notice" type="success" class="feedback">{{ notice }}</UiAlert>
    <UiSpin :show="loading">
      <div v-if="data" class="inspection-workspace">
        <aside class="inspection-rail">
          <h2>{{ t('entityType.basic') }}</h2>
          <dl>
            <div>
              <dt>{{ t('entityType.propCount') }}</dt>
              <dd>{{ data.data_props?.length ?? 0 }}</dd>
            </div>
            <div>
              <dt>{{ t('entityType.relationCount') }}</dt>
              <dd>
                {{ usagesLoading ? t('common.loading') : (usages?.relations?.length ?? '—') }}
              </dd>
            </div>
            <div>
              <dt>{{ t('entityType.parentTypes') }}</dt>
              <dd>{{ parentChain.join(' / ') || t('entityType.noParent') }}</dd>
            </div>
          </dl>
          <p>{{ t(data.status === 'PUBLISHED' ? 'ui.frozen' : 'ui.working') }}</p>
          <h2>{{ t('entityType.validationState') }}</h2>
          <p v-if="!usages?.validations?.length">{{ t('entityType.noValidation') }}</p>
          <ul v-else class="validation-list">
            <li v-for="check in usages.validations" :key="check.check_code">
              <span class="mono">{{ check.check_code }}</span
              ><span>{{ check.state }} · {{ t(`report.states.${check.state}`) }}</span>
            </li>
          </ul>
        </aside>
        <div class="inspection-main">
          <UiTabs type="line" animated>
            <UiTabPane name="basic" :tab="t('entityType.basic')">
              <UiDescriptions :column="2" bordered content-style="overflow-wrap: anywhere">
                <UiDescriptionsItem :label="t('common.name')">{{ data.name }}</UiDescriptionsItem>
                <UiDescriptionsItem :label="t('common.iri')">{{ data.iri }}</UiDescriptionsItem>
                <UiDescriptionsItem :label="t('common.status')"
                  ><UiTag
                    :type="data.status === 'PUBLISHED' ? 'success' : 'default'"
                    size="small"
                    >{{ t(`resourceStatus.${data.status}`) }}</UiTag
                  ></UiDescriptionsItem
                >
                <UiDescriptionsItem :label="t('common.revision')">{{
                  data.current_revision
                }}</UiDescriptionsItem>
                <UiDescriptionsItem :label="t('common.label')">{{
                  localized(data.label_i18n)
                }}</UiDescriptionsItem>
                <UiDescriptionsItem :label="t('common.definition')">{{
                  localized(data.definition_i18n)
                }}</UiDescriptionsItem>
              </UiDescriptions>

              <!-- 校验状态：最近一次资产层校验里与该类型相关的检查项（四态） -->
              <section class="section">
                <h3 class="section-title">{{ t('entityType.validationState') }}</h3>
                <UiAlert v-if="!usages?.validations?.length" type="info" class="feedback">{{
                  t('entityType.noValidation')
                }}</UiAlert>
                <ul v-else class="validation-list">
                  <li v-for="item in usages.validations" :key="item.check_code">
                    <span class="check-tag" :style="{ '--dot': VALIDATION_VAR[item.state] }">
                      <i class="status-dot" />
                      {{ t(`report.states.${item.state}`) }}
                    </span>
                    <span>{{ item.check_code }}</span>
                    <span v-if="item.message" class="muted">{{ item.message }}</span>
                  </li>
                </ul>
              </section>
            </UiTabPane>
            <UiTabPane name="dataProps" :tab="t('entityType.dataProps')">
              <UiAlert v-if="data.status !== 'DRAFT'" type="info" class="feedback">{{
                t('entityProps.readOnly')
              }}</UiAlert>
              <UiSpace class="toolbar" justify="space-between" align="center">
                <p>{{ t('entityProps.pinHint') }}</p>
                <UiButton v-if="isDraft" type="primary" :disabled="busy" @click="openProperty()">{{
                  t('entityType.addProp')
                }}</UiButton>
              </UiSpace>
              <UiDataTable
                :columns="propColumns"
                :rows="data.data_props ?? []"
                :row-key="(prop: DataTypeProp) => prop.name"
                :scroll-x="1000"
              >
                <template #empty><UiEmpty :description="t('common.empty')" /></template>
              </UiDataTable>
            </UiTabPane>
            <UiTabPane name="hierarchy" :tab="t('entityType.hierarchy')">
              <UiButton v-if="isDraft" :disabled="busy" @click="openBasicEditor">{{
                t('entityType.editParents')
              }}</UiButton>
              <!-- 继承链：显示成名字而不是裸 id，未知 id 原样回退 -->
              <div v-if="parentChain.length" class="chain">
                <span v-for="(name, index) in parentChain" :key="name" class="chain-item">
                  <span v-if="index" class="chain-arrow" aria-hidden="true" />
                  <UiTag size="small">{{ name }}</UiTag>
                </span>
                <span class="chain-arrow" aria-hidden="true" />
                <UiTag size="small" type="primary">{{ localized(data.label_i18n) }}</UiTag>
              </div>
              <UiEmpty v-else :description="t('entityType.noParent')" />
            </UiTabPane>

            <UiTabPane name="relations" :tab="t('entityType.relations')">
              <UiDataTable
                :columns="relationColumns"
                :rows="usages?.relations ?? []"
                :row-key="(row: TypeRelationUsage) => row.id"
                :loading="usagesLoading"
                :scroll-x="640"
              >
                <template #empty><UiEmpty :description="t('entityType.noRelations')" /></template>
              </UiDataTable>
            </UiTabPane>

            <UiTabPane name="rules" :tab="t('entityType.rules')">
              <UiDataTable
                :columns="ruleColumns"
                :rows="usages?.rules ?? []"
                :row-key="(row: TypeRuleUsage) => row.id"
                :loading="usagesLoading"
                :scroll-x="560"
              >
                <template #empty><UiEmpty :description="t('entityType.noRules')" /></template>
              </UiDataTable>
            </UiTabPane>

            <UiTabPane name="references" :tab="t('entityType.references')">
              <UiSpin :show="usagesLoading">
                <section class="section">
                  <h3 class="section-title">{{ t('entityType.referencedBy') }}</h3>
                  <div v-if="usages?.domains?.length" class="ref-group">
                    <span class="ref-label">{{ t('page.domains') }}</span>
                    <UiSpace>
                      <UiTag
                        v-for="domain in usages.domains"
                        :key="domain.id"
                        size="small"
                        :type="domain.as_ref ? 'warning' : 'default'"
                      >
                        {{ localized(domain.label_i18n) }}
                        <template v-if="domain.as_ref">{{ t('domain.refMember') }}</template>
                      </UiTag>
                    </UiSpace>
                  </div>
                  <div v-if="usages?.ontologies?.length" class="ref-group">
                    <span class="ref-label">{{ t('page.ontologies') }}</span>
                    <UiSpace>
                      <UiTag v-for="onto in usages.ontologies" :key="onto.id" size="small">
                        {{
                          t('entityType.ontologyRef', {
                            name: localized(onto.label_i18n),
                            revision: onto.current_revision,
                          })
                        }}
                      </UiTag>
                    </UiSpace>
                  </div>
                  <UiEmpty
                    v-if="!usages?.domains?.length && !usages?.ontologies?.length"
                    :description="t('entityType.notReferenced')"
                  />
                </section>

                <section class="section">
                  <h3 class="section-title">{{ t('entityType.revisionHistory') }}</h3>
                  <ul v-if="usages?.revisions?.length" class="revision-list">
                    <li v-for="item in usages.revisions" :key="item.revision">
                      <span class="mono">{{
                        t('entityType.revisionValue', { revision: item.revision })
                      }}</span>
                      <span class="muted mono">{{ item.published_at }}</span>
                    </li>
                  </ul>
                  <UiEmpty v-else :description="t('entityType.noRevisions')" />
                </section>
              </UiSpin>
            </UiTabPane>
          </UiTabs>
        </div>
      </div>
      <UiEmpty v-else-if="!loading && !error" :description="t('common.empty')" />
    </UiSpin>
    <!-- 基本信息编辑。机读名是资源身份、IRI 由它推导，两者只读；其余字段走
         EntityTypeUpdate，更新 label/definition/parent_ids，不动 data_props。 -->
    <UiDrawer
      v-model:show="basicVisible"
      width="min(520px, 100vw)"
      :mask-closable="!busy"
      :close-on-esc="!busy"
    >
      <UiDrawerContent class="asset-editor" :title="t('entityType.edit')" :closable="!busy">
        <UiAlert v-if="basicError" type="error" class="feedback">{{ basicError }}</UiAlert>
        <FormContainer
          ref="basicFormRef"
          :model="basicForm"
          :rules="basicRules"
          :disabled="busy"
          label-placement="top"
        >
          <fieldset class="form-section">
            <legend>{{ t('common.name') }}</legend>
            <FormField :label="t('common.name')">
              <UiInput :value="data?.name ?? ''" disabled />
              <template #feedback>{{ t('entityType.nameImmutable') }}</template>
            </FormField>
          </fieldset>
          <fieldset class="form-section">
            <legend>{{ t('common.definition') }}</legend>
            <FormField :label="t('common.labelZh')" path="labelZh">
              <UiInput v-model:value="basicForm.labelZh" />
            </FormField>
            <FormField :label="t('common.labelEn')" path="labelEn">
              <UiInput v-model:value="basicForm.labelEn" />
            </FormField>
            <FormField :label="t('common.definitionZh')" path="definitionZh">
              <UiInput
                v-model:value="basicForm.definitionZh"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 4 }"
              />
            </FormField>
            <FormField :label="t('common.definitionEn')" path="definitionEn">
              <UiInput
                v-model:value="basicForm.definitionEn"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 4 }"
              />
            </FormField>
          </fieldset>
          <FormField :label="t('entityType.parentTypes')" path="parentIds">
            <UiSpace vertical style="width: 100%">
              <UiSelect
                v-model:value="basicForm.parentIds"
                :options="parentOptions"
                :loading="typeListLoading"
                multiple
                filterable
                clearable
              />
              <span>{{ t('entityType.parentHint') }}</span>
              <UiAlert v-if="typeListError" type="warning"
                >{{ typeListError }}
                <UiButton @click="loadTypeLabels">{{ t('ui.retry') }}</UiButton></UiAlert
              >
            </UiSpace>
          </FormField>
        </FormContainer>
        <template #footer>
          <UiSpace justify="end">
            <UiButton :disabled="busy" @click="basicVisible = false">
              {{ t('common.cancel') }}
            </UiButton>
            <UiButton type="primary" :loading="busy" @click="saveBasic">
              {{ t('common.save') }}
            </UiButton>
          </UiSpace>
        </template>
      </UiDrawerContent>
    </UiDrawer>
    <UiDrawer
      :show="propertyVisible"
      width="min(600px, 100vw)"
      :mask-closable="!busy && !propertyValidating"
      :close-on-esc="!busy && !propertyValidating"
      @update:show="propertyVisible = $event"
    >
      <UiDrawerContent
        class="asset-editor"
        :title="editingName ? t('entityProps.edit') : t('entityType.addProp')"
        :closable="!busy && !propertyValidating"
      >
        <UiAlert v-if="editorError" type="error" class="feedback">{{ editorError }}</UiAlert>
        <FormContainer
          :key="propertySession"
          ref="propertyFormRef"
          :model="form"
          :rules="propertyFormRules"
          :disabled="busy"
          :submitting="busy"
          :aria-busy="busy || propertyValidating"
          label-placement="top"
          @submit="submitProperty"
        >
          <fieldset class="form-section">
            <legend>{{ t('common.definition') }}</legend>
            <FormField
              :label="t('common.name')"
              path="name"
              :help="t('entityProps.nameHelp')"
              required
              ><UiInput
                v-model:value="form.name"
                :disabled="editingName !== null"
                :placeholder="t('enumDictionaries.nameHint')"
            /></FormField>
            <FormField :label="t('common.labelZh')" path="label_i18n.zh-CN" required
              ><UiInput v-model:value="form.label_i18n['zh-CN']"
            /></FormField>
            <FormField :label="t('common.labelEn')" path="label_i18n.en-US"
              ><UiInput v-model:value="form.label_i18n['en-US']"
            /></FormField>
            <FormField :label="t('enumDictionaries.definitionZh')" path="definition_i18n.zh-CN"
              ><UiInput v-model:value="form.definition_i18n['zh-CN']" type="textarea"
            /></FormField>
            <FormField :label="t('enumDictionaries.definitionEn')" path="definition_i18n.en-US"
              ><UiInput v-model:value="form.definition_i18n['en-US']" type="textarea"
            /></FormField>
          </fieldset>
          <fieldset class="form-section">
            <legend>{{ t('common.datatype') }}</legend>
            <FormField :label="t('common.datatype')" path="datatype" required
              ><UiSelect
                :value="form.datatype"
                :options="datatypeOptions"
                @update:value="changeDatatype"
            /></FormField>
            <template v-if="form.datatype === 'enum'">
              <UiAlert v-if="dictionaryError" type="error" class="feedback"
                >{{ dictionaryError }}
                <UiButton size="small" @click="loadDictionaries()">{{
                  t('enumDictionaries.retry')
                }}</UiButton></UiAlert
              >
              <FormField :label="t('entityProps.dictionary')" path="enum_dict_id" required>
                <UiSelect
                  :value="form.enum_dict_id"
                  :options="dictionaryOptions"
                  :loading="dictionaryLoading"
                  :placeholder="t('entityProps.searchDictionary')"
                  filterable
                  remote
                  clearable
                  @search="loadDictionaries"
                  @update:value="changeDictionary"
                />
              </FormField>
              <UiAlert v-if="versionsError" type="error" class="feedback"
                >{{ versionsError }}
                <UiButton
                  v-if="form.enum_dict_id !== null"
                  size="small"
                  @click="loadVersions(form.enum_dict_id)"
                  >{{ t('enumDictionaries.retry') }}</UiButton
                ></UiAlert
              >
              <FormField
                :label="t('enumDictionaries.pinnedRevision')"
                path="enum_dict_revision"
                :help="t('entityProps.pinHint')"
                required
              >
                <UiSelect
                  v-model:value="form.enum_dict_revision"
                  :options="versionOptions"
                  :loading="versionsLoading"
                  :disabled="form.enum_dict_id === null || versionsLoading"
                  :placeholder="t('entityProps.chooseVersion')"
                />
              </FormField>
              <UiAlert
                v-if="form.enum_dict_revision !== null && newerVersion > form.enum_dict_revision"
                type="info"
                class="feedback"
                >{{ t('entityProps.newerVersion', { revision: newerVersion }) }}</UiAlert
              >
            </template>
            <FormField :label="t('entityProps.defaultValue')" path="default_value">
              <UiSelect
                v-if="form.datatype === 'enum'"
                v-model:value="form.default_value"
                :options="defaultOptions"
                :disabled="!selectedVersion"
                :placeholder="t('entityProps.noDefault')"
                clearable
              />
              <UiInput
                v-else
                :value="form.default_value"
                :placeholder="t('entityProps.noDefault')"
                clearable
                @update:value="form.default_value = $event === '' ? null : $event"
              />
            </FormField>
          </fieldset>
          <fieldset class="form-section">
            <legend>{{ t('entityProps.minCardinality') }}</legend>
            <FormField :label="t('common.nullable')" path="nullable"
              ><UiSwitch v-model:value="form.nullable" :aria-label="t('common.nullable')"
            /></FormField>
            <FormField
              :label="t('entityProps.minCardinality')"
              path="min_cardinality"
              :help="t('entityProps.cardinalityHelp')"
            >
              <UiInput
                :value="form.min_cardinality"
                inputmode="numeric"
                :placeholder="t('entityProps.noConstraint')"
                clearable
                @update:value="form.min_cardinality = $event === '' ? null : $event"
              />
            </FormField>
            <FormField
              :label="t('entityProps.maxCardinality')"
              path="max_cardinality"
              :help="t('entityProps.cardinalityOrder')"
            >
              <UiInput
                :value="form.max_cardinality"
                inputmode="numeric"
                :placeholder="t('entityProps.noConstraint')"
                clearable
                @update:value="form.max_cardinality = $event === '' ? null : $event"
              />
            </FormField>
            <FormField
              :label="t('entityProps.minValue')"
              path="min_value"
              :help="t('entityProps.numericHelp')"
            >
              <UiInput
                :value="form.min_value"
                :placeholder="t('entityProps.noConstraint')"
                clearable
                @update:value="form.min_value = $event === '' ? null : $event"
              />
            </FormField>
            <FormField
              :label="t('entityProps.maxValue')"
              path="max_value"
              :help="t('entityProps.numericHelp')"
            >
              <UiInput
                :value="form.max_value"
                :placeholder="t('entityProps.noConstraint')"
                clearable
                @update:value="form.max_value = $event === '' ? null : $event"
              />
            </FormField>
          </fieldset>
          <FormField :label="t('entityProps.sourceClauseRef')" path="source_clause_ref">
            <UiInput
              v-model:value="form.source_clause_ref"
              :placeholder="t('entityProps.noConstraint')"
              clearable
            />
          </FormField>
        </FormContainer>
        <template #footer
          ><UiSpace>
            <UiButton
              type="primary"
              :loading="busy || propertyValidating"
              :disabled="!isDraft || versionsLoading || propertyValidating"
              @click="submitProperty"
              >{{ t('common.save') }}</UiButton
            >
            <UiButton :disabled="busy || propertyValidating" @click="propertyVisible = false">{{
              t('common.cancel')
            }}</UiButton>
          </UiSpace></template
        >
      </UiDrawerContent>
    </UiDrawer>
  </div>
</template>

<style scoped>
.feedback,
.toolbar {
  margin-bottom: 16px;
}
.spaced {
  margin-top: 16px;
}

/* 基本信息页签里的分区（校验状态）与引用页签的分组 */
.section + .section {
  margin-top: 20px;
}

.section-title {
  margin: 20px 0 10px;
  font-size: var(--font-h3);
  font-weight: 500;
  color: var(--text-secondary);
}

.validation-list {
  display: grid;
  gap: 6px;
  padding: 0;
  margin: 0;
  list-style: none;
  font-size: var(--font-caption);
}

.validation-list li {
  display: flex;
  gap: 10px;
  align-items: center;
}

.check-tag {
  display: inline-flex;
  flex: none;
  gap: 6px;
  align-items: center;
  width: 78px;
  padding: 1px 8px;
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-pill);
}

.status-dot {
  width: 6px;
  height: 6px;
  background: var(--dot);
  border-radius: 50%;
}

/* 继承链：父类型 → 当前类型 */
.chain {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.chain-item {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.chain-arrow {
  color: var(--text-tertiary);
}

/* 箭头用 CSS 画，避免模板里出现裸文本（no-raw-text 规则） */
.chain-arrow::before {
  content: '→';
}

.ref-group {
  display: flex;
  gap: 10px;
  align-items: baseline;
  margin-bottom: 8px;
}

.ref-label {
  flex: none;
  width: 72px;
  color: var(--text-tertiary);
  font-size: var(--font-caption);
}

.revision-list {
  display: grid;
  gap: 4px;
  padding: 0;
  margin: 0;
  list-style: none;
  font-size: var(--font-caption);
}

.revision-list li {
  display: flex;
  gap: 12px;
  align-items: baseline;
}

.muted {
  color: var(--text-tertiary);
}
</style>

<style scoped src="../styles/observatory.css"></style>
