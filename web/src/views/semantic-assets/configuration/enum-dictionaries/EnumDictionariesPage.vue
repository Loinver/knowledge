<script setup lang="ts">
import { computed, h, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import type {
  EnumDictionary,
  EnumDictionaryInput,
  EnumReference,
  EnumSort,
} from '@/api/enum-dictionaries'
import { enumDictionariesApi } from '@/api/enum-dictionaries'
import SearchPanel from '@/components/business/SearchPanel.vue'
import SearchTable from '@/components/business/SearchTable.vue'
import PageHeader from '@/components/PageHeader.vue'
import type { DataTableColumns, FormInst, FormRules } from '@/components/ui'
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
  UiPopconfirm,
  UiSelect,
  UiSpace,
  UiSpin,
  UiTabPane,
  UiTabs,
} from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useAssetAccess } from '@/composables/useAssetAccess'
import { useDraftGuard } from '@/composables/useDraftGuard'

import AssetIdentity from '../../components/AssetIdentity.vue'

const { t, locale } = useI18n()
const { toMessage } = useApiError()
const { canWrite } = useAssetAccess()
const router = useRouter()
const route = useRoute()
const items = ref<EnumDictionary[]>([])
const total = ref(0)
const page = ref(Math.max(1, Number(route.query.page) || 1))
const query = ref(typeof route.query.q === 'string' ? route.query.q : '')
const search = ref(query.value)
const sort = ref<EnumSort>(
  ['name', '-name', 'id', '-id'].includes(String(route.query.sort))
    ? (route.query.sort as EnumSort)
    : 'name',
)
const loading = ref(false)
const busy = ref(false)
const validating = ref(false)
const error = ref('')
const notice = ref('')
const showEditor = ref(false)
const editorLoading = ref(false)
const editorReady = ref(false)
const editorError = ref('')
const saved = ref<EnumDictionary | null>(null)
const form = ref<EnumDictionaryInput>(emptyDictionary())
const formRef = ref<FormInst | null>(null)
const rules = computed<FormRules>(() => {
  const input = form.value
  // Snapshot dependencies so changing a sibling or removing a row rechecks existing errors.
  const values = input.entries.map((entry) => entry.value.trim())
  const required = {
    required: true,
    trigger: ['input', 'blur'],
  }
  const result: FormRules = {
    name: [
      required,
      {
        pattern: /^[A-Z][A-Za-z0-9]*$/,
        message: t('ontology.namePattern'),
        trigger: ['input', 'blur'],
      },
    ],
    'label_i18n.zh-CN': required,
    'definition_i18n.zh-CN': required,
    entries: {
      required: true,
      type: 'array',
      message: t('enumDictionaries.entriesRequired'),
    },
  }
  input.entries.forEach((_entry, index) => {
    const value = values[index]
    result[`entries.${index}.value`] = [
      required,
      {
        trigger: ['input', 'blur'],
        validator: () =>
          !value ||
          values.filter((other) => other === value).length === 1 ||
          t('enumDictionaries.valueDuplicate'),
      },
    ]
    result[`entries.${index}.label_i18n.zh-CN`] = required
  })
  return result
})
const revisions = ref<EnumDictionary[]>([])
const references = ref<EnumReference[]>([])
const selectedRevision = ref<number | null>(null)
const activeTab = ref('edit')
const editorVisible = useDraftGuard(
  showEditor,
  () => form.value,
  () => canWrite.value && editorReady.value,
)
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

function resetSearch() {
  search.value = ''
  query.value = ''
  sort.value = 'name'
  page.value = 1
}

function changeSort(value: EnumSort) {
  sort.value = value
  page.value = 1
}

function openCreate() {
  if (!canWrite.value || busy.value || validating.value) return
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
  if (busy.value || validating.value) return
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

async function removeEntry(index: number, errors: Record<string, string>) {
  if (
    !canWrite.value ||
    busy.value ||
    validating.value ||
    !editorReady.value ||
    form.value.entries.length <= 1
  )
    return
  const input = form.value
  const generation = editorGeneration
  const instance = formRef.value
  const paths = Object.keys(errors).flatMap((path) => {
    const entry = /^entries\.(\d+)\.(.+)$/.exec(path)
    if (!entry) return [path]
    const position = Number(entry[1])
    if (position === index) return []
    return [`entries.${position > index ? position - 1 : position}.${entry[2]}`]
  })
  instance?.restoreValidation()
  input.entries.splice(index, 1)
  await nextTick()
  if (
    !alive ||
    input !== form.value ||
    generation !== editorGeneration ||
    instance !== formRef.value
  )
    return
  // Revalidate only previously invalid entries at their new positions; untouched rows stay quiet.
  if (paths.length) await instance?.validate(undefined, paths).catch(() => undefined)
}

async function submit() {
  if (
    !showEditor.value ||
    !canWrite.value ||
    activeTab.value !== 'edit' ||
    busy.value ||
    validating.value ||
    !editorReady.value
  )
    return
  const generation = editorGeneration
  const input = form.value
  const item = saved.value
  validating.value = true
  editorError.value = ''
  notice.value = ''
  try {
    try {
      await formRef.value?.validate()
    } catch {
      return
    }
    if (
      !alive ||
      generation !== editorGeneration ||
      input !== form.value ||
      item !== saved.value ||
      !showEditor.value ||
      !canWrite.value ||
      activeTab.value !== 'edit' ||
      !editorReady.value
    )
      return
    if (!validInput()) {
      editorError.value = t('enumDictionaries.invalid')
      return
    }
    const payload = JSON.parse(JSON.stringify(input)) as EnumDictionaryInput
    validating.value = false
    busy.value = true
    if (item) await enumDictionariesApi.update(item, payload)
    else await enumDictionariesApi.create(payload)
    if (!alive || generation !== editorGeneration) return
    showEditor.value = false
    notice.value = t('enumDictionaries.saved')
    await load()
  } catch (err) {
    if (alive && generation === editorGeneration) editorError.value = failure(err)
  } finally {
    if (alive) {
      validating.value = false
      busy.value = false
    }
  }
}

async function remove(item: EnumDictionary) {
  if (!canWrite.value || busy.value || validating.value) return
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
watch([page, query, sort], () => {
  void router.replace({
    query: {
      ...route.query,
      q: query.value || undefined,
      sort: sort.value,
      page: page.value > 1 ? page.value : undefined,
    },
  })
})
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
const entryColumns = computed<DataTableColumns<EnumDictionary['entries'][number]>>(() => [
  { title: t('enumDictionaries.value'), key: 'value' },
  {
    title: t('common.label'),
    key: 'label_i18n',
    render: (entry: EnumDictionary['entries'][number]) => localized(entry.label_i18n),
  },
])
const columns = computed<DataTableColumns<EnumDictionary>>(() => [
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
    fixed: 'right',
    width: 200,
    render: (item: EnumDictionary) =>
      h(UiSpace, {}, () => [
        h(UiButton, { size: 'small', disabled: busy.value, onClick: () => openEdit(item) }, () =>
          t('enumDictionaries.details'),
        ),
        h(
          UiPopconfirm,
          { disabled: busy.value || !canWrite.value, onPositiveClick: () => remove(item) },
          {
            trigger: () =>
              h(
                UiButton,
                { size: 'small', type: 'error', disabled: busy.value || !canWrite.value },
                () => t('common.delete'),
              ),
            default: () => t('enumDictionaries.confirmDelete', { name: item.name }),
          },
        ),
      ]),
  },
])
const referenceColumns = computed<DataTableColumns<EnumReference>>(() => [
  {
    title: t('enumDictionaries.resource'),
    key: 'resource_name',
    render: (item: EnumReference) =>
      item.resource_kind === 'ENTITY'
        ? h(
            UiButton,
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
  <div class="enum-page asset-page">
    <PageHeader :title="t('enumDictionaries.title')" :description="t('enumDictionaries.intro')">
      <template #actions>
        <UiButton type="primary" :disabled="busy || !canWrite" @click="openCreate">
          {{ t('enumDictionaries.create') }}
        </UiButton>
      </template>
    </PageHeader>
    <UiAlert v-if="!canWrite" type="info">{{ t('governanceUi.readOnly') }}</UiAlert>
    <section class="ledger-surface">
      <SearchPanel
        v-model:query="search"
        class="toolbar"
        :label="t('common.search')"
        :placeholder="t('enumDictionaries.search')"
        :loading="loading"
        @submit="doSearch"
        @clear="clearSearch"
        @reset="resetSearch"
      >
        <template #filter>
          <FormField :label="t('enumDictionaries.sort')" :show-feedback="false">
            <UiSelect
              :value="sort"
              :options="sortOptions"
              :aria-label="t('enumDictionaries.sort')"
              style="width: 180px"
              @update:value="changeSort"
            />
          </FormField>
        </template>
      </SearchPanel>
      <UiAlert v-if="notice" type="success" class="feedback">{{ notice }}</UiAlert>
      <SearchTable
        :columns="columns"
        :rows="items"
        :loading="loading"
        :error="error"
        :label="t('enumDictionaries.title')"
        :row-key="(row: EnumDictionary) => row.id"
        :searchable="false"
        mode="remote"
        :total="total"
        :page="page"
        :page-size="20"
        :pagination="!loading && !error && total > 0"
        size="small"
        :max-height="600"
        :scroll-x="760"
        @update:page="page = $event"
        @retry="load"
      >
        <template #toolbar>
          <header class="ledger-caption">
            <h2>{{ t('enumDictionaries.title') }}</h2>
            <span>{{
              t('assetLedger.resultCount', {
                count:
                  loading || error
                    ? t('common.noneValue')
                    : new Intl.NumberFormat(locale).format(total),
              })
            }}</span>
          </header>
        </template>
        <template #empty
          ><UiEmpty :description="t(query ? 'ui.emptyFiltered' : 'enumDictionaries.empty')"
        /></template>
      </SearchTable>
    </section>
    <UiDrawer
      :show="editorVisible"
      width="min(760px, 100vw)"
      :close-on-esc="!busy && !validating"
      :mask-closable="!busy && !validating"
      @update:show="editorVisible = $event"
    >
      <UiDrawerContent
        class="asset-editor"
        :title="saved ? t('enumDictionaries.details') : t('enumDictionaries.create')"
        :closable="!busy && !validating"
      >
        <div class="editor-identity">
          <AssetIdentity
            :name="
              (activeTab === 'history' ? historyItem?.name : saved?.name) ||
              form.name ||
              t('enumDictionaries.create')
            "
            :revision="activeTab === 'history' ? (selectedRevision ?? undefined) : saved?.revision"
            :context="
              activeTab === 'history'
                ? t('enumDictionaries.history')
                : t('governanceUi.currentEntries')
            "
          />
        </div>
        <UiAlert v-if="!canWrite" type="info" class="feedback">{{
          t('governanceUi.readOnly')
        }}</UiAlert>
        <UiAlert v-if="editorError" type="error" class="feedback">
          {{ editorError }}
          <UiButton
            v-if="saved && !editorReady && !editorLoading"
            size="small"
            @click="openEdit(saved)"
            >{{ t('enumDictionaries.retry') }}</UiButton
          >
        </UiAlert>
        <p v-if="editorLoading" role="status">{{ t('common.loading') }}</p>
        <UiSpin :show="editorLoading">
          <UiTabs
            v-if="editorReady"
            v-model:value="activeTab"
            :disabled="busy || validating"
            type="line"
          >
            <UiTabPane name="edit" :tab="t('governanceUi.currentEntries')">
              <p v-if="saved">
                {{ t('enumDictionaries.editRevision', { revision: saved.revision }) }}
              </p>
              <FormContainer
                ref="formRef"
                v-slot="{ errors: fieldErrors }"
                :model="form"
                :rules="rules"
                :disabled="busy || !editorReady || !canWrite"
                :submitting="busy"
                :readonly="!canWrite"
                label-placement="top"
                @submit="submit"
              >
                <fieldset class="form-section">
                  <legend>{{ t('common.name') }}</legend>
                  <FormField path="name" :label="t('common.name')" required
                    ><UiInput
                      v-model:value="form.name"
                      :disabled="!!saved || busy || !canWrite"
                      :placeholder="t('enumDictionaries.nameHint')"
                  /></FormField>
                  <FormField path="label_i18n.zh-CN" :label="t('common.labelZh')" required
                    ><UiInput v-model:value="form.label_i18n['zh-CN']"
                  /></FormField>
                  <FormField path="label_i18n.en-US" :label="t('common.labelEn')"
                    ><UiInput v-model:value="form.label_i18n['en-US']"
                  /></FormField>
                </fieldset>
                <fieldset class="form-section">
                  <legend>{{ t('common.definition') }}</legend>
                  <FormField
                    path="definition_i18n.zh-CN"
                    :label="t('enumDictionaries.definitionZh')"
                    required
                    ><UiInput v-model:value="form.definition_i18n['zh-CN']" type="textarea"
                  /></FormField>
                  <FormField
                    path="definition_i18n.en-US"
                    :label="t('enumDictionaries.definitionEn')"
                    ><UiInput v-model:value="form.definition_i18n['en-US']" type="textarea"
                  /></FormField>
                </fieldset>
                <fieldset class="form-section">
                  <legend>{{ t('enumDictionaries.entries') }}</legend>
                  <FormField path="entries" :label="t('enumDictionaries.entries')">
                    <div v-for="(entry, index) in form.entries" :key="index" class="entry-row">
                      <FormField
                        :path="`entries.${index}.value`"
                        :label="t('enumDictionaries.value')"
                        required
                        ><UiInput v-model:value="entry.value"
                      /></FormField>
                      <FormField
                        :path="`entries.${index}.label_i18n.zh-CN`"
                        :label="t('common.labelZh')"
                        required
                        ><UiInput v-model:value="entry.label_i18n['zh-CN']"
                      /></FormField>
                      <FormField
                        :path="`entries.${index}.label_i18n.en-US`"
                        :label="t('common.labelEn')"
                        ><UiInput v-model:value="entry.label_i18n['en-US']"
                      /></FormField>
                      <UiButton
                        :disabled="!canWrite || busy || editorLoading || form.entries.length === 1"
                        :aria-label="t('enumDictionaries.removeEntry', { index: index + 1 })"
                        @click="removeEntry(index, fieldErrors)"
                        >{{ t('common.delete') }}</UiButton
                      >
                    </div>
                    <UiButton
                      :disabled="!canWrite || busy || !editorReady"
                      @click="
                        form.entries.push({ value: '', label_i18n: { 'zh-CN': '', 'en-US': '' } })
                      "
                      >{{ t('enumDictionaries.addEntry') }}</UiButton
                    >
                  </FormField>
                </fieldset></FormContainer
              >
            </UiTabPane>
            <UiTabPane v-if="saved" name="history" :tab="t('enumDictionaries.history')">
              <UiAlert type="info" class="feedback">{{
                t('governanceUi.frozenRevision', { revision: selectedRevision ?? '—' })
              }}</UiAlert>
              <p>{{ t('enumDictionaries.historyHint') }}</p>
              <UiSelect
                v-model:value="selectedRevision"
                :options="revisionOptions"
                :aria-label="t('common.revision')"
              />
              <template v-if="historyItem">
                <UiDescriptions :column="1" bordered class="history-description">
                  <UiDescriptionsItem :label="t('common.label')">{{
                    localized(historyItem.label_i18n)
                  }}</UiDescriptionsItem>
                  <UiDescriptionsItem :label="t('common.definition')">{{
                    localized(historyItem.definition_i18n)
                  }}</UiDescriptionsItem>
                </UiDescriptions>
                <UiDataTable mode="none" :rows="historyItem.entries" :columns="entryColumns" />
              </template>
              <UiEmpty
                v-else-if="!editorLoading"
                :description="t(editorReady ? 'common.empty' : 'enumDictionaries.loadFailed')"
              />
            </UiTabPane>
            <UiTabPane v-if="saved" name="references" :tab="t('enumDictionaries.references')">
              <p>{{ t('enumDictionaries.referencesHint') }}</p>
              <UiDataTable mode="none" :rows="references" :columns="referenceColumns"
                ><template #empty
                  ><UiEmpty
                    :description="
                      t(
                        editorReady
                          ? 'enumDictionaries.noReferences'
                          : 'enumDictionaries.loadFailed',
                      )
                    " /></template
              ></UiDataTable>
            </UiTabPane>
          </UiTabs>
        </UiSpin>
        <template #footer>
          <UiSpace>
            <UiButton
              v-if="activeTab === 'edit'"
              type="primary"
              :loading="busy || validating"
              :disabled="busy || validating || !canWrite || !editorReady"
              @click="submit"
              >{{ t('common.save') }}</UiButton
            >
            <UiButton :disabled="busy || validating" @click="editorVisible = false">{{
              t('common.cancel')
            }}</UiButton>
          </UiSpace>
        </template>
      </UiDrawerContent>
    </UiDrawer>
  </div>
</template>

<style scoped>
.enum-page {
  display: grid;
  gap: var(--space-4);
}
.enum-page :deep(.ui-card) {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-medium);
}
.toolbar,
.feedback {
  margin-bottom: 16px;
}
.history-description {
  margin: 16px 0;
}
.entry-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr auto;
  gap: 8px;
  align-items: center;
}
@media (max-width: 640px) {
  .entry-row {
    grid-template-columns: 1fr;
    border-bottom: 1px solid var(--border);
    padding: 12px 0;
  }
}
</style>

<style scoped src="../../styles/observatory.css"></style>
