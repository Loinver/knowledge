<script setup lang="ts">
import type { FormInst, FormRules } from 'naive-ui'
import {
  NAlert,
  NButton,
  NDataTable,
  NDescriptions,
  NDescriptionsItem,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NPopconfirm,
  NSelect,
  NSpace,
  NSpin,
  NSwitch,
  NTabPane,
  NTabs,
  NTag,
} from 'naive-ui'
import { computed, h, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import type {
  DataTypeProp,
  DataTypePropInput,
  EntityType,
  EntityTypeUsages,
  TypeRelationUsage,
  TypeRuleUsage,
} from '@/api/entity-types'
import { entityTypesApi } from '@/api/entity-types'
import type { EnumDictionary } from '@/api/enum-dictionaries'
import { enumDictionariesApi } from '@/api/enum-dictionaries'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'

const { t, locale } = useI18n()
const { toMessage } = useApiError()
const route = useRoute()
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const data = ref<EntityType | null>(null)
/** 关联关系 / 规则 / 引用与版本：一次请求取全，三个页签共用。 */
const usages = ref<EntityTypeUsages | null>(null)
const usagesLoading = ref(false)
/** 父类型 id → 标签，用于把继承链显示成名字而不是裸 id。 */
const typeLabels = ref<Record<number, string>>({})
const showEditor = ref(false)
const editorError = ref('')
const editingName = ref<string | null>(null)
const form = ref(emptyProperty())
const dictionaries = ref<EnumDictionary[]>([])
const dictionaryLoading = ref(false)
const dictionaryError = ref('')
const versions = ref<EnumDictionary[]>([])
const versionsLoading = ref(false)
const versionsError = ref('')
let loadGeneration = 0
let editorGeneration = 0
let dictionaryController: AbortController | undefined
let versionController: AbortController | undefined
let alive = true

/**
 * 基本信息（标签 / 定义）的编辑态。
 *
 * 机读名 name 是资源的身份，创建后不可改，表单里只读展示；IRI 由
 * namespace + name 推导，同样不在这里改。其余可编辑字段与后端
 * `EntityTypeUpdate` 一致：只送 label_i18n / definition_i18n，不碰 data_props。
 */
const showBasicEditor = ref(false)
const basicError = ref('')
const basicFormRef = ref<FormInst | null>(null)
const basicForm = ref({ labelZh: '', labelEn: '', definitionZh: '', definitionEn: '' })

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
  const generation = ++loadGeneration
  editorGeneration++
  showEditor.value = false
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
  void loadUsages(id, generation)
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
  try {
    const list = await entityTypesApi.list({ page_size: 200 })
    const map: Record<number, string> = {}
    for (const item of list) {
      map[item.id] = item.label_i18n?.[locale.value] ?? item.label_i18n?.['zh-CN'] ?? item.name
    }
    typeLabels.value = map
  } catch {
    typeLabels.value = {}
  }
}

async function handlePublish() {
  if (!data.value || data.value.status !== 'DRAFT' || busy.value) return
  const generation = loadGeneration
  busy.value = true
  error.value = ''
  try {
    await entityTypesApi.publish(data.value.id)
    if (alive && generation === loadGeneration) await loadDetail()
  } catch (err) {
    if (alive && generation === loadGeneration) error.value = failure(err)
  } finally {
    if (alive) busy.value = false
  }
}

/**
 * 打开基本信息编辑抽屉。只允许在草稿态编辑——已发布/已归档的资源是冻结快照。
 */
function openBasicEditor() {
  if (!data.value || data.value.status !== 'DRAFT' || busy.value) return
  basicForm.value = {
    labelZh: data.value.label_i18n?.['zh-CN'] ?? '',
    labelEn: data.value.label_i18n?.['en-US'] ?? '',
    definitionZh: data.value.definition_i18n?.['zh-CN'] ?? '',
    definitionEn: data.value.definition_i18n?.['en-US'] ?? '',
  }
  basicError.value = ''
  showBasicEditor.value = true
}

/** 中文标签必填；英文缺省时回退到中文，不留空 key。 */
function collectBasicPayload(): {
  label_i18n: Record<string, string>
  definition_i18n: Record<string, string>
} {
  const f = basicForm.value
  const labelZh = f.labelZh.trim()
  const label: Record<string, string> = { 'zh-CN': labelZh }
  label['en-US'] = f.labelEn.trim() || labelZh

  const definition: Record<string, string> = {}
  if (f.definitionZh.trim()) definition['zh-CN'] = f.definitionZh.trim()
  if (f.definitionEn.trim()) definition['en-US'] = f.definitionEn.trim()
  return { label_i18n: label, definition_i18n: definition }
}

async function saveBasic() {
  const entity = data.value
  if (!entity || entity.status !== 'DRAFT' || busy.value) return
  try {
    await basicFormRef.value?.validate()
  } catch {
    return
  }
  const generation = loadGeneration
  busy.value = true
  basicError.value = ''
  error.value = ''
  notice.value = ''
  try {
    const result = await entityTypesApi.update(entity.id, {
      ...collectBasicPayload(),
      if_match: entity.current_revision,
      edit_revision: entity.edit_revision,
    })
    if (!alive || generation !== loadGeneration) return
    data.value = result
    notice.value = t('entityType.basicSaved')
    showBasicEditor.value = false
  } catch (err) {
    if (!alive || generation !== loadGeneration) return
    basicError.value = failure(err)
  } finally {
    if (alive) busy.value = false
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
  if (data.value?.status !== 'DRAFT' || busy.value) return
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
  }
}

async function saveProperties(props: DataTypePropInput[], editor = false) {
  const entity = data.value
  if (!entity || entity.status !== 'DRAFT' || busy.value) return
  const generation = loadGeneration
  const edit = editorGeneration
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
    if (!alive || generation !== loadGeneration) return
    data.value = result
    notice.value = t('entityProps.saved')
    if (editor && edit === editorGeneration) showEditor.value = false
  } catch (err) {
    if (!alive || generation !== loadGeneration) return
    if (editor && edit === editorGeneration) editorError.value = failure(err)
    else error.value = failure(err)
  } finally {
    if (alive) busy.value = false
  }
}

function submitProperty() {
  if (!data.value || busy.value || versionsLoading.value) return
  const input = form.value
  if (
    (editingName.value === null && !/^[A-Z][A-Za-z0-9]*$/.test(input.name)) ||
    !input.name.trim() ||
    !input.label_i18n['zh-CN'].trim()
  ) {
    editorError.value = t('entityProps.invalid')
    return
  }
  if (
    (data.value.data_props ?? []).some(
      (prop) => prop.name === input.name && prop.name !== editingName.value,
    )
  ) {
    editorError.value = t('entityProps.duplicate')
    return
  }
  if (input.datatype === 'enum') {
    if (input.enum_dict_id === null || !selectedVersion.value) {
      editorError.value = t('entityProps.chooseVersion')
      return
    }
    if (
      input.default_value !== null &&
      !selectedVersion.value.entries.some((entry) => entry.value === input.default_value)
    ) {
      editorError.value = t('entityProps.invalidDefault')
      return
    }
  }
  const props = (data.value.data_props ?? []).map(propertyInput)
  const replacement: DataTypePropInput = JSON.parse(JSON.stringify(input))
  if (editingName.value === null) props.push(replacement)
  else {
    const index = props.findIndex((prop) => prop.name === editingName.value)
    if (index < 0) return
    props[index] = replacement
  }
  void saveProperties(props, true)
}

function removeProperty(prop: DataTypeProp) {
  const props = (data.value?.data_props ?? [])
    .filter((item) => item.name !== prop.name)
    .map(propertyInput)
  void saveProperties(props)
}

const isDraft = computed(() => data.value?.status === 'DRAFT')
const selectedVersion = computed(() =>
  versions.value.find((item) => item.revision === form.value.enum_dict_revision),
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
  ...(isDraft.value
    ? [
        {
          title: t('common.actions'),
          key: 'actions',
          render: (prop: DataTypeProp) =>
            h(NSpace, {}, () => [
              h(
                NButton,
                { size: 'small', disabled: busy.value, onClick: () => openProperty(prop) },
                () => t('common.edit'),
              ),
              h(
                NPopconfirm,
                { onPositiveClick: () => removeProperty(prop) },
                {
                  trigger: () =>
                    h(NButton, { size: 'small', type: 'error', disabled: busy.value }, () =>
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
      h(NTag, { size: 'small', type: row.status === 'PUBLISHED' ? 'success' : 'default' }, () =>
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
watch(showEditor, (show) => {
  if (!show) {
    editorGeneration++
    dictionaryController?.abort()
    versionController?.abort()
  }
})
onBeforeUnmount(() => {
  alive = false
  loadGeneration++
  dictionaryController?.abort()
  versionController?.abort()
})
</script>

<template>
  <div>
    <PageHeader
      :title="data ? localized(data.label_i18n) : t('page.entityDetail')"
      :description="data?.iri"
    >
      <template #actions>
        <n-button v-if="data && isDraft" :disabled="busy" @click="openBasicEditor">
          {{ t('common.edit') }}
        </n-button>
        <n-button
          v-if="data && isDraft"
          type="primary"
          :disabled="busy"
          :loading="busy"
          @click="handlePublish"
        >
          {{ t('common.publish') }}
        </n-button>
      </template>
    </PageHeader>
    <n-alert v-if="error" type="error" class="feedback"
      >{{ error }}
      <n-button size="small" :disabled="busy" @click="loadDetail">{{
        t('enumDictionaries.retry')
      }}</n-button></n-alert
    >
    <n-alert v-if="notice" type="success" class="feedback">{{ notice }}</n-alert>
    <n-spin :show="loading">
      <n-tabs v-if="data" type="line" animated>
        <n-tab-pane name="basic" :tab="t('entityType.basic')">
          <n-descriptions :column="2" bordered>
            <n-descriptions-item :label="t('common.name')">{{ data.name }}</n-descriptions-item>
            <n-descriptions-item :label="t('common.iri')">{{ data.iri }}</n-descriptions-item>
            <n-descriptions-item :label="t('common.status')"
              ><n-tag :type="data.status === 'PUBLISHED' ? 'success' : 'default'" size="small">{{
                t(`resourceStatus.${data.status}`)
              }}</n-tag></n-descriptions-item
            >
            <n-descriptions-item :label="t('common.revision')">{{
              data.current_revision
            }}</n-descriptions-item>
            <n-descriptions-item :label="t('common.label')">{{
              localized(data.label_i18n)
            }}</n-descriptions-item>
            <n-descriptions-item :label="t('common.definition')">{{
              localized(data.definition_i18n)
            }}</n-descriptions-item>
          </n-descriptions>

          <!-- 校验状态：最近一次资产层校验里与该类型相关的检查项（四态） -->
          <section class="section">
            <h3 class="section-title">{{ t('entityType.validationState') }}</h3>
            <n-alert v-if="!usages?.validations?.length" type="info" class="feedback">{{
              t('entityType.noValidation')
            }}</n-alert>
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
        </n-tab-pane>
        <n-tab-pane name="dataProps" :tab="t('entityType.dataProps')">
          <n-alert v-if="!isDraft" type="info" class="feedback">{{
            t('entityProps.readOnly')
          }}</n-alert>
          <n-space class="toolbar" justify="space-between" align="center">
            <p>{{ t('entityProps.pinHint') }}</p>
            <n-button v-if="isDraft" type="primary" :disabled="busy" @click="openProperty()">{{
              t('entityType.addProp')
            }}</n-button>
          </n-space>
          <n-data-table
            :columns="propColumns"
            :data="data.data_props ?? []"
            :row-key="(prop: DataTypeProp) => prop.name"
            :scroll-x="1000"
          >
            <template #empty><n-empty :description="t('common.empty')" /></template>
          </n-data-table>
        </n-tab-pane>
        <n-tab-pane name="hierarchy" :tab="t('entityType.hierarchy')">
          <!-- 继承链：显示成名字而不是裸 id，未知 id 原样回退 -->
          <div v-if="parentChain.length" class="chain">
            <span v-for="(name, index) in parentChain" :key="name" class="chain-item">
              <span v-if="index" class="chain-arrow" aria-hidden="true" />
              <n-tag size="small">{{ name }}</n-tag>
            </span>
            <span class="chain-arrow" aria-hidden="true" />
            <n-tag size="small" type="primary">{{ localized(data.label_i18n) }}</n-tag>
          </div>
          <n-empty v-else :description="t('entityType.noParent')" />
        </n-tab-pane>

        <n-tab-pane name="relations" :tab="t('entityType.relations')">
          <n-data-table
            :columns="relationColumns"
            :data="usages?.relations ?? []"
            :row-key="(row: TypeRelationUsage) => row.id"
            :loading="usagesLoading"
            :scroll-x="640"
          >
            <template #empty><n-empty :description="t('entityType.noRelations')" /></template>
          </n-data-table>
        </n-tab-pane>

        <n-tab-pane name="rules" :tab="t('entityType.rules')">
          <n-data-table
            :columns="ruleColumns"
            :data="usages?.rules ?? []"
            :row-key="(row: TypeRuleUsage) => row.id"
            :loading="usagesLoading"
            :scroll-x="560"
          >
            <template #empty><n-empty :description="t('entityType.noRules')" /></template>
          </n-data-table>
        </n-tab-pane>

        <n-tab-pane name="references" :tab="t('entityType.references')">
          <n-spin :show="usagesLoading">
            <section class="section">
              <h3 class="section-title">{{ t('entityType.referencedBy') }}</h3>
              <div v-if="usages?.domains?.length" class="ref-group">
                <span class="ref-label">{{ t('page.domains') }}</span>
                <n-space>
                  <n-tag
                    v-for="domain in usages.domains"
                    :key="domain.id"
                    size="small"
                    :type="domain.as_ref ? 'warning' : 'default'"
                  >
                    {{ localized(domain.label_i18n) }}
                    <template v-if="domain.as_ref">{{ t('domain.refMember') }}</template>
                  </n-tag>
                </n-space>
              </div>
              <div v-if="usages?.ontologies?.length" class="ref-group">
                <span class="ref-label">{{ t('page.ontologies') }}</span>
                <n-space>
                  <n-tag v-for="onto in usages.ontologies" :key="onto.id" size="small">
                    {{
                      t('entityType.ontologyRef', {
                        name: localized(onto.label_i18n),
                        revision: onto.current_revision,
                      })
                    }}
                  </n-tag>
                </n-space>
              </div>
              <n-empty
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
              <n-empty v-else :description="t('entityType.noRevisions')" />
            </section>
          </n-spin>
        </n-tab-pane>
      </n-tabs>
      <n-empty v-else-if="!loading && !error" :description="t('common.empty')" />
    </n-spin>
    <!-- 基本信息编辑。机读名是资源身份、IRI 由它推导，两者只读；其余字段走
         EntityTypeUpdate，只送 label/definition，不动 data_props。 -->
    <n-drawer
      v-model:show="showBasicEditor"
      :width="520"
      :mask-closable="!busy"
      :close-on-esc="!busy"
    >
      <n-drawer-content :title="t('entityType.edit')" :closable="!busy">
        <n-alert v-if="basicError" type="error" class="feedback">{{ basicError }}</n-alert>
        <n-form
          ref="basicFormRef"
          :model="basicForm"
          :rules="basicRules"
          :disabled="busy"
          label-placement="top"
        >
          <n-form-item :label="t('common.name')">
            <n-input :value="data?.name ?? ''" disabled />
            <template #feedback>{{ t('entityType.nameImmutable') }}</template>
          </n-form-item>
          <n-form-item :label="t('common.labelZh')" path="labelZh">
            <n-input v-model:value="basicForm.labelZh" />
          </n-form-item>
          <n-form-item :label="t('common.labelEn')" path="labelEn">
            <n-input v-model:value="basicForm.labelEn" />
          </n-form-item>
          <n-form-item :label="t('common.definitionZh')" path="definitionZh">
            <n-input
              v-model:value="basicForm.definitionZh"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
            />
          </n-form-item>
          <n-form-item :label="t('common.definitionEn')" path="definitionEn">
            <n-input
              v-model:value="basicForm.definitionEn"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
            />
          </n-form-item>
        </n-form>
        <template #footer>
          <n-space justify="end">
            <n-button :disabled="busy" @click="showBasicEditor = false">
              {{ t('common.cancel') }}
            </n-button>
            <n-button type="primary" :loading="busy" @click="saveBasic">
              {{ t('common.save') }}
            </n-button>
          </n-space>
        </template>
      </n-drawer-content>
    </n-drawer>
    <n-drawer
      :show="showEditor"
      :width="600"
      :mask-closable="!busy"
      :close-on-esc="!busy"
      @update:show="showEditor = $event"
    >
      <n-drawer-content
        :title="editingName ? t('entityProps.edit') : t('entityType.addProp')"
        :closable="!busy"
      >
        <n-alert v-if="editorError" type="error" class="feedback">{{ editorError }}</n-alert>
        <n-form :disabled="busy" label-placement="top">
          <n-form-item :label="t('common.name')" required
            ><n-input
              v-model:value="form.name"
              :disabled="editingName !== null"
              :placeholder="t('enumDictionaries.nameHint')"
          /></n-form-item>
          <n-form-item :label="t('common.labelZh')" required
            ><n-input v-model:value="form.label_i18n['zh-CN']"
          /></n-form-item>
          <n-form-item :label="t('common.labelEn')"
            ><n-input v-model:value="form.label_i18n['en-US']"
          /></n-form-item>
          <n-form-item :label="t('enumDictionaries.definitionZh')"
            ><n-input v-model:value="form.definition_i18n['zh-CN']" type="textarea"
          /></n-form-item>
          <n-form-item :label="t('enumDictionaries.definitionEn')"
            ><n-input v-model:value="form.definition_i18n['en-US']" type="textarea"
          /></n-form-item>
          <n-form-item :label="t('common.datatype')" required
            ><n-select
              :value="form.datatype"
              :options="datatypeOptions"
              @update:value="changeDatatype"
          /></n-form-item>
          <template v-if="form.datatype === 'enum'">
            <n-alert v-if="dictionaryError" type="error" class="feedback"
              >{{ dictionaryError }}
              <n-button size="small" @click="loadDictionaries()">{{
                t('enumDictionaries.retry')
              }}</n-button></n-alert
            >
            <n-form-item :label="t('entityProps.dictionary')" required>
              <n-select
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
            </n-form-item>
            <n-alert v-if="versionsError" type="error" class="feedback"
              >{{ versionsError }}
              <n-button
                v-if="form.enum_dict_id !== null"
                size="small"
                @click="loadVersions(form.enum_dict_id)"
                >{{ t('enumDictionaries.retry') }}</n-button
              ></n-alert
            >
            <n-form-item :label="t('enumDictionaries.pinnedRevision')" required>
              <n-select
                v-model:value="form.enum_dict_revision"
                :options="versionOptions"
                :loading="versionsLoading"
                :disabled="form.enum_dict_id === null || versionsLoading"
                :placeholder="t('entityProps.chooseVersion')"
              />
            </n-form-item>
            <n-alert
              v-if="form.enum_dict_revision !== null && newerVersion > form.enum_dict_revision"
              type="info"
              class="feedback"
              >{{ t('entityProps.newerVersion', { revision: newerVersion }) }}</n-alert
            >
            <p>{{ t('entityProps.pinHint') }}</p>
          </template>
          <n-form-item :label="t('entityProps.defaultValue')">
            <n-select
              v-if="form.datatype === 'enum'"
              v-model:value="form.default_value"
              :options="defaultOptions"
              :disabled="!selectedVersion"
              :placeholder="t('entityProps.noDefault')"
              clearable
            />
            <n-input
              v-else
              :value="form.default_value"
              :placeholder="t('entityProps.noDefault')"
              clearable
              @update:value="form.default_value = $event === '' ? null : $event"
            />
          </n-form-item>
          <n-form-item :label="t('common.nullable')"
            ><n-switch v-model:value="form.nullable" :aria-label="t('common.nullable')"
          /></n-form-item>
        </n-form>
        <template #footer
          ><n-space>
            <n-button
              type="primary"
              :loading="busy"
              :disabled="!isDraft || versionsLoading"
              @click="submitProperty"
              >{{ t('common.save') }}</n-button
            >
            <n-button :disabled="busy" @click="showEditor = false">{{
              t('common.cancel')
            }}</n-button>
          </n-space></template
        >
      </n-drawer-content>
    </n-drawer>
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
