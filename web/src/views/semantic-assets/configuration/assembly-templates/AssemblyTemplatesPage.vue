<script setup lang="ts">
import { computed, h, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import type { Template, TemplateInput, TemplateOntology, TemplateResource } from '@/api/templates'
import { templatesApi as api } from '@/api/templates'
import SearchPanel from '@/components/business/SearchPanel.vue'
import SearchTable from '@/components/business/SearchTable.vue'
import PageHeader from '@/components/PageHeader.vue'
import type { DataTableColumns, FormInst } from '@/components/ui'
import {
  FormContainer,
  FormField,
  UiAlert,
  UiButton,
  UiDrawer,
  UiDrawerContent,
  UiEmpty,
  UiInput,
  UiInputNumber,
  UiModal,
  UiPopconfirm,
  UiSelect,
  UiSpace,
  UiTable,
  UiTag,
} from '@/components/ui'
import { useAssetAccess } from '@/composables/useAssetAccess'
import { useDraftGuard } from '@/composables/useDraftGuard'
import TemplateCoreCheck from '@/views/semantic-assets/configuration/assembly-templates/components/TemplateCoreCheck.vue'

import AssetIdentity from '../../components/AssetIdentity.vue'
import type { EditorModel } from './templateValidation'
import {
  editorErrors,
  editorRules,
  instanceErrors,
  instancePayload,
  instanceRules,
  metadataPayload,
  resourceSelectionError,
} from './templateValidation'

const { t, locale } = useI18n()
const { canWrite } = useAssetAccess()
const route = useRoute()
const router = useRouter()
const items = ref<Template[]>([])
const total = ref(0)
const page = ref(Math.max(1, Number(route.query.page) || 1))
const query = ref(typeof route.query.q === 'string' ? route.query.q : '')
const search = ref(query.value)
const filter = ref<string | null>(
  ['builtin', 'custom'].includes(String(route.query.kind)) ? String(route.query.kind) : null,
)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const listError = ref('')
const initialized = ref(false)
const notice = ref('')
const checkingTemplate = ref<Template | null>(null)
const editor = ref(false)
const mode = ref<'create' | 'edit' | 'copy' | 'fromOntology'>('create')
const saved = ref<Template | null>(null)
const form = ref<TemplateInput>(empty())
const catalog = ref<TemplateResource[]>([])
const ontologies = ref<TemplateOntology[]>([])
const resourceId = ref<number | null>(null)
const resourceRevision = ref<number | null>(null)
const ontologyId = ref<number | null>(null)
const ontologyRevision = ref<number | null>(null)
const instanceTemplate = ref<Template | null>(null)
const instantiateVisible = ref(false)
const instanceStep = ref<'preview' | 'configure'>('preview')
const catalogLoading = ref(false)
const catalogError = ref('')
const instance = ref({ name: '', iri: '', labelZh: '', labelEn: '' })
const editorFormRef = ref<FormInst | null>(null)
const instanceFormRef = ref<FormInst | null>(null)
const editorValidation = ref(false)
const instanceValidation = ref(false)
const addingResource = ref(false)
const editorSession = ref(0)
const instanceSession = ref(0)
const editorModel: EditorModel = {
  get metadata() {
    return form.value
  },
  get ontologyId() {
    return ontologyId.value
  },
  get ontologyRevision() {
    return ontologyRevision.value
  },
  get resourceId() {
    return resourceId.value
  },
  get resourceRevision() {
    return resourceRevision.value
  },
}
const translate = (key: string, params?: { max: number }) => (params ? t(key, params) : t(key))
const editorFormRules = computed(() =>
  editorRules(editorModel, mode.value, addingResource.value, translate, catalog.value),
)
const instanceFormRules = computed(() => instanceRules(instance.value, translate))
const controller = new AbortController()
let listController: AbortController | undefined
let sessionGeneration = 0
let operationGeneration = 0
let editorValidationGeneration = 0
let instanceValidationGeneration = 0
let editorInputGeneration = 0
let instanceInputGeneration = 0

function empty(): TemplateInput {
  return {
    name: '',
    label_i18n: { 'zh-CN': '', 'en-US': '' },
    source: '',
    basis: '',
    resources: [],
  }
}
function input(item: Template): TemplateInput {
  return {
    name: item.name,
    label_i18n: { ...item.label_i18n },
    source: item.source,
    basis: item.basis,
    resources: item.resources.map((r) => ({ ...r })),
  }
}
function label(item: { name: string; label_i18n?: Record<string, string> | null }) {
  return (
    item.label_i18n?.[locale.value]?.trim() ||
    `${item.label_i18n?.['zh-CN'] || item.name} (${t('rules.untranslated')})`
  )
}
const readonly = computed(() => mode.value === 'edit' && saved.value?.builtin)
const editorVisible = useDraftGuard(
  editor,
  () => editorModel,
  () => canWrite.value && !readonly.value,
  () => editorSession.value,
)
const instanceVisible = useDraftGuard(
  instantiateVisible,
  () => instance.value,
  () => canWrite.value && instanceStep.value === 'configure',
  () => instanceSession.value,
)
const resourcesEditable = computed(
  () => canWrite.value && !readonly.value && mode.value !== 'copy' && mode.value !== 'fromOntology',
)
const missingInstanceResources = computed(
  () =>
    instanceTemplate.value?.resources.some(
      (entry) =>
        !catalog.value.some(
          (resource) =>
            resource.resource_id === entry.resource_id &&
            resource.revisions.includes(entry.pinned_revision),
        ),
    ) ?? false,
)
const canSave = computed(
  () =>
    canWrite.value &&
    !readonly.value &&
    form.value.name.trim() &&
    form.value.label_i18n['zh-CN']?.trim() &&
    form.value.source.trim() &&
    form.value.basis.trim() &&
    (mode.value !== 'fromOntology' || (ontologyId.value && ontologyRevision.value)),
)
const resourceOptions = computed(() =>
  catalog.value.map((r) => ({
    label: `${label(r)} · ${r.name}`,
    value: r.resource_id,
    disabled: form.value.resources?.some((ref) => ref.resource_id === r.resource_id),
  })),
)
const versionOptions = computed(() =>
  (catalog.value.find((r) => r.resource_id === resourceId.value)?.revisions || []).map((value) => ({
    value,
    label: String(value),
  })),
)
const ontologyOptions = computed(() =>
  ontologies.value
    .filter((item) => item.current_revision > 0)
    .map((item) => ({ value: item.id, label: `${label(item)} · ${item.name}` })),
)
const filterOptions = computed(() =>
  ['builtin', 'custom'].map((value) => ({ value, label: t(`templates.${value}`) })),
)
const columns = computed<DataTableColumns<Template>>(() => [
  { title: t('common.name'), key: 'name' },
  { title: t('common.label'), key: 'label_i18n', render: label },
  { title: t('templates.source'), key: 'source' },
  {
    title: t('templates.kind'),
    key: 'builtin',
    render: (row: Template) =>
      h(UiTag, {}, { default: () => t(row.builtin ? 'templates.builtin' : 'templates.custom') }),
  },
  { title: t('common.revision'), key: 'revision' },
  { title: t('templates.references'), key: 'reference_count' },
  {
    title: t('common.actions'),
    key: 'actions',
    fixed: 'right',
    width: 380,
    render: (row: Template) =>
      h(
        UiSpace,
        {},
        {
          default: () => [
            h(
              UiButton,
              {
                size: 'small',
                disabled: busy.value || !canWrite.value,
                title: !canWrite.value ? t('governanceUi.checkReadOnly') : undefined,
                onClick: () => {
                  checkingTemplate.value = row
                },
              },
              { default: () => t('coreCheck.title') },
            ),
            h(
              UiButton,
              { size: 'small', disabled: busy.value, onClick: () => open('edit', row) },
              { default: () => t('templates.details') },
            ),
            h(
              UiButton,
              {
                size: 'small',
                disabled: busy.value || !canWrite.value,
                onClick: () => open('copy', row),
              },
              { default: () => t('templates.copy') },
            ),
            h(
              UiButton,
              { size: 'small', disabled: busy.value, onClick: () => prepareInstance(row) },
              { default: () => t('governanceUi.previewTemplate') },
            ),
          ],
        },
      ),
  },
])

function message(err: unknown) {
  const body = err as { code?: string; params?: { reason?: string } }
  if (body.code === 'KG.REVISION_CONFLICT') return t('templates.conflict')
  if (body.params?.reason === 'template_in_use') return t('templates.inUse')
  return t('templates.failed', { reason: body.params?.reason || body.code || 'NETWORK_ERROR' })
}
async function run(action: (isCurrent: () => boolean) => Promise<void>) {
  if (busy.value) return
  const operation = ++operationGeneration
  const session = sessionGeneration
  const isCurrent = () =>
    !controller.signal.aborted && operation === operationGeneration && session === sessionGeneration
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await action(isCurrent)
  } catch (err) {
    if (isCurrent()) error.value = message(err)
  } finally {
    if (isCurrent()) busy.value = false
  }
}
async function load() {
  listController?.abort()
  const request = new AbortController()
  listController = request
  loading.value = true
  listError.value = ''
  items.value = []
  try {
    const result = await api.list(
      {
        q: search.value,
        page: page.value,
        builtin: filter.value === null ? undefined : filter.value === 'builtin',
      },
      request.signal,
    )
    if (request.signal.aborted) return
    items.value = result.items
    total.value = result.total
    const lastPage = Math.max(1, Math.ceil(result.total / 20))
    if (page.value > lastPage) page.value = lastPage
  } catch (err) {
    if (!request.signal.aborted) listError.value = message(err)
  } finally {
    if (!request.signal.aborted) {
      loading.value = false
      initialized.value = true
    }
  }
}
async function open(next: typeof mode.value, item?: Template) {
  if (next !== 'edit' && !canWrite.value) return
  invalidateSession()
  await run(async (isCurrent) => {
    const latest = item ? await api.get(item.id) : null
    if (!isCurrent()) return
    saved.value = latest
    form.value = latest ? input(latest) : empty()
    mode.value = next
    resourceId.value = null
    resourceRevision.value = null
    ontologyId.value = null
    ontologyRevision.value = null
    editorSession.value++
    editor.value = true
  })
}
async function addResource() {
  if (!resourcesEditable.value || busy.value || editorValidation.value || !editor.value) return
  const session = sessionGeneration
  const operation = operationGeneration
  const inputGeneration = editorInputGeneration
  const validation = ++editorValidationGeneration
  const resource = resourceId.value
  const revision = resourceRevision.value
  editorValidation.value = true
  addingResource.value = true
  try {
    if (editorFormRef.value) {
      await nextTick()
      try {
        await editorFormRef.value.validate(undefined, [
          'resourceId',
          'resourceRevision',
          'metadata.resources',
        ])
      } catch {
        return
      }
    }
    if (
      session !== sessionGeneration ||
      operation !== operationGeneration ||
      inputGeneration !== editorInputGeneration ||
      controller.signal.aborted ||
      !resourcesEditable.value ||
      busy.value ||
      !editor.value
    )
      return
    const invalid = resourceSelectionError(editorModel, catalog.value)
    if (invalid) {
      if (!editorFormRef.value) error.value = translate(invalid, { max: 1000 })
      return
    }
    form.value.resources = [
      ...(form.value.resources || []),
      { resource_id: resource!, pinned_revision: revision! },
    ]
    resourceId.value = null
    resourceRevision.value = null
  } finally {
    if (validation === editorValidationGeneration) {
      editorValidation.value = false
      addingResource.value = false
    }
  }
}
async function save() {
  if (!canWrite.value || readonly.value || !editor.value || busy.value || editorValidation.value)
    return
  const session = sessionGeneration
  const operation = operationGeneration
  const inputGeneration = editorInputGeneration
  const validation = ++editorValidationGeneration
  const action = mode.value
  const target = saved.value
    ? { ...saved.value, resources: saved.value.resources.map((r) => ({ ...r })) }
    : null
  if ((action === 'edit' || action === 'copy') && !target) return
  const snapshot: EditorModel = {
    metadata: {
      ...form.value,
      label_i18n: { ...form.value.label_i18n },
      resources: form.value.resources?.map((r) => ({ ...r })),
    },
    ontologyId: ontologyId.value,
    ontologyRevision: ontologyRevision.value,
    resourceId: resourceId.value,
    resourceRevision: resourceRevision.value,
  }
  const invalid = editorErrors(snapshot, action)
  editorValidation.value = true
  try {
    if (editorFormRef.value) {
      try {
        await editorFormRef.value.validate()
      } catch {
        return
      }
    }
    if (
      controller.signal.aborted ||
      session !== sessionGeneration ||
      operation !== operationGeneration ||
      inputGeneration !== editorInputGeneration ||
      !editor.value ||
      busy.value ||
      !canWrite.value ||
      readonly.value
    )
      return
    if (Object.keys(invalid).length) {
      if (!editorFormRef.value) {
        const first = Object.values(invalid)[0]
        error.value = translate(first.key, first.params)
      }
      return
    }
    if (!canSave.value) return
    if (
      (action === 'create' || action === 'edit') &&
      (snapshot.resourceId !== null || snapshot.resourceRevision !== null) &&
      resourceSelectionError(snapshot, catalog.value)
    )
      return
    const metadata = metadataPayload(snapshot.metadata)
    await run(async (isCurrent) => {
      const result =
        action === 'fromOntology'
          ? await api.fromOntology({
              ...metadata,
              ontology_id: snapshot.ontologyId!,
              ontology_revision: snapshot.ontologyRevision!,
            })
          : action === 'copy'
            ? await api.copy(target!, metadata)
            : action === 'edit'
              ? await api.update(target!, { ...metadata, resources: snapshot.metadata.resources })
              : await api.create({ ...metadata, resources: snapshot.metadata.resources })
      if (!isCurrent()) return
      saved.value = result
      form.value = input(result)
      mode.value = 'edit'
      resourceId.value = null
      resourceRevision.value = null
      editorSession.value++
      notice.value = t('templates.saved')
      await load()
    })
  } finally {
    if (validation === editorValidationGeneration) editorValidation.value = false
  }
}
async function remove() {
  if (
    !canWrite.value ||
    !saved.value ||
    saved.value.builtin ||
    saved.value.reference_count > 0 ||
    editorValidation.value
  )
    return
  const item = saved.value
  await run(async (isCurrent) => {
    await api.remove(item)
    if (!isCurrent()) return
    editor.value = false
    notice.value = t('templates.deleted')
    await load()
  })
}
async function prepareInstance(item: Template) {
  invalidateSession()
  await run(async (isCurrent) => {
    const latest = await api.get(item.id)
    if (!isCurrent()) return
    instanceTemplate.value = latest
    instanceStep.value = 'preview'
    instance.value = { name: '', iri: '', labelZh: '', labelEn: '' }
    instanceSession.value++
    instantiateVisible.value = true
  })
}
function configureInstance() {
  if (
    !canWrite.value ||
    busy.value ||
    catalogLoading.value ||
    catalogError.value ||
    missingInstanceResources.value ||
    !instanceTemplate.value
  )
    return
  instanceSession.value++
  instanceStep.value = 'configure'
}
async function instantiate() {
  if (
    !canWrite.value ||
    !instantiateVisible.value ||
    busy.value ||
    instanceValidation.value ||
    instanceStep.value !== 'configure' ||
    !instanceTemplate.value ||
    catalogLoading.value ||
    catalogError.value ||
    missingInstanceResources.value
  )
    return
  const session = sessionGeneration
  const operation = operationGeneration
  const inputGeneration = instanceInputGeneration
  const validation = ++instanceValidationGeneration
  const item = {
    ...instanceTemplate.value,
    resources: instanceTemplate.value.resources.map((r) => ({ ...r })),
  }
  const snapshot = { ...instance.value }
  const invalid = instanceErrors(snapshot)
  instanceValidation.value = true
  try {
    if (instanceFormRef.value) {
      try {
        await instanceFormRef.value.validate()
      } catch {
        return
      }
    }
    if (
      controller.signal.aborted ||
      session !== sessionGeneration ||
      operation !== operationGeneration ||
      inputGeneration !== instanceInputGeneration ||
      !instantiateVisible.value ||
      instanceStep.value !== 'configure' ||
      busy.value ||
      !canWrite.value ||
      catalogLoading.value ||
      catalogError.value ||
      missingInstanceResources.value
    )
      return
    if (Object.keys(invalid).length) {
      if (!instanceFormRef.value) {
        const first = Object.values(invalid)[0]
        error.value = translate(first.key, first.params)
      }
      return
    }
    const payload = instancePayload(snapshot)
    await run(async (isCurrent) => {
      const created = await api.instantiate(item, payload)
      if (!isCurrent()) return
      instantiateVisible.value = false
      const completedSession = sessionGeneration
      notice.value = t('templates.createdOntology', {
        name: created.name,
        template: created.template?.name || item.name,
      })
      await load()
      const options = await api.ontologies(controller.signal)
      if (!controller.signal.aborted && completedSession === sessionGeneration)
        ontologies.value = options
    })
  } finally {
    if (validation === instanceValidationGeneration) instanceValidation.value = false
  }
}
watch(resourceId, () => {
  resourceRevision.value = versionOptions.value.at(-1)?.value ?? null
})
watch(ontologyId, () => {
  ontologyRevision.value =
    ontologies.value.find((r) => r.id === ontologyId.value)?.current_revision ?? null
})
function doSearch() {
  const next = query.value.trim()
  if (search.value === next && page.value === 1) void load()
  else {
    page.value = 1
    search.value = next
  }
}
function clearSearch() {
  query.value = ''
  doSearch()
}
function changeFilter(value: string | null) {
  page.value = 1
  filter.value = value
}
function resetSearch() {
  query.value = ''
  if (search.value === '' && page.value === 1 && filter.value === null) void load()
  else {
    search.value = ''
    filter.value = null
    page.value = 1
  }
}
function invalidateSession() {
  sessionGeneration++
  operationGeneration++
  busy.value = false
  editorValidationGeneration++
  instanceValidationGeneration++
  editorValidation.value = false
  instanceValidation.value = false
  addingResource.value = false
}
watch(
  () => [editorModel, mode.value, saved.value],
  () => {
    editorInputGeneration++
  },
  { deep: true, flush: 'sync' },
)
watch(
  () => [instance.value, instanceTemplate.value, instanceStep.value],
  () => {
    instanceInputGeneration++
  },
  { deep: true, flush: 'sync' },
)
watch(
  [editor, instantiateVisible],
  ([edit, instance], [wasEdit, wasInstance]) => {
    if ((!edit && wasEdit) || (!instance && wasInstance)) invalidateSession()
  },
  { flush: 'sync' },
)
watch([page, search, filter], load, { immediate: true })
watch([page, search, filter], () => {
  void router.replace({
    query: {
      ...route.query,
      q: search.value || undefined,
      kind: filter.value || undefined,
      page: page.value > 1 ? page.value : undefined,
    },
  })
})
async function loadCatalog() {
  if (catalogLoading.value) return
  catalogLoading.value = true
  catalogError.value = ''
  try {
    const [resources, options] = await Promise.all([
      api.resources(controller.signal),
      api.ontologies(controller.signal),
    ])
    if (controller.signal.aborted) return
    catalog.value = resources
    ontologies.value = options
  } catch (err) {
    if (!controller.signal.aborted) catalogError.value = message(err)
  } finally {
    if (!controller.signal.aborted) catalogLoading.value = false
  }
}
onMounted(loadCatalog)
onBeforeUnmount(() => {
  controller.abort()
  listController?.abort()
})
</script>

<template>
  <UiDrawer
    :show="!!checkingTemplate"
    width="min(600px, 100vw)"
    @update:show="
      (value) => {
        if (!value) checkingTemplate = null
      }
    "
  >
    <UiDrawerContent class="asset-editor" :title="t('coreCheck.title')" closable>
      <TemplateCoreCheck
        v-if="checkingTemplate"
        :key="checkingTemplate.id"
        :template-id="checkingTemplate.id"
      />
    </UiDrawerContent>
  </UiDrawer>
  <section class="templates-page asset-page">
    <PageHeader :title="t('templates.title')" :description="t('templates.intro')">
      <template #actions>
        <UiButton :disabled="busy || !canWrite" @click="open('fromOntology')">{{
          t('templates.fromOntology')
        }}</UiButton>
        <UiButton type="primary" :disabled="busy || !canWrite" @click="open('create')">{{
          t('templates.create')
        }}</UiButton>
      </template>
    </PageHeader>
    <UiAlert v-if="!canWrite" type="info">{{ t('governanceUi.readOnly') }}</UiAlert>
    <UiAlert v-if="error && !editor && !instantiateVisible" type="error" role="alert"
      >{{ error }}
      <UiButton size="small" @click="load">{{ t('governanceUi.retry') }}</UiButton>
    </UiAlert>
    <UiAlert v-if="catalogError" type="error" role="alert"
      >{{ catalogError }}
      <UiButton size="small" @click="loadCatalog">{{ t('governanceUi.retry') }}</UiButton>
    </UiAlert>
    <UiAlert v-if="notice" type="success" role="status">{{ notice }}</UiAlert>
    <section class="ledger-surface">
      <header class="ledger-caption">
        <h2>{{ t('templates.title') }}</h2>
        <span>{{
          t('assetLedger.resultCount', {
            count:
              loading || listError
                ? t('common.noneValue')
                : new Intl.NumberFormat(locale).format(total),
          })
        }}</span>
      </header>
      <div>
        <SearchPanel
          v-model:query="query"
          :loading="loading"
          @submit="doSearch"
          @clear="clearSearch"
          @reset="resetSearch"
        >
          <template #filters>
            <FormField :label="t('templates.kind')" :show-feedback="false">
              <UiSelect
                :value="filter"
                :options="filterOptions"
                :placeholder="t('templates.all')"
                clearable
                style="width: 180px"
                @update:value="changeFilter"
              />
            </FormField>
          </template>
        </SearchPanel>
        <UiButton :loading="loading" @click="load">{{ t('graph.refresh') }}</UiButton>
        <SearchTable
          :searchable="false"
          :rows="items"
          mode="remote"
          :total="total"
          :page="page"
          :page-size="20"
          :initialized="initialized"
          :error="listError"
          :row-key="(row: Template) => row.id"
          size="small"
          :max-height="600"
          :columns="columns"
          :loading="loading"
          :scroll-x="1000"
          @update:page="page = $event"
          @retry="load"
          ><template #empty
            ><UiEmpty
              :description="t(search || filter ? 'ui.emptyFiltered' : 'common.empty')" /></template
        ></SearchTable>
      </div>
    </section>
    <UiDrawer
      v-model:show="editorVisible"
      width="min(820px, 100vw)"
      :mask-closable="false"
      :close-on-esc="!busy && !editorValidation"
      ><UiDrawerContent
        class="asset-editor"
        :title="t(`templates.${mode}`)"
        :closable="!busy && !editorValidation"
      >
        <div class="editor-identity">
          <AssetIdentity
            :name="form.name || t(`templates.${mode}`)"
            :revision="saved?.revision"
            :context="t(readonly ? 'templates.builtinHint' : 'templates.pinHint')"
          />
        </div>
        <UiSpace vertical
          ><UiAlert v-if="!canWrite" type="info">{{ t('governanceUi.readOnly') }}</UiAlert
          ><UiAlert v-if="error" type="error" role="alert">{{ error }}</UiAlert
          ><UiAlert v-if="notice" type="success">{{ notice }}</UiAlert
          ><UiAlert v-if="readonly" type="info">{{ t('templates.builtinHint') }}</UiAlert
          ><UiAlert v-if="saved" type="info">{{
            t('templates.revisionHint', { revision: saved.revision, count: saved.reference_count })
          }}</UiAlert></UiSpace
        >
        <FormContainer
          :key="editorSession"
          ref="editorFormRef"
          :model="editorModel"
          :rules="editorFormRules"
          label-placement="top"
          :disabled="busy || !canWrite"
          :readonly="!!readonly || !canWrite"
          :submitting="busy"
          class="editor-form"
          :aria-busy="busy || editorValidation"
          @submit="save"
        >
          <fieldset class="form-section">
            <legend>{{ t('common.name') }}</legend>
            <div class="form-grid">
              <FormField :label="t('common.name')" path="metadata.name" required
                ><UiInput v-model:value="form.name" /></FormField
              ><FormField :label="t('templates.source')" path="metadata.source" required
                ><UiInput v-model:value="form.source" /></FormField
              ><FormField :label="t('common.labelZh')" path="metadata.label_i18n.zh-CN" required
                ><UiInput v-model:value="form.label_i18n['zh-CN']" /></FormField
              ><FormField :label="t('common.labelEn')" path="metadata.label_i18n.en-US"
                ><UiInput v-model:value="form.label_i18n['en-US']"
              /></FormField>
            </div>
          </fieldset>
          <fieldset class="form-section">
            <legend>{{ t('templates.basis') }}</legend>
            <FormField :label="t('templates.basis')" path="metadata.basis" required
              ><UiInput v-model:value="form.basis" type="textarea"
            /></FormField>
          </fieldset>
          <template v-if="mode === 'fromOntology'"
            ><FormField :label="t('export.ontology')" path="ontologyId" required
              ><UiSelect
                v-model:value="ontologyId"
                :options="ontologyOptions"
                filterable /></FormField
            ><FormField :label="t('export.revision')" path="ontologyRevision" required
              ><UiInputNumber v-model:value="ontologyRevision" /></FormField
          ></template>
          <template v-else
            ><UiSpace v-if="resourcesEditable" align="center" class="filters"
              ><FormField
                :label="t('templates.resource')"
                path="resourceId"
                label-placement="left"
                :label-width="72"
                ><UiSelect
                  v-model:value="resourceId"
                  :options="resourceOptions"
                  filterable
                  clearable
                  style="width: 280px" /></FormField
              ><FormField
                :label="t('templates.pinnedRevision')"
                path="resourceRevision"
                label-placement="left"
                :label-width="96"
                ><UiSelect
                  v-model:value="resourceRevision"
                  :options="versionOptions"
                  clearable
                  style="width: 110px" /></FormField
              ><UiButton
                :disabled="busy || !resourcesEditable || editorValidation"
                @click="addResource"
                >{{ t('templates.addResource') }}</UiButton
              ></UiSpace
            >
            <FormField
              v-slot="field"
              :label="t('templates.resources')"
              path="metadata.resources"
              :help="t('templates.pinHint')"
            >
              <div
                :id="field.id"
                tabindex="0"
                :aria-labelledby="field.ariaLabelledby"
                :aria-describedby="field.ariaDescribedby"
                :aria-invalid="field.ariaInvalid"
              >
                <UiTable size="small"
                  ><thead>
                    <tr>
                      <th>{{ t('templates.resource') }}</th>
                      <th>{{ t('templates.pinnedRevision') }}</th>
                      <th v-if="resourcesEditable">{{ t('common.actions') }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(entry, index) in form.resources" :key="entry.resource_id">
                      <td :title="catalog.find((r) => r.resource_id === entry.resource_id)?.iri">
                        {{
                          catalog.find((r) => r.resource_id === entry.resource_id)?.name ||
                          t('templates.resourceUnavailable', { id: entry.resource_id })
                        }}
                      </td>
                      <td>{{ entry.pinned_revision }}</td>
                      <td v-if="resourcesEditable">
                        <UiButton
                          size="small"
                          :disabled="busy || !resourcesEditable"
                          @click="form.resources?.splice(index, 1)"
                          >{{ t('common.delete') }}</UiButton
                        >
                      </td>
                    </tr>
                  </tbody></UiTable
                >
              </div>
            </FormField> </template
          ><UiAlert type="info" class="pin-hint">{{ t('templates.pinHint') }}</UiAlert>
        </FormContainer>
        <template #footer
          ><UiSpace justify="space-between" style="width: 100%"
            ><UiPopconfirm
              v-if="mode === 'edit' && saved"
              :disabled="busy || readonly || !canWrite || saved.reference_count > 0"
              @positive-click="remove"
              ><template #trigger
                ><UiButton
                  type="error"
                  secondary
                  :disabled="busy || readonly || !canWrite || saved.reference_count > 0"
                  >{{ t('common.delete') }}</UiButton
                ></template
              >{{ t('templates.confirmDelete', { name: saved.name }) }}</UiPopconfirm
            ><UiSpace
              ><UiButton :disabled="busy || editorValidation" @click="editorVisible = false">{{
                t('common.cancel')
              }}</UiButton
              ><UiButton
                type="primary"
                :disabled="busy || !canWrite || !!readonly || editorValidation"
                :loading="busy || editorValidation"
                @click="save"
                >{{ t('common.save') }}</UiButton
              ></UiSpace
            ></UiSpace
          ></template
        >
      </UiDrawerContent></UiDrawer
    >
    <UiModal
      v-model:show="instanceVisible"
      preset="card"
      :title="
        t(instanceStep === 'preview' ? 'governanceUi.previewTemplate' : 'templates.instantiate')
      "
      style="width: min(720px, 100vw)"
      :mask-closable="false"
      :closable="!busy && !instanceValidation"
      :close-on-esc="!busy && !instanceValidation"
      ><UiAlert v-if="error" type="error" role="alert">{{ error }}</UiAlert>
      <UiAlert v-if="!canWrite" type="info">{{ t('governanceUi.readOnly') }}</UiAlert>
      <section v-if="instanceTemplate" class="instance-preview">
        <h3>{{ label(instanceTemplate) }}</h3>
        <p>{{ t('governanceUi.templateRevision', { revision: instanceTemplate.revision }) }}</p>
        <p>{{ instanceTemplate.source }} · {{ instanceTemplate.basis }}</p>
        <UiAlert type="info">{{ t('governanceUi.instanceHint') }}</UiAlert>
        <p v-if="catalogLoading" role="status">{{ t('common.loading') }}</p>
        <UiAlert v-else-if="catalogError" type="error"
          >{{ catalogError }}
          <UiButton @click="loadCatalog">{{ t('governanceUi.retry') }}</UiButton>
        </UiAlert>
        <template v-else>
          <UiAlert v-if="missingInstanceResources" type="warning">{{
            t('governanceUi.missingMembers')
          }}</UiAlert>
          <UiTable size="small">
            <thead>
              <tr>
                <th>{{ t('templates.resource') }}</th>
                <th>{{ t('templates.pinnedRevision') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="entry in instanceTemplate.resources" :key="entry.resource_id">
                <td :title="catalog.find((r) => r.resource_id === entry.resource_id)?.iri">
                  {{
                    catalog.find((r) => r.resource_id === entry.resource_id)?.name ||
                    t('templates.resourceUnavailable', { id: entry.resource_id })
                  }}
                </td>
                <td>{{ entry.pinned_revision }}</td>
              </tr>
            </tbody>
          </UiTable>
          <UiEmpty
            v-if="!instanceTemplate.resources.length"
            :description="t('governanceUi.noMembers')"
          />
        </template>
      </section>
      <UiButton
        v-if="instanceStep === 'preview'"
        type="primary"
        :disabled="
          busy || !canWrite || catalogLoading || !!catalogError || missingInstanceResources
        "
        @click="configureInstance"
        >{{ t('governanceUi.configureInstance') }}</UiButton
      >
      <template v-else>
        <FormContainer
          :key="instanceSession"
          ref="instanceFormRef"
          :model="instance"
          :rules="instanceFormRules"
          label-placement="top"
          :disabled="busy || !canWrite"
          :readonly="!canWrite"
          :submitting="busy"
          :aria-busy="busy || instanceValidation"
          @submit="instantiate"
          ><FormField :label="t('common.name')" path="name" required
            ><UiInput v-model:value="instance.name" /></FormField
          ><FormField :label="t('common.iri')" path="iri" required
            ><UiInput v-model:value="instance.iri" :title="instance.iri" /></FormField
          ><FormField :label="t('common.labelZh')" path="labelZh" required
            ><UiInput v-model:value="instance.labelZh" /></FormField
          ><FormField :label="t('common.labelEn')" path="labelEn"
            ><UiInput v-model:value="instance.labelEn" /></FormField></FormContainer
        ><UiButton
          type="primary"
          :loading="busy || instanceValidation"
          :disabled="
            busy ||
            !canWrite ||
            instanceValidation ||
            catalogLoading ||
            !!catalogError ||
            missingInstanceResources
          "
          @click="instantiate"
          >{{ t('templates.instantiate') }}</UiButton
        ></template
      ></UiModal
    >
  </section>
</template>

<style scoped>
.templates-page {
  display: grid;
  gap: 16px;
}
.templates-page :deep(.ui-card),
.instance-preview {
  background: var(--bg-surface);
  border-color: var(--border);
  border-radius: var(--radius-medium);
}
.instance-preview {
  display: grid;
  gap: 12px;
  margin-bottom: 20px;
  overflow-wrap: anywhere;
}
h2,
p {
  margin: 0;
}
p {
  color: var(--text-secondary);
}
.filters,
.pin-hint {
  margin: 16px 0;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}
.editor-form {
  margin-top: 16px;
}
.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
@media (max-width: 640px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>

<style scoped src="../../styles/observatory.css"></style>
