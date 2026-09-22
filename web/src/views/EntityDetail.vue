<script setup lang="ts">
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

import type { DataTypeProp, DataTypePropInput, EntityType } from '@/api/client'
import { api } from '@/api/client'
import type { EnumDictionary } from '@/api/enum-dictionaries'
import { enumDictionariesApi } from '@/api/enum-dictionaries'
import { useApiError } from '@/composables/useApiError'

const { t, locale } = useI18n()
const { toMessage } = useApiError()
const route = useRoute()
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const data = ref<EntityType | null>(null)
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
    const result = await api.entityTypes.get(id)
    if (alive && generation === loadGeneration) data.value = result
  } catch (err) {
    if (alive && generation === loadGeneration) error.value = failure(err)
  } finally {
    if (alive && generation === loadGeneration) loading.value = false
  }
}

async function handlePublish() {
  if (!data.value || data.value.status !== 'DRAFT' || busy.value) return
  const generation = loadGeneration
  busy.value = true
  error.value = ''
  try {
    await api.entityTypes.publish(data.value.id)
    if (alive && generation === loadGeneration) await loadDetail()
  } catch (err) {
    if (alive && generation === loadGeneration) error.value = failure(err)
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
    const result = await api.entityTypes.update(entity.id, {
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

watch(() => route.params.id, loadDetail, { immediate: true })
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
          <n-button
            class="spaced"
            type="primary"
            :disabled="!isDraft || busy"
            :loading="busy"
            @click="handlePublish"
            >{{ t('common.publish') }}</n-button
          >
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
          <n-space v-if="data.parent_ids?.length"
            ><n-tag v-for="id in data.parent_ids" :key="id">{{ id }}</n-tag></n-space
          >
          <n-empty v-else :description="t('common.empty')" />
        </n-tab-pane>
        <n-tab-pane name="relations" :tab="t('entityType.relations')"
          ><n-empty :description="t('common.empty')"
        /></n-tab-pane>
        <n-tab-pane name="rules" :tab="t('entityType.rules')"
          ><n-empty :description="t('common.empty')"
        /></n-tab-pane>
        <n-tab-pane name="references" :tab="t('entityType.references')"
          ><n-empty :description="t('common.empty')"
        /></n-tab-pane>
      </n-tabs>
      <n-empty v-else-if="!loading && !error" :description="t('common.empty')" />
    </n-spin>
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
</style>
