<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  AiModelCapability,
  AiModelConfig,
  AiModelCreate,
  AiModelDefault,
  AiModelQuery,
  AiModelUpdate,
} from '@/api/ai-models'
import { aiModelsApi } from '@/api/ai-models'
import { getSessionGeneration, subscribeTokens } from '@/api/tokens'
import PageHeader from '@/components/PageHeader.vue'
import type { DataTableColumns, FormInst, FormRules } from '@/components/ui'
import {
  FormContainer,
  FormField,
  SearchTable,
  UiAlert,
  UiButton,
  UiCard,
  UiCheckbox,
  UiDrawer,
  UiDrawerContent,
  UiEmpty,
  UiInput,
  UiInputNumber,
  UiPopconfirm,
  UiSelect,
  UiSpace,
  UiSpin,
  UiSwitch,
  UiTag,
} from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useDraftGuard } from '@/composables/useDraftGuard'
import { useOwnedMutation } from '@/composables/useOwnedMutation'
import { useAuthStore } from '@/stores/auth'

type ModelForm = {
  name: string
  capability: AiModelCapability
  baseUrl: string
  model: string
  timeoutSeconds: number | null
  modelVersion: string
  enabled: boolean
  apiKey: string
  clearKey: boolean
}

const capabilities: AiModelCapability[] = ['CHAT', 'EMBEDDING']
const pageSize = 20
const { t } = useI18n()
const { toMessage } = useApiError()
const auth = useAuthStore()
const items = ref<AiModelConfig[]>([])
const total = ref(0)
const page = ref(1)
const search = ref('')
const query = ref('')
const capabilityFilter = ref<AiModelCapability | null>(null)
const enabledFilter = ref<boolean | null>(null)
const enabledSelection = computed<string | null>({
  get: () => (enabledFilter.value === null ? null : String(enabledFilter.value)),
  set: (value) => {
    enabledFilter.value = value === null ? null : value === 'true'
  },
})
const sort = ref<NonNullable<AiModelQuery['sort']>>('name')
const loading = ref(false)
const error = ref('')
const notice = ref('')
const selections = ref<AiModelDefault[]>([])
const defaultModels = ref<Partial<Record<AiModelCapability, AiModelConfig>>>({})
const defaultsLoading = ref(false)
const defaultsError = ref('')
const showEditor = ref(false)
const editorLoading = ref(false)
const editorReady = ref(false)
const editorError = ref('')
const editing = ref<AiModelConfig | null>(null)
const editorMutation = useOwnedMutation(
  () => [showEditor.value, editing.value?.id, auth.user?.id, auth.isAdmin],
  failure,
)
const actionMutation = useOwnedMutation(() => [auth.user?.id, auth.isAdmin], failure)
const { busy: saving } = editorMutation
const busy = computed(() => saving.value || actionMutation.busy.value)
const formRef = ref<FormInst | null>(null)
const form = ref<ModelForm>(emptyForm())
const editorVisible = useDraftGuard(
  showEditor,
  () => form.value,
  () => auth.isAdmin && editorReady.value,
)
const actionsDisabled = computed(
  () => !auth.isAdmin || busy.value || loading.value || defaultsLoading.value,
)
let listController: AbortController | undefined
let defaultsController: AbortController | undefined
let editorController: AbortController | undefined
let editorGeneration = 0
let alive = true
const listSession = ref(getSessionGeneration())
const stopListSession = subscribeTokens(() => {
  listSession.value = getSessionGeneration()
})
const listIdentity = computed(() =>
  JSON.stringify([listSession.value, auth.user?.id, auth.user?.role, auth.user?.status]),
)
const listQuery = computed(() => ({
  q: query.value || undefined,
  capability: capabilityFilter.value ?? undefined,
  enabled: enabledFilter.value ?? undefined,
  page: page.value,
  page_size: pageSize,
  sort: sort.value,
}))
const listKey = computed(() => JSON.stringify([listIdentity.value, listQuery.value]))
watch(
  listKey,
  () => {
    listController?.abort()
    items.value = []
    total.value = 0
    error.value = ''
    loading.value = false
  },
  { flush: 'sync' },
)

function emptyForm(): ModelForm {
  return {
    name: '',
    capability: 'CHAT',
    baseUrl: '',
    model: '',
    timeoutSeconds: 30,
    modelVersion: '1',
    enabled: false,
    apiKey: '',
    clearKey: false,
  }
}

function copyForm(configuration: AiModelConfig): ModelForm {
  return {
    name: configuration.name,
    capability: configuration.capability,
    baseUrl: configuration.base_url,
    model: configuration.model,
    timeoutSeconds: configuration.timeout_seconds,
    modelVersion: configuration.model_version,
    enabled: configuration.enabled,
    apiKey: '',
    clearKey: false,
  }
}

function capabilityLabel(capability: AiModelCapability): string {
  return t(capability === 'CHAT' ? 'aiModels.capabilities.chat' : 'aiModels.capabilities.embedding')
}

function failure(cause: unknown): string {
  const body = cause as { code?: string; params?: { reason?: string } } | undefined
  if (body?.code === 'KG.REVISION_CONFLICT') return t('aiModels.conflict')
  if (body?.code === 'KG.RESOURCE_NOT_FOUND') return t('aiModels.notFound')
  if (body?.code === 'KG.ALREADY_EXISTS') return t('aiModels.duplicateName')
  if (body?.code === 'KG.INVALID_REQUEST') {
    switch (body.params?.reason) {
      case 'api_key_invalid':
        return t('aiModels.invalidKeyMask')
      case 'enabled_requires_key':
        return t('aiModels.keyRequired')
      case 'api_key_required_for_origin_change':
        return t('aiModels.originKeyRequired')
      case 'capability_mismatch':
      case 'config_must_be_enabled_with_key':
        return t('aiModels.defaultEligibility')
    }
  }
  return toMessage(cause)
}

const capabilityOptions = computed(() =>
  capabilities.map((value) => ({ value, label: capabilityLabel(value) })),
)
const enabledOptions = computed(() => [
  { value: 'true', label: t('aiModels.enabled') },
  { value: 'false', label: t('aiModels.disabled') },
])
const sortOptions = computed(() => [
  { value: 'name', label: t('aiModels.sorts.name') },
  { value: '-name', label: t('aiModels.sorts.nameDescending') },
  { value: '-id', label: t('aiModels.sorts.newest') },
])
const originChanged = computed(() => {
  if (!editing.value?.has_key) return false
  try {
    return new URL(form.value.baseUrl).origin !== new URL(editing.value.base_url).origin
  } catch {
    return false
  }
})

async function load() {
  const session = getSessionGeneration()
  listController?.abort()
  if (!alive || !auth.isAdmin) return
  const controller = new AbortController()
  listController = controller
  const key = listKey.value
  const owns = () =>
    !controller.signal.aborted &&
    alive &&
    session === getSessionGeneration() &&
    key === listKey.value &&
    auth.isAdmin
  loading.value = true
  error.value = ''
  try {
    const result = await aiModelsApi.page(listQuery.value, controller.signal)
    if (!owns()) return
    if (page.value > Math.max(1, Math.ceil(result.total / pageSize))) {
      page.value = Math.max(1, Math.ceil(result.total / pageSize))
      return
    }
    items.value = result.items
    total.value = result.total
  } catch (cause) {
    if (owns()) error.value = failure(cause)
  } finally {
    if (owns()) loading.value = false
  }
}

async function loadDefaults() {
  const session = getSessionGeneration()
  defaultsController?.abort()
  if (!auth.isAdmin) return
  const controller = new AbortController()
  defaultsController = controller
  defaultsLoading.value = true
  defaultsError.value = ''
  selections.value = []
  defaultModels.value = {}
  try {
    const current = await aiModelsApi.defaults(controller.signal)
    const configurations = await Promise.all(
      current.map((selection) =>
        selection.config_id === null
          ? null
          : aiModelsApi.getDetailById(selection.config_id, controller.signal),
      ),
    )
    if (controller.signal.aborted || !alive || session !== getSessionGeneration() || !auth.isAdmin)
      return
    selections.value = current
    defaultModels.value = Object.fromEntries(
      current.flatMap((selection, index) =>
        configurations[index] ? [[selection.capability, configurations[index]]] : [],
      ),
    )
  } catch (cause) {
    if (!controller.signal.aborted && alive && session === getSessionGeneration() && auth.isAdmin)
      defaultsError.value = failure(cause)
  } finally {
    if (!controller.signal.aborted && alive) defaultsLoading.value = false
  }
}

async function refresh() {
  await Promise.all([load(), loadDefaults()])
}

function clearSearch() {
  search.value = ''
  doSearch()
}
function resetSearch() {
  const changed =
    query.value !== '' ||
    capabilityFilter.value !== null ||
    enabledFilter.value !== null ||
    sort.value !== 'name' ||
    page.value !== 1
  search.value = ''
  query.value = ''
  capabilityFilter.value = null
  enabledFilter.value = null
  sort.value = 'name'
  page.value = 1
  if (!changed) void load()
}

function doSearch() {
  const keyword = search.value.trim()
  if (query.value === keyword && page.value === 1) void load()
  else {
    query.value = keyword
    page.value = 1
  }
}

function openCreate() {
  if (actionsDisabled.value) return
  editorController?.abort()
  editorGeneration++
  editing.value = null
  form.value = emptyForm()
  editorError.value = ''
  editorLoading.value = false
  editorReady.value = true
  showEditor.value = true
}

async function openEdit(configuration: AiModelConfig) {
  const session = getSessionGeneration()
  if (!auth.isAdmin || busy.value) return
  editorController?.abort()
  const controller = new AbortController()
  editorController = controller
  editorGeneration++
  editing.value = configuration
  form.value = copyForm(configuration)
  editorError.value = ''
  editorReady.value = false
  editorLoading.value = true
  showEditor.value = true
  try {
    const current = await aiModelsApi.getDetailById(configuration.id, controller.signal)
    if (
      controller.signal.aborted ||
      !alive ||
      !showEditor.value ||
      session !== getSessionGeneration() ||
      !auth.isAdmin
    )
      return
    editing.value = current
    form.value = copyForm(current)
    editorReady.value = true
  } catch (cause) {
    if (!controller.signal.aborted && alive && session === getSessionGeneration() && auth.isAdmin)
      editorError.value = failure(cause)
  } finally {
    if (!controller.signal.aborted && alive) editorLoading.value = false
  }
}

function reloadEditor() {
  const configuration = editing.value
  if (!configuration || busy.value) return
  editorVisible.value = false
  if (!showEditor.value) void openEdit(configuration)
}

function validAddress(value: unknown): boolean {
  if (typeof value !== 'string') return false
  try {
    const address = value.trim()
    const url = new URL(address)
    return (
      !/\s/.test(address) &&
      !Array.from(address).some(
        (character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127,
      ) &&
      ['http:', 'https:'].includes(url.protocol) &&
      !url.username &&
      !url.password &&
      !url.search &&
      !url.hash
    )
  } catch {
    return false
  }
}
const rules = computed<FormRules>(() => ({
  name: {
    required: true,
    max: 200,
    message: t('aiModels.requiredFields'),
    trigger: ['blur', 'input'],
  },
  capability: {
    required: true,
    validator: (_rule, value) => capabilities.includes(value as AiModelCapability),
    message: t('aiModels.requiredFields'),
  },
  baseUrl: {
    required: true,
    validator: (_rule, value) => validAddress(value),
    message: t('aiModels.invalidUrl'),
    trigger: ['blur', 'input'],
  },
  model: {
    required: true,
    max: 255,
    message: t('aiModels.requiredFields'),
    trigger: ['blur', 'input'],
  },
  modelVersion: {
    required: true,
    max: 100,
    message: t('aiModels.requiredFields'),
    trigger: ['blur', 'input'],
  },
  timeoutSeconds: {
    required: true,
    type: 'integer',
    min: 1,
    max: 120,
    message: t('aiModels.invalidTimeout'),
    trigger: ['blur', 'input'],
  },
  enabled: { type: 'boolean', message: t('common.required') },
  apiKey: {
    validator: (_rule, value) => {
      const key = typeof value === 'string' ? value.trim() : ''
      if (key && /^\*+$/.test(key)) return t('aiModels.invalidKeyMask')
      if (originChanged.value && !key && !form.value.clearKey)
        return t('aiModels.originKeyRequired')
      const hasKey = !!key || (!!editing.value?.has_key && !form.value.clearKey)
      if (form.value.enabled && !hasKey) return t('aiModels.keyRequired')
      return true
    },
    trigger: ['blur', 'input'],
  },
}))

async function submit() {
  if (
    !alive ||
    !showEditor.value ||
    !formRef.value ||
    !auth.isAdmin ||
    busy.value ||
    !editorReady.value
  )
    return
  const session = getSessionGeneration()
  const generation = editorGeneration
  const draft = form.value
  const owns = () =>
    alive &&
    auth.isAdmin &&
    showEditor.value &&
    generation === editorGeneration &&
    draft === form.value &&
    session === getSessionGeneration()
  editorError.value = ''
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  if (!owns() || busy.value || !editorReady.value) return
  const configuration = editing.value
  const input = form.value
  const key = input.apiKey.trim()
  const fields = {
    name: input.name.trim(),
    base_url: input.baseUrl.trim(),
    model: input.model.trim(),
    timeout_seconds: input.timeoutSeconds!,
    model_version: input.modelVersion.trim(),
    enabled: input.clearKey ? false : input.enabled,
  }
  const payload: AiModelUpdate = {
    ...fields,
    ...(input.clearKey ? { api_key: null } : key ? { api_key: key } : {}),
  }
  notice.value = ''
  const saved = await editorMutation.run(async () => {
    if (configuration) return aiModelsApi.edit(configuration, payload)
    else {
      const create: AiModelCreate = {
        ...fields,
        capability: input.capability,
        ...(key ? { api_key: key } : {}),
      }
      return aiModelsApi.add(create)
    }
  })
  if (!owns()) return
  if (!saved) {
    editorError.value = editorMutation.error.value
    return
  }
  showEditor.value = false
  form.value.apiKey = ''
  notice.value = t(configuration ? 'aiModels.saved' : 'aiModels.created')
  await refresh()
}

async function mutate(action: () => Promise<unknown>, successKey: string) {
  const session = getSessionGeneration()
  const userId = auth.user?.id
  if (actionsDisabled.value) return
  error.value = ''
  notice.value = ''
  const completed = await actionMutation.run(async () => {
    await action()
    return true
  })
  if (!alive || session !== getSessionGeneration() || userId !== auth.user?.id || !auth.isAdmin)
    return
  if (!completed) {
    error.value = actionMutation.error.value
    return
  }
  notice.value = t(successKey)
  await refresh()
}

function changeEnabled(configuration: AiModelConfig) {
  if (!configuration.enabled && !configuration.has_key) return
  return mutate(
    () => aiModelsApi.edit(configuration, { enabled: !configuration.enabled }),
    configuration.enabled ? 'aiModels.disabledNotice' : 'aiModels.enabledNotice',
  )
}

function setDefault(configuration: AiModelConfig) {
  const selection = selections.value.find((item) => item.capability === configuration.capability)
  if (!selection || !configuration.enabled || !configuration.has_key) return
  return mutate(() => aiModelsApi.setDefault(selection, configuration.id), 'aiModels.defaultSaved')
}

function clearDefault(capability: AiModelCapability) {
  const selection = selections.value.find((item) => item.capability === capability)
  if (!selection || selection.config_id === null) return
  return mutate(() => aiModelsApi.setDefault(selection, null), 'aiModels.defaultCleared')
}

function remove(configuration: AiModelConfig) {
  return mutate(() => aiModelsApi.delete(configuration), 'aiModels.deleted')
}

watch([page, query, capabilityFilter, enabledFilter, sort, listIdentity], load, { immediate: true })
watch(
  showEditor,
  (visible) => {
    if (!visible) {
      editorController?.abort()
      editorGeneration++
      editorReady.value = false
      form.value.apiKey = ''
      formRef.value?.restoreValidation()
    }
  },
  { flush: 'sync' },
)
watch(
  () => form.value.clearKey,
  (clear) => {
    if (clear) {
      form.value.apiKey = ''
      form.value.enabled = false
    }
  },
)
watch(
  () => [auth.user?.id, auth.isAdmin],
  () => {
    editorController?.abort()
    showEditor.value = false
    editorGeneration++
    if (auth.isAdmin) void loadDefaults()
    else {
      listController?.abort()
      defaultsController?.abort()
      editorController?.abort()
      showEditor.value = false
      selections.value = []
      defaultModels.value = {}
      form.value.apiKey = ''
    }
  },
)
onMounted(loadDefaults)
onBeforeUnmount(() => {
  alive = false
  stopListSession()
  editorGeneration++
  listController?.abort()
  defaultsController?.abort()
  editorController?.abort()
  form.value.apiKey = ''
})

const columns = computed<DataTableColumns<AiModelConfig>>(() => [
  { title: t('aiModels.name'), key: 'name', width: 180, ellipsis: { tooltip: true } },
  {
    title: t('aiModels.capability'),
    key: 'capability',
    width: 120,
    render: (configuration) => capabilityLabel(configuration.capability),
  },
  { title: t('aiModels.model'), key: 'model', width: 180, ellipsis: { tooltip: true } },
  { title: t('aiModels.baseUrl'), key: 'base_url', width: 230, ellipsis: { tooltip: true } },
  {
    title: t('aiModels.key'),
    key: 'has_key',
    width: 120,
    render: (configuration) =>
      h(UiTag, { size: 'small' }, () =>
        t(configuration.has_key ? 'aiModels.keySet' : 'aiModels.keyMissing'),
      ),
  },
  {
    title: t('common.status'),
    key: 'enabled',
    width: 100,
    render: (configuration) =>
      h(UiTag, { size: 'small', type: configuration.enabled ? 'success' : 'default' }, () =>
        t(configuration.enabled ? 'aiModels.enabled' : 'aiModels.disabled'),
      ),
  },
  {
    title: t('aiModels.default'),
    key: 'is_default',
    width: 120,
    render: (configuration) =>
      t(configuration.is_default ? 'aiModels.isDefault' : 'common.noneValue'),
  },
  {
    title: t('common.actions'),
    key: 'actions',
    width: 320,
    fixed: 'right',
    render: (configuration) => {
      const disabled = actionsDisabled.value
      const toggle = () =>
        h(
          UiButton,
          {
            size: 'small',
            disabled: disabled || (!configuration.enabled && !configuration.has_key),
            title: !configuration.has_key ? t('aiModels.keyRequired') : undefined,
            onClick:
              configuration.enabled && configuration.is_default
                ? undefined
                : () => changeEnabled(configuration),
          },
          () => t(configuration.enabled ? 'aiModels.disable' : 'aiModels.enable'),
        )
      return h(UiSpace, { size: 'small', wrap: false }, () => [
        h(UiButton, { size: 'small', disabled, onClick: () => openEdit(configuration) }, () =>
          t('common.edit'),
        ),
        configuration.enabled && configuration.is_default
          ? h(
              UiPopconfirm,
              {
                disabled,
                positiveText: t('common.confirm'),
                negativeText: t('common.cancel'),
                onPositiveClick: () => changeEnabled(configuration),
              },
              { trigger: toggle, default: () => t('aiModels.disableDefaultConfirm') },
            )
          : toggle(),
        h(
          UiButton,
          {
            size: 'small',
            disabled:
              disabled ||
              configuration.is_default ||
              !configuration.enabled ||
              !configuration.has_key ||
              !selections.value.some((item) => item.capability === configuration.capability),
            title: t('aiModels.defaultEligibility'),
            onClick: () => setDefault(configuration),
          },
          () => t('aiModels.setDefault'),
        ),
        h(
          UiPopconfirm,
          {
            disabled,
            positiveText: t('common.confirm'),
            negativeText: t('common.cancel'),
            onPositiveClick: () => remove(configuration),
          },
          {
            trigger: () =>
              h(UiButton, { size: 'small', type: 'error', disabled }, () => t('common.delete')),
            default: () => t('aiModels.deleteConfirm', { name: configuration.name }),
          },
        ),
      ])
    },
  },
])
</script>

<template>
  <section class="ai-models-page system-page">
    <PageHeader :title="t('page.systemAiModels')" :description="t('aiModels.description')">
      <template #actions>
        <UiButton type="primary" :disabled="actionsDisabled" @click="openCreate">
          {{ t('aiModels.create') }}
        </UiButton>
      </template>
    </PageHeader>
    <UiAlert v-if="!auth.isAdmin" type="warning">{{ t('aiModels.adminOnly') }}</UiAlert>
    <template v-else>
      <UiAlert type="info" class="feedback">{{ t('aiModels.writeHint') }}</UiAlert>
      <UiAlert v-if="notice" type="success" class="feedback">{{ notice }}</UiAlert>
      <UiAlert v-if="defaultsError" type="error" class="feedback">
        {{ defaultsError }}
        <UiButton size="small" :disabled="busy" @click="loadDefaults">{{ t('ui.retry') }}</UiButton>
      </UiAlert>
      <div v-else class="default-grid" :aria-busy="defaultsLoading">
        <article
          v-for="capability in capabilities"
          :key="capability"
          class="default-panel"
          :data-testid="`ai-default-${capability}`"
        >
          <header class="default-heading">
            <span>{{ capability }}</span>
            <h2>{{ t('aiModels.defaultTitle', { capability: capabilityLabel(capability) }) }}</h2>
          </header>
          <div class="default-body">
            <p v-if="defaultsLoading" role="status">{{ t('common.loading') }}</p>
            <template v-else>
              <p class="default-name">
                {{ defaultModels[capability]?.name ?? t('aiModels.notConfigured') }}
              </p>
              <p v-if="defaultModels[capability]" class="default-model">
                {{ defaultModels[capability]?.model }}
              </p>
              <p v-else class="default-model">{{ t('aiModels.noDefaultHint') }}</p>
              <UiPopconfirm
                v-if="defaultModels[capability]"
                :disabled="actionsDisabled"
                :positive-text="t('common.confirm')"
                :negative-text="t('common.cancel')"
                @positive-click="clearDefault(capability)"
              >
                <template #trigger>
                  <UiButton size="small" :disabled="actionsDisabled">
                    {{ t('aiModels.clearDefault') }}
                  </UiButton>
                </template>
                {{ t('aiModels.clearDefaultConfirm', { capability: capabilityLabel(capability) }) }}
              </UiPopconfirm>
            </template>
          </div>
        </article>
      </div>
      <UiCard size="small" class="ledger-panel"
        ><header class="ledger-heading">
          <h2>{{ t('operationsUi.configuration') }}</h2>
          <span v-if="!error && !loading">{{ t('assetAudit.total', { count: total }) }}</span>
        </header>

        <SearchTable
          v-model:page="page"
          v-model:query="search"
          mode="remote"
          :total="total"
          :page-size="pageSize"
          :pagination="true"
          :search-placeholder="t('aiModels.search')"
          :error="error"
          :disabled="busy"
          size="small"
          :columns="columns"
          :rows="items"
          :loading="loading"
          :row-key="(configuration: AiModelConfig) => configuration.id"
          :scroll-x="1470"
          @submit="doSearch"
          @clear="clearSearch"
          @reset="resetSearch"
          @retry="load"
        >
          <template #filter
            ><div class="flex flex-wrap items-end gap-3">
              <FormField :label="t('aiModels.capability')" :show-feedback="false">
                <UiSelect
                  v-model:value="capabilityFilter"
                  :options="capabilityOptions"
                  :aria-label="t('aiModels.capability')"
                  :disabled="busy"
                  clearable
                  @update:value="page = 1"
                />
              </FormField>
              <FormField :label="t('common.status')" :show-feedback="false">
                <UiSelect
                  v-model:value="enabledSelection"
                  :options="enabledOptions"
                  :aria-label="t('common.status')"
                  :disabled="busy"
                  clearable
                  @update:value="page = 1"
                />
              </FormField>
              <FormField :label="t('aiModels.sort')" :show-feedback="false">
                <UiSelect
                  v-model:value="sort"
                  :options="sortOptions"
                  :aria-label="t('aiModels.sort')"
                  :disabled="busy"
                  @update:value="page = 1"
                />
              </FormField>
              <UiSpace class="filter-actions">
                <UiButton :loading="loading || defaultsLoading" :disabled="busy" @click="refresh">
                  {{ t('graph.refresh') }}
                </UiButton>
              </UiSpace>
            </div></template
          >
          <template #empty><UiEmpty :description="t('aiModels.empty')" /></template>
        </SearchTable>
      </UiCard>
    </template>
    <UiDrawer
      :show="editorVisible"
      width="min(560px, 100vw)"
      :close-on-esc="!busy"
      :mask-closable="!busy"
      @update:show="!busy && (editorVisible = $event)"
    >
      <UiDrawerContent :title="t(editing ? 'aiModels.edit' : 'aiModels.create')" :closable="!busy">
        <UiSpin :show="editorLoading">
          <UiAlert v-if="editorError" type="error" class="feedback">
            {{ editorError }}
            <UiButton v-if="editing" size="small" :disabled="busy" @click="reloadEditor">
              {{ t('aiModels.reload') }}
            </UiButton>
          </UiAlert>
          <FormContainer
            v-if="editorReady"
            id="system-ai-model-form"
            ref="formRef"
            :model="form"
            :rules="rules"
            :disabled="busy || !auth.isAdmin"
            :submitting="saving"
            label-placement="top"
            @submit="submit"
          >
            <fieldset class="settings-group">
              <legend>{{ t('operationsUi.modelIdentity') }}</legend>
              <FormField :label="t('aiModels.name')" path="name" required>
                <UiInput
                  v-model:value="form.name"
                  :maxlength="200"
                  :input-props="{ 'aria-label': t('aiModels.name') }"
                />
              </FormField>
              <FormField :label="t('aiModels.capability')" path="capability" required>
                <UiSelect
                  v-model:value="form.capability"
                  :options="capabilityOptions"
                  :aria-label="t('aiModels.capability')"
                  :disabled="!!editing || busy"
                />
              </FormField>
              <p v-if="editing" class="field-hint">{{ t('aiModels.capabilityImmutable') }}</p>
            </fieldset>
            <fieldset class="settings-group">
              <legend>{{ t('operationsUi.connection') }}</legend>
              <FormField :label="t('aiModels.baseUrl')" path="baseUrl" required>
                <UiInput
                  v-model:value="form.baseUrl"
                  :maxlength="2048"
                  :placeholder="t('aiModels.baseUrlPlaceholder')"
                  :input-props="{ 'aria-label': t('aiModels.baseUrl') }"
                />
              </FormField>
              <UiAlert v-if="originChanged" type="warning" class="feedback">
                {{ t('aiModels.originKeyRequired') }}
              </UiAlert>
              <FormField :label="t('aiModels.model')" path="model" required>
                <UiInput
                  v-model:value="form.model"
                  :maxlength="255"
                  :placeholder="t('aiModels.modelPlaceholder')"
                  :input-props="{ 'aria-label': t('aiModels.model') }"
                />
              </FormField>
              <FormField :label="t('aiModels.modelVersion')" path="modelVersion" required>
                <UiInput
                  v-model:value="form.modelVersion"
                  :maxlength="100"
                  :input-props="{ 'aria-label': t('aiModels.modelVersion') }"
                />
              </FormField>
              <FormField :label="t('aiModels.timeout')" path="timeoutSeconds" required>
                <UiInputNumber
                  v-model:value="form.timeoutSeconds"
                  :min="1"
                  :max="120"
                  :precision="0"
                  :input-props="{ 'aria-label': t('aiModels.timeout') }"
                  class="number-input"
                />
              </FormField>
            </fieldset>
            <fieldset class="settings-group">
              <legend>{{ t('operationsUi.credentials') }}</legend>
              <FormField :label="t('aiModels.key')" path="apiKey">
                <UiInput
                  v-model:value="form.apiKey"
                  type="password"
                  show-password-on="click"
                  :disabled="busy || form.clearKey"
                  :placeholder="t(editing?.has_key ? 'aiModels.keepKey' : 'aiModels.enterKey')"
                  :input-props="{ 'aria-label': t('aiModels.key'), autocomplete: 'new-password' }"
                />
              </FormField>
              <p class="field-hint">
                {{ t(editing?.has_key ? 'aiModels.keySet' : 'aiModels.keyMissing') }}
                {{ t('aiModels.keyWriteOnly') }}
              </p>
              <UiCheckbox v-if="editing?.has_key" v-model:checked="form.clearKey" :disabled="busy">
                {{ t('aiModels.clearKey') }}
              </UiCheckbox>
              <UiAlert v-if="form.clearKey" type="warning" class="feedback">
                {{ t('aiModels.clearKeyHint') }}
              </UiAlert>
              <FormField :label="t('aiModels.enabledField')" path="enabled" class="enabled-field">
                <UiSwitch
                  v-model:value="form.enabled"
                  :disabled="busy || form.clearKey"
                  :aria-disabled="busy || form.clearKey"
                  :aria-label="t('aiModels.enabledField')"
                />
              </FormField>
            </fieldset>
          </FormContainer>
        </UiSpin>
        <template #footer>
          <UiSpace>
            <UiButton :disabled="busy" @click="editorVisible = false">{{
              t('common.cancel')
            }}</UiButton>
            <UiButton
              type="primary"
              :loading="saving"
              :disabled="!auth.isAdmin || !editorReady || busy"
              attr-type="submit"
              form="system-ai-model-form"
            >
              {{ t(editing ? 'common.save' : 'common.create') }}
            </UiButton>
          </UiSpace>
        </template>
      </UiDrawerContent>
    </UiDrawer>
  </section>
</template>

<style scoped src="../SystemWorkspace.css"></style>

<style scoped>
.ai-models-page {
  min-width: 0;
}
.feedback {
  margin-bottom: var(--space-4);
}
.default-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}
.default-panel {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-panel, var(--bg-surface));
  overflow: hidden;
}
.default-heading {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}
.default-heading span {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--violet);
}
.default-heading h2 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}
.default-body {
  padding: 20px;
  background: var(--bg-inset);
}
.default-name {
  margin: 0;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.default-model,
.field-hint {
  margin: var(--space-2) 0 var(--space-4);
  color: var(--text-secondary);
  font-size: var(--font-small);
  overflow-wrap: anywhere;
}
.filters {
  display: grid;
  grid-template-columns: minmax(180px, 2fr) repeat(3, minmax(120px, 1fr)) auto;
  gap: var(--space-3);
  align-items: end;
  margin-bottom: var(--space-4);
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border);
}
.filter-actions {
  padding-bottom: var(--space-1);
}
.number-input {
  width: 100%;
}
.enabled-field {
  margin-top: var(--space-4);
}
.pagination {
  justify-content: flex-end;
  margin-top: var(--space-4);
}
@media (max-width: 1100px) {
  .filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 640px) {
  .default-grid,
  .filters {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
