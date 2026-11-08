<script setup lang="ts">
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NModal,
  NPagination,
  NPopconfirm,
  NSelect,
  NSpace,
  NTable,
  NTag,
} from 'naive-ui'
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Template, TemplateInput, TemplateOntology, TemplateResource } from '@/api/templates'
import { templatesApi as api } from '@/api/templates'
import PageHeader from '@/components/PageHeader.vue'
import { useDraftGuard } from '@/composables/useDraftGuard'
import TemplateCoreCheck from '@/views/governance/components/TemplateCoreCheck.vue'
import { useGovernanceAccess } from '@/views/governance/composables/useGovernanceAccess'

const { t, locale } = useI18n()
const { canWrite } = useGovernanceAccess()
const items = ref<Template[]>([])
const total = ref(0)
const page = ref(1)
const query = ref('')
const search = ref('')
const filter = ref<string | null>(null)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
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
const controller = new AbortController()
let listController: AbortController | undefined

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
    item.label_i18n?.[locale.value] ||
    `${item.label_i18n?.['zh-CN'] || item.name} (${t('rules.untranslated')})`
  )
}
const readonly = computed(() => mode.value === 'edit' && saved.value?.builtin)
const editorVisible = useDraftGuard(
  editor,
  () =>
    JSON.stringify(form.value) !== JSON.stringify(saved.value ? input(saved.value) : empty()) ||
    (mode.value === 'fromOntology' &&
      (ontologyId.value !== null || ontologyRevision.value !== null)),
  () => canWrite.value && !readonly.value,
)
const instanceVisible = useDraftGuard(
  instantiateVisible,
  () => instance.value,
  () => canWrite.value && instanceStep.value === 'configure',
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
const columns = computed(() => [
  { title: t('common.name'), key: 'name' },
  { title: t('common.label'), key: 'label_i18n', render: label },
  { title: t('templates.source'), key: 'source' },
  {
    title: t('templates.kind'),
    key: 'builtin',
    render: (row: Template) =>
      h(NTag, {}, { default: () => t(row.builtin ? 'templates.builtin' : 'templates.custom') }),
  },
  { title: t('common.revision'), key: 'revision' },
  { title: t('templates.references'), key: 'reference_count' },
  {
    title: t('common.actions'),
    key: 'actions',
    render: (row: Template) =>
      h(
        NSpace,
        {},
        {
          default: () => [
            h(
              NButton,
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
              NButton,
              { size: 'small', disabled: busy.value, onClick: () => open('edit', row) },
              { default: () => t('templates.details') },
            ),
            h(
              NButton,
              {
                size: 'small',
                disabled: busy.value || !canWrite.value,
                onClick: () => open('copy', row),
              },
              { default: () => t('templates.copy') },
            ),
            h(
              NButton,
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
async function run(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await action()
  } catch (err) {
    if (!controller.signal.aborted) error.value = message(err)
  } finally {
    busy.value = false
  }
}
async function load() {
  listController?.abort()
  const request = new AbortController()
  listController = request
  loading.value = true
  error.value = ''
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
    if (!items.value.length && page.value > 1) page.value--
  } catch (err) {
    if (!request.signal.aborted) error.value = message(err)
  } finally {
    if (!request.signal.aborted) loading.value = false
  }
}
async function open(next: typeof mode.value, item?: Template) {
  if (next !== 'edit' && !canWrite.value) return
  await run(async () => {
    const latest = item ? await api.get(item.id) : null
    if (controller.signal.aborted) return
    saved.value = latest
    form.value = latest ? input(latest) : empty()
    mode.value = next
    resourceId.value = null
    ontologyId.value = null
    ontologyRevision.value = null
    editor.value = true
  })
}
function addResource() {
  if (
    !resourcesEditable.value ||
    busy.value ||
    resourceId.value === null ||
    resourceRevision.value === null
  )
    return
  form.value.resources = [
    ...(form.value.resources || []),
    { resource_id: resourceId.value, pinned_revision: resourceRevision.value },
  ]
  resourceId.value = null
}
async function save() {
  if (!canSave.value) return
  await run(async () => {
    const metadata = {
      name: form.value.name,
      label_i18n: Object.fromEntries(
        Object.entries(form.value.label_i18n).filter(([, text]) => text.trim()),
      ),
      source: form.value.source,
      basis: form.value.basis,
    }
    const result =
      mode.value === 'fromOntology'
        ? await api.fromOntology({
            ...metadata,
            ontology_id: ontologyId.value!,
            ontology_revision: ontologyRevision.value!,
          })
        : mode.value === 'copy' && saved.value
          ? await api.copy(saved.value, metadata)
          : mode.value === 'edit' && saved.value
            ? await api.update(saved.value, { ...metadata, resources: form.value.resources })
            : await api.create({ ...metadata, resources: form.value.resources })
    if (controller.signal.aborted) return
    saved.value = result
    form.value = input(result)
    mode.value = 'edit'
    notice.value = t('templates.saved')
    await load()
  })
}
async function remove() {
  if (!canWrite.value || !saved.value || saved.value.builtin || saved.value.reference_count > 0)
    return
  const item = saved.value
  await run(async () => {
    await api.remove(item)
    if (controller.signal.aborted) return
    editor.value = false
    notice.value = t('templates.deleted')
    await load()
  })
}
async function prepareInstance(item: Template) {
  await run(async () => {
    const latest = await api.get(item.id)
    if (controller.signal.aborted) return
    instanceTemplate.value = latest
    instanceStep.value = 'preview'
    instance.value = { name: '', iri: '', labelZh: '', labelEn: '' }
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
  instanceStep.value = 'configure'
}
async function instantiate() {
  if (
    !canWrite.value ||
    instanceStep.value !== 'configure' ||
    !instanceTemplate.value ||
    catalogLoading.value ||
    catalogError.value ||
    missingInstanceResources.value ||
    !instance.value.name.trim() ||
    !instance.value.iri.trim() ||
    !instance.value.labelZh.trim()
  )
    return
  const item = instanceTemplate.value
  await run(async () => {
    const created = await api.instantiate(item, {
      name: instance.value.name,
      iri: instance.value.iri,
      label_i18n: {
        'zh-CN': instance.value.labelZh,
        ...(instance.value.labelEn.trim() ? { 'en-US': instance.value.labelEn } : {}),
      },
    })
    if (controller.signal.aborted) return
    instantiateVisible.value = false
    notice.value = t('templates.createdOntology', {
      name: created.name,
      template: created.template?.name || item.name,
    })
    await load()
    ontologies.value = await api.ontologies(controller.signal)
  })
}
watch(resourceId, () => {
  resourceRevision.value = versionOptions.value.at(-1)?.value ?? null
})
watch(ontologyId, () => {
  ontologyRevision.value =
    ontologies.value.find((r) => r.id === ontologyId.value)?.current_revision ?? null
})
watch([page, search, filter], load, { immediate: true })
watch([search, filter], () => {
  page.value = 1
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
  <NDrawer
    :show="!!checkingTemplate"
    width="min(600px, 100vw)"
    @update:show="
      (value) => {
        if (!value) checkingTemplate = null
      }
    "
  >
    <NDrawerContent :title="t('coreCheck.title')" closable>
      <TemplateCoreCheck
        v-if="checkingTemplate"
        :key="checkingTemplate.id"
        :template-id="checkingTemplate.id"
      />
    </NDrawerContent>
  </NDrawer>
  <section class="templates-page">
    <PageHeader :title="t('templates.title')" :description="t('templates.intro')">
      <template #actions>
        <NButton :disabled="busy || !canWrite" @click="open('fromOntology')">{{
          t('templates.fromOntology')
        }}</NButton>
        <NButton type="primary" :disabled="busy || !canWrite" @click="open('create')">{{
          t('templates.create')
        }}</NButton>
      </template>
    </PageHeader>
    <NAlert v-if="!canWrite" type="info">{{ t('governanceUi.readOnly') }}</NAlert>
    <NAlert v-if="error && !editor && !instantiateVisible" type="error" role="alert"
      >{{ error }}
      <NButton size="small" @click="load">{{ t('governanceUi.retry') }}</NButton>
    </NAlert>
    <NAlert v-if="catalogError" type="error" role="alert"
      >{{ catalogError }}
      <NButton size="small" @click="loadCatalog">{{ t('governanceUi.retry') }}</NButton>
    </NAlert>
    <NAlert v-if="notice" type="success" role="status">{{ notice }}</NAlert>
    <NCard size="small"
      ><NSpace class="filters" align="center"
        ><NFormItem
          :label="t('common.search')"
          label-placement="left"
          :label-width="72"
          :show-feedback="false"
          ><NInput
            v-model:value="query"
            clearable
            @keyup.enter="search = query.trim()" /></NFormItem
        ><NButton @click="search = query.trim()">{{ t('common.search') }}</NButton
        ><NFormItem
          :label="t('templates.kind')"
          label-placement="left"
          :label-width="72"
          :show-feedback="false"
          ><NSelect
            v-model:value="filter"
            :options="filterOptions"
            :placeholder="t('templates.all')"
            clearable
            style="width: 180px" /></NFormItem
        ><NButton :loading="loading" @click="load">{{ t('graph.refresh') }}</NButton></NSpace
      >
      <p v-if="loading" role="status">{{ t('common.loading') }}</p>
      <NDataTable
        v-else-if="!error"
        :data="items"
        :columns="columns"
        :loading="loading"
        :scroll-x="1000"
        ><template #empty
          ><NEmpty :description="t('governanceUi.templatesEmpty')" /></template></NDataTable
      ><NPagination
        v-if="!loading && !error && total > 20"
        v-model:page="page"
        :page-size="20"
        :item-count="total"
        class="pagination"
    /></NCard>
    <NDrawer
      v-model:show="editorVisible"
      width="min(820px, 100vw)"
      :mask-closable="false"
      :close-on-esc="!busy"
      ><NDrawerContent :title="t(`templates.${mode}`)" :closable="!busy">
        <NSpace vertical
          ><NAlert v-if="!canWrite" type="info">{{ t('governanceUi.readOnly') }}</NAlert
          ><NAlert v-if="error" type="error" role="alert">{{ error }}</NAlert
          ><NAlert v-if="notice" type="success">{{ notice }}</NAlert
          ><NAlert v-if="readonly" type="info">{{ t('templates.builtinHint') }}</NAlert
          ><NAlert v-if="saved" type="info">{{
            t('templates.revisionHint', { revision: saved.revision, count: saved.reference_count })
          }}</NAlert></NSpace
        >
        <NForm label-placement="top" :disabled="busy || readonly || !canWrite" class="editor-form">
          <div class="form-grid">
            <NFormItem :label="t('common.name')" required
              ><NInput v-model:value="form.name" /></NFormItem
            ><NFormItem :label="t('templates.source')" required
              ><NInput v-model:value="form.source" /></NFormItem
            ><NFormItem :label="t('common.labelZh')" required
              ><NInput v-model:value="form.label_i18n['zh-CN']" /></NFormItem
            ><NFormItem :label="t('common.labelEn')"
              ><NInput v-model:value="form.label_i18n['en-US']"
            /></NFormItem>
          </div>
          <NFormItem :label="t('templates.basis')" required
            ><NInput v-model:value="form.basis" type="textarea"
          /></NFormItem>
          <template v-if="mode === 'fromOntology'"
            ><NFormItem :label="t('export.ontology')" required
              ><NSelect
                v-model:value="ontologyId"
                :options="ontologyOptions"
                filterable /></NFormItem
            ><NFormItem :label="t('export.revision')" required
              ><NInputNumber
                v-model:value="ontologyRevision"
                :min="1"
                :precision="0"
                :max="ontologies.find((r) => r.id === ontologyId)?.current_revision" /></NFormItem
          ></template>
          <template v-else
            ><h3>{{ t('templates.resources') }}</h3>
            <NSpace v-if="resourcesEditable" align="center" class="filters"
              ><NFormItem
                :label="t('templates.resource')"
                label-placement="left"
                :label-width="72"
                :show-feedback="false"
                ><NSelect
                  v-model:value="resourceId"
                  :options="resourceOptions"
                  filterable
                  style="width: 280px" /></NFormItem
              ><NFormItem
                :label="t('templates.pinnedRevision')"
                label-placement="left"
                :label-width="96"
                :show-feedback="false"
                ><NSelect
                  v-model:value="resourceRevision"
                  :options="versionOptions"
                  style="width: 110px" /></NFormItem
              ><NButton
                :disabled="
                  busy || !resourcesEditable || resourceId === null || resourceRevision === null
                "
                @click="addResource"
                >{{ t('templates.addResource') }}</NButton
              ></NSpace
            >
            <NTable size="small"
              ><thead>
                <tr>
                  <th>{{ t('templates.resource') }}</th>
                  <th>{{ t('templates.pinnedRevision') }}</th>
                  <th v-if="resourcesEditable">{{ t('common.actions') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(entry, index) in form.resources" :key="entry.resource_id">
                  <td>
                    {{
                      catalog.find((r) => r.resource_id === entry.resource_id)?.name ||
                      t('templates.resourceUnavailable', { id: entry.resource_id })
                    }}
                  </td>
                  <td>{{ entry.pinned_revision }}</td>
                  <td v-if="resourcesEditable">
                    <NButton
                      size="small"
                      :disabled="busy || !resourcesEditable"
                      @click="form.resources?.splice(index, 1)"
                      >{{ t('common.delete') }}</NButton
                    >
                  </td>
                </tr>
              </tbody></NTable
            > </template
          ><NAlert type="info" class="pin-hint">{{ t('templates.pinHint') }}</NAlert>
        </NForm>
        <template #footer
          ><NSpace justify="space-between" style="width: 100%"
            ><NPopconfirm
              v-if="mode === 'edit' && saved"
              :disabled="busy || readonly || !canWrite || saved.reference_count > 0"
              @positive-click="remove"
              ><template #trigger
                ><NButton
                  type="error"
                  secondary
                  :disabled="busy || readonly || !canWrite || saved.reference_count > 0"
                  >{{ t('common.delete') }}</NButton
                ></template
              >{{ t('templates.confirmDelete', { name: saved.name }) }}</NPopconfirm
            ><NSpace
              ><NButton :disabled="busy" @click="editorVisible = false">{{
                t('common.cancel')
              }}</NButton
              ><NButton type="primary" :disabled="busy || !canSave" :loading="busy" @click="save">{{
                t('common.save')
              }}</NButton></NSpace
            ></NSpace
          ></template
        >
      </NDrawerContent></NDrawer
    >
    <NModal
      v-model:show="instanceVisible"
      preset="card"
      :title="
        t(instanceStep === 'preview' ? 'governanceUi.previewTemplate' : 'templates.instantiate')
      "
      style="width: min(720px, 100vw)"
      :mask-closable="false"
      :closable="!busy"
      :close-on-esc="!busy"
      ><NAlert v-if="error" type="error" role="alert">{{ error }}</NAlert>
      <NAlert v-if="!canWrite" type="info">{{ t('governanceUi.readOnly') }}</NAlert>
      <section v-if="instanceTemplate" class="instance-preview">
        <h3>{{ label(instanceTemplate) }}</h3>
        <p>{{ t('governanceUi.templateRevision', { revision: instanceTemplate.revision }) }}</p>
        <p>{{ instanceTemplate.source }} · {{ instanceTemplate.basis }}</p>
        <NAlert type="info">{{ t('governanceUi.instanceHint') }}</NAlert>
        <p v-if="catalogLoading" role="status">{{ t('common.loading') }}</p>
        <NAlert v-else-if="catalogError" type="error"
          >{{ catalogError }}
          <NButton @click="loadCatalog">{{ t('governanceUi.retry') }}</NButton>
        </NAlert>
        <template v-else>
          <NAlert v-if="missingInstanceResources" type="warning">{{
            t('governanceUi.missingMembers')
          }}</NAlert>
          <NTable size="small">
            <thead>
              <tr>
                <th>{{ t('templates.resource') }}</th>
                <th>{{ t('templates.pinnedRevision') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="entry in instanceTemplate.resources" :key="entry.resource_id">
                <td>
                  {{
                    catalog.find((r) => r.resource_id === entry.resource_id)?.name ||
                    t('templates.resourceUnavailable', { id: entry.resource_id })
                  }}
                </td>
                <td>{{ entry.pinned_revision }}</td>
              </tr>
            </tbody>
          </NTable>
          <NEmpty
            v-if="!instanceTemplate.resources.length"
            :description="t('governanceUi.noMembers')"
          />
        </template>
      </section>
      <NButton
        v-if="instanceStep === 'preview'"
        type="primary"
        :disabled="
          busy || !canWrite || catalogLoading || !!catalogError || missingInstanceResources
        "
        @click="configureInstance"
        >{{ t('governanceUi.configureInstance') }}</NButton
      >
      <template v-else>
        <NForm label-placement="top" :disabled="busy || !canWrite"
          ><NFormItem :label="t('common.name')" required
            ><NInput v-model:value="instance.name" /></NFormItem
          ><NFormItem :label="t('common.iri')" required
            ><NInput v-model:value="instance.iri" /></NFormItem
          ><NFormItem :label="t('common.labelZh')" required
            ><NInput v-model:value="instance.labelZh" /></NFormItem
          ><NFormItem :label="t('common.labelEn')"
            ><NInput v-model:value="instance.labelEn" /></NFormItem></NForm
        ><NButton
          type="primary"
          :loading="busy"
          :disabled="
            busy ||
            !canWrite ||
            !instance.name.trim() ||
            !instance.iri.trim() ||
            !instance.labelZh.trim() ||
            catalogLoading ||
            !!catalogError ||
            missingInstanceResources
          "
          @click="instantiate"
          >{{ t('templates.instantiate') }}</NButton
        ></template
      ></NModal
    >
  </section>
</template>

<style scoped>
.templates-page {
  display: grid;
  gap: 16px;
}
.templates-page :deep(.n-card),
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
