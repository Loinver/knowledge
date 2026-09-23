<script setup lang="ts">
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NDescriptions,
  NDescriptionsItem,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NPagination,
  NPopconfirm,
  NSelect,
  NSpace,
  NSpin,
  NTabPane,
  NTabs,
} from 'naive-ui'
import { computed, h, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import type {
  EnumDictionary,
  EnumDictionaryInput,
  EnumReference,
  EnumSort,
} from '@/api/enum-dictionaries'
import { enumDictionariesApi } from '@/api/enum-dictionaries'
import { useApiError } from '@/composables/useApiError'

const { t, locale } = useI18n()
const { toMessage } = useApiError()
const router = useRouter()
const items = ref<EnumDictionary[]>([])
const total = ref(0)
const page = ref(1)
const search = ref('')
const query = ref('')
const sort = ref<EnumSort>('name')
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const showEditor = ref(false)
const editorLoading = ref(false)
const editorReady = ref(false)
const editorError = ref('')
const saved = ref<EnumDictionary | null>(null)
const form = ref<EnumDictionaryInput>(emptyDictionary())
const revisions = ref<EnumDictionary[]>([])
const references = ref<EnumReference[]>([])
const selectedRevision = ref<number | null>(null)
const activeTab = ref('edit')
let listController: AbortController | undefined
let editorController: AbortController | undefined
let editorGeneration = 0
let alive = true

function emptyDictionary(): EnumDictionaryInput {
  return {
    name: '',
    label_i18n: { 'zh-CN': '', 'en-US': '' },
    definition_i18n: { 'zh-CN': '', 'en-US': '' },
    entries: [{ value: '', label_i18n: { 'zh-CN': '', 'en-US': '' } }],
  }
}

function copyInput(item: EnumDictionary): EnumDictionaryInput {
  return {
    name: item.name,
    label_i18n: { ...item.label_i18n },
    definition_i18n: { ...item.definition_i18n },
    entries: item.entries.map((entry) => ({ ...entry, label_i18n: { ...entry.label_i18n } })),
  }
}

function localized(labels: Record<string, string> | null | undefined) {
  return labels?.[locale.value]?.trim() || t('enumDictionaries.untranslated')
}

function failure(err: unknown) {
  const { code, params } = (err as { code?: string; params?: Record<string, unknown> }) ?? {}
  if (params?.reason === 'enum_dictionary_in_use') return t('enumDictionaries.inUse')
  if (code === 'KG.REVISION_CONFLICT') return t('enumDictionaries.conflict')
  if (code === 'KG.ALREADY_EXISTS') return t('enumDictionaries.duplicate')
  return toMessage(err)
}

async function load() {
  listController?.abort()
  const controller = new AbortController()
  listController = controller
  loading.value = true
  error.value = ''
  items.value = []
  try {
    const result = await enumDictionariesApi.list(
      { page: page.value, page_size: 20, q: query.value, sort: sort.value },
      controller.signal,
    )
    if (controller.signal.aborted || !alive) return
    if (page.value > 1 && result.items.length === 0) {
      page.value = Math.max(1, Math.ceil(result.total / 20))
      return
    }
    items.value = result.items
    total.value = result.total
  } catch (err) {
    if (!controller.signal.aborted && alive) error.value = failure(err)
  } finally {
    if (!controller.signal.aborted && alive) loading.value = false
  }
}

function doSearch() {
  if (query.value === search.value.trim() && page.value === 1) void load()
  else {
    page.value = 1
    query.value = search.value.trim()
  }
}

function clearSearch() {
  search.value = ''
  doSearch()
}

function changeSort(value: EnumSort) {
  sort.value = value
  page.value = 1
}

function openCreate() {
  if (busy.value) return
  editorController?.abort()
  editorGeneration++
  saved.value = null
  form.value = emptyDictionary()
  revisions.value = []
  references.value = []
  editorError.value = ''
  editorLoading.value = false
  editorReady.value = true
  activeTab.value = 'edit'
  showEditor.value = true
}

async function openEdit(item: EnumDictionary) {
  if (busy.value) return
  editorController?.abort()
  const controller = new AbortController()
  editorController = controller
  editorGeneration++
  saved.value = item
  form.value = copyInput(item)
  revisions.value = []
  references.value = []
  selectedRevision.value = null
  editorError.value = ''
  activeTab.value = 'edit'
  showEditor.value = true
  editorLoading.value = true
  editorReady.value = false
  try {
    const [current, history, uses] = await Promise.all([
      enumDictionariesApi.get(item.id, controller.signal),
      enumDictionariesApi.revisions(item.id, controller.signal),
      enumDictionariesApi.references(item.id, controller.signal),
    ])
    if (controller.signal.aborted || !alive) return
    saved.value = current
    form.value = copyInput(current)
    revisions.value = history
    references.value = uses
    selectedRevision.value = current.revision
    editorReady.value = true
  } catch (err) {
    if (!controller.signal.aborted && alive) editorError.value = failure(err)
  } finally {
    if (!controller.signal.aborted && alive) editorLoading.value = false
  }
}

function validInput() {
  const input = form.value
  return (
    /^[A-Z][A-Za-z0-9]*$/.test(input.name) &&
    !!input.label_i18n['zh-CN']?.trim() &&
    !!input.definition_i18n['zh-CN']?.trim() &&
    input.entries.length > 0 &&
    input.entries.every((entry) => entry.value.trim() && entry.label_i18n['zh-CN']?.trim()) &&
    new Set(input.entries.map((entry) => entry.value.trim())).size === input.entries.length
  )
}

async function submit() {
  if (busy.value || !editorReady.value) return
  if (!validInput()) {
    editorError.value = t('enumDictionaries.invalid')
    return
  }
  const generation = editorGeneration
  busy.value = true
  editorError.value = ''
  notice.value = ''
  try {
    const payload = JSON.parse(JSON.stringify(form.value)) as EnumDictionaryInput
    if (saved.value) await enumDictionariesApi.update(saved.value, payload)
    else await enumDictionariesApi.create(payload)
    if (!alive || generation !== editorGeneration) return
    showEditor.value = false
    notice.value = t('enumDictionaries.saved')
    await load()
  } catch (err) {
    if (alive && generation === editorGeneration) editorError.value = failure(err)
  } finally {
    if (alive) busy.value = false
  }
}

async function remove(item: EnumDictionary) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await enumDictionariesApi.remove(item)
    if (!alive) return
    notice.value = t('enumDictionaries.deleted')
    await load()
  } catch (err) {
    if (alive) error.value = failure(err)
  } finally {
    if (alive) busy.value = false
  }
}

watch([page, query, sort], load, { immediate: true })
watch(showEditor, (show) => {
  if (!show) {
    editorController?.abort()
    editorGeneration++
  }
})
onBeforeUnmount(() => {
  alive = false
  listController?.abort()
  editorController?.abort()
})

const historyItem = computed(() =>
  revisions.value.find((item) => item.revision === selectedRevision.value),
)
const revisionOptions = computed(() =>
  revisions.value.map((item) => ({
    value: item.revision,
    label: t('enumDictionaries.revisionLabel', { revision: item.revision }),
  })),
)
const sortOptions = computed(() =>
  ['name', '-name', 'id', '-id'].map((value) => ({
    value,
    label: t(`enumDictionaries.sorts.${value}`),
  })),
)
const entryColumns = computed(() => [
  { title: t('enumDictionaries.value'), key: 'value' },
  {
    title: t('common.label'),
    key: 'label_i18n',
    render: (entry: EnumDictionary['entries'][number]) => localized(entry.label_i18n),
  },
])
const columns = computed(() => [
  { title: t('common.name'), key: 'name' },
  {
    title: t('common.label'),
    key: 'label_i18n',
    render: (item: EnumDictionary) => localized(item.label_i18n),
  },
  { title: t('common.revision'), key: 'revision' },
  {
    title: t('enumDictionaries.entries'),
    key: 'entries',
    render: (item: EnumDictionary) => item.entries.length,
  },
  {
    title: t('common.actions'),
    key: 'actions',
    render: (item: EnumDictionary) =>
      h(NSpace, {}, () => [
        h(NButton, { size: 'small', disabled: busy.value, onClick: () => openEdit(item) }, () =>
          t('enumDictionaries.details'),
        ),
        h(
          NPopconfirm,
          { onPositiveClick: () => remove(item) },
          {
            trigger: () =>
              h(NButton, { size: 'small', type: 'error', disabled: busy.value }, () =>
                t('common.delete'),
              ),
            default: () => t('enumDictionaries.confirmDelete', { name: item.name }),
          },
        ),
      ]),
  },
])
const referenceColumns = computed(() => [
  {
    title: t('enumDictionaries.resource'),
    key: 'resource_name',
    render: (item: EnumReference) =>
      item.resource_kind === 'ENTITY'
        ? h(
            NButton,
            {
              text: true,
              type: 'primary',
              onClick: () =>
                router.push({ name: 'entity-detail', params: { id: item.resource_id } }),
            },
            () => item.resource_name,
          )
        : item.resource_name,
  },
  { title: t('enumDictionaries.property'), key: 'property_name' },
  {
    title: t('common.status'),
    key: 'resource_status',
    render: (item: EnumReference) => t(`resourceStatus.${item.resource_status}`),
  },
  { title: t('enumDictionaries.pinnedRevision'), key: 'enum_dict_revision' },
  { title: t('enumDictionaries.latestRevision'), key: 'latest_revision' },
])
</script>

<template>
  <div class="enum-page">
    <n-card :title="t('enumDictionaries.title')" :bordered="false">
      <template #header-extra
        ><n-button type="primary" :disabled="busy" @click="openCreate">{{
          t('enumDictionaries.create')
        }}</n-button></template
      >
      <p class="intro">{{ t('enumDictionaries.intro') }}</p>
      <n-space class="toolbar" align="center">
        <n-input
          v-model:value="search"
          :aria-label="t('common.search')"
          :placeholder="t('enumDictionaries.search')"
          clearable
          @keyup.enter="doSearch"
          @clear="clearSearch"
        />
        <n-button @click="doSearch">{{ t('common.search') }}</n-button>
        <n-select
          :value="sort"
          :options="sortOptions"
          :aria-label="t('enumDictionaries.sort')"
          style="width: 180px"
          @update:value="changeSort"
        />
      </n-space>
      <n-alert v-if="error" type="error" class="feedback"
        >{{ error }}
        <n-button size="small" @click="load">{{ t('enumDictionaries.retry') }}</n-button></n-alert
      >
      <n-alert v-if="notice" type="success" class="feedback">{{ notice }}</n-alert>
      <n-data-table
        :columns="columns"
        :data="items"
        :loading="loading"
        :row-key="(row: EnumDictionary) => row.id"
        remote
      >
        <template #empty
          ><n-empty
            :description="error ? t('enumDictionaries.loadFailed') : t('enumDictionaries.empty')"
        /></template>
      </n-data-table>
      <n-pagination
        v-if="total > 0"
        v-model:page="page"
        :item-count="total"
        :page-size="20"
        :disabled="loading"
        class="pagination"
      />
    </n-card>
    <n-drawer
      :show="showEditor"
      :width="760"
      :close-on-esc="!busy"
      :mask-closable="!busy"
      @update:show="showEditor = $event"
    >
      <n-drawer-content
        :title="saved ? t('enumDictionaries.details') : t('enumDictionaries.create')"
        :closable="!busy"
      >
        <n-alert v-if="editorError" type="error" class="feedback">
          {{ editorError }}
          <n-button
            v-if="saved && !editorReady && !editorLoading"
            size="small"
            @click="openEdit(saved)"
            >{{ t('enumDictionaries.retry') }}</n-button
          >
        </n-alert>
        <n-spin :show="editorLoading">
          <n-tabs v-model:value="activeTab" type="line">
            <n-tab-pane name="edit" :tab="t('common.edit')">
              <p v-if="saved">
                {{ t('enumDictionaries.editRevision', { revision: saved.revision }) }}
              </p>
              <n-form :disabled="busy || !editorReady" label-placement="top">
                <n-form-item :label="t('common.name')" required
                  ><n-input
                    v-model:value="form.name"
                    :disabled="!!saved"
                    :placeholder="t('enumDictionaries.nameHint')"
                /></n-form-item>
                <n-form-item :label="t('common.labelZh')" required
                  ><n-input v-model:value="form.label_i18n['zh-CN']"
                /></n-form-item>
                <n-form-item :label="t('common.labelEn')"
                  ><n-input v-model:value="form.label_i18n['en-US']"
                /></n-form-item>
                <n-form-item :label="t('enumDictionaries.definitionZh')" required
                  ><n-input v-model:value="form.definition_i18n['zh-CN']" type="textarea"
                /></n-form-item>
                <n-form-item :label="t('enumDictionaries.definitionEn')"
                  ><n-input v-model:value="form.definition_i18n['en-US']" type="textarea"
                /></n-form-item>
                <h3>{{ t('enumDictionaries.entries') }}</h3>
                <div v-for="(entry, index) in form.entries" :key="index" class="entry-row">
                  <n-form-item :label="t('enumDictionaries.value')" required
                    ><n-input v-model:value="entry.value"
                  /></n-form-item>
                  <n-form-item :label="t('common.labelZh')" required
                    ><n-input v-model:value="entry.label_i18n['zh-CN']"
                  /></n-form-item>
                  <n-form-item :label="t('common.labelEn')"
                    ><n-input v-model:value="entry.label_i18n['en-US']"
                  /></n-form-item>
                  <n-button
                    :disabled="busy || editorLoading || form.entries.length === 1"
                    :aria-label="t('enumDictionaries.removeEntry', { index: index + 1 })"
                    @click="form.entries.splice(index, 1)"
                    >{{ t('common.delete') }}</n-button
                  >
                </div>
                <n-button
                  :disabled="busy || !editorReady"
                  @click="
                    form.entries.push({ value: '', label_i18n: { 'zh-CN': '', 'en-US': '' } })
                  "
                  >{{ t('enumDictionaries.addEntry') }}</n-button
                >
              </n-form>
            </n-tab-pane>
            <n-tab-pane v-if="saved" name="history" :tab="t('enumDictionaries.history')">
              <p>{{ t('enumDictionaries.historyHint') }}</p>
              <n-select
                v-model:value="selectedRevision"
                :options="revisionOptions"
                :aria-label="t('common.revision')"
              />
              <template v-if="historyItem">
                <n-descriptions :column="1" bordered class="history-description">
                  <n-descriptions-item :label="t('common.label')">{{
                    localized(historyItem.label_i18n)
                  }}</n-descriptions-item>
                  <n-descriptions-item :label="t('common.definition')">{{
                    localized(historyItem.definition_i18n)
                  }}</n-descriptions-item>
                </n-descriptions>
                <n-data-table :data="historyItem.entries" :columns="entryColumns" />
              </template>
              <n-empty
                v-else-if="!editorLoading"
                :description="t(editorReady ? 'common.empty' : 'enumDictionaries.loadFailed')"
              />
            </n-tab-pane>
            <n-tab-pane v-if="saved" name="references" :tab="t('enumDictionaries.references')">
              <p>{{ t('enumDictionaries.referencesHint') }}</p>
              <n-data-table :data="references" :columns="referenceColumns"
                ><template #empty
                  ><n-empty
                    :description="
                      t(
                        editorReady
                          ? 'enumDictionaries.noReferences'
                          : 'enumDictionaries.loadFailed',
                      )
                    " /></template
              ></n-data-table>
            </n-tab-pane>
          </n-tabs>
        </n-spin>
        <template #footer>
          <n-space>
            <n-button
              v-if="activeTab === 'edit'"
              type="primary"
              :loading="busy"
              :disabled="!editorReady"
              @click="submit"
              >{{ t('common.save') }}</n-button
            >
            <n-button :disabled="busy" @click="showEditor = false">{{
              t('common.cancel')
            }}</n-button>
          </n-space>
        </template>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<style scoped>
.intro {
  margin: 0 0 16px;
  color: var(--text-secondary);
}
.toolbar,
.feedback {
  margin-bottom: 16px;
}
.pagination,
.history-description {
  margin: 16px 0;
}
.entry-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr auto;
  gap: 8px;
  align-items: center;
}
</style>
