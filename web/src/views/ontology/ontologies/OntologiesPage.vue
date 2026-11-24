<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import type { Ontology } from '@/api/ontology'
import { ontologyApi } from '@/api/ontology'
import PageHeader from '@/components/PageHeader.vue'
import type { DataTableColumns, FormInst, FormRules } from '@/components/ui'
import {
  FormContainer,
  FormField,
  SearchPanel,
  UiAlert,
  UiButton,
  UiDataTable,
  UiDrawer,
  UiDrawerContent,
  UiEmpty,
  UiInput,
  UiPopconfirm,
  UiSelect,
  UiSpace,
  UiSpin,
} from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useDraftGuard } from '@/composables/useDraftGuard'
import { useAuthStore } from '@/stores/auth'

/**
 * 本体库。
 *
 * 本体是「实体类型 + 关系类型 + 业务域」装配出来的产物，此前只能在设计器的
 * 下拉里选，没有列表页、也没有直接新建的入口——`ontologyApi.create` 在 API 层
 * 存在但从未被任何页面调用，设计器空态却写着「或直接创建一个本体」。
 */

const auth = useAuthStore()
const canWrite = computed(() => ['ADMIN', 'EDITOR'].includes(auth.user?.role ?? ''))
const { t, locale } = useI18n()
const { toMessage } = useApiError()
const router = useRouter()
let listGeneration = 0
let alive = true
onBeforeUnmount(() => {
  alive = false
  listGeneration++
})
const numbers = computed(() => new Intl.NumberFormat(locale.value))

const loading = ref(false)
const items = ref<Ontology[]>([])
const searchQuery = ref('')
const appliedQuery = ref('')
const page = ref(1)
const statusFilter = ref<Ontology['status'] | null>(null)
const visibleItems = computed(() =>
  statusFilter.value
    ? items.value.filter((item) => item.status === statusFilter.value)
    : items.value,
)
const statusCounts = computed(() =>
  (['DRAFT', 'PUBLISHED', 'ARCHIVED'] as const).map((status) => ({
    status,
    count: items.value.filter((item) => item.status === status).length,
  })),
)
const error = ref('')
const notice = ref('')
const publishingId = ref<number | null>(null)
const removingId = ref<number | null>(null)

const showCreate = ref(false)
const creating = ref(false)
const createError = ref('')
const formRef = ref<FormInst | null>(null)
/** 抽屉两用：新建 / 编辑。编辑时机读名与 IRI 是身份，只读展示。 */
const mode = ref<'create' | 'edit'>('create')
const editingId = ref<number | null>(null)
const editingRevision = ref(0)
const editingEditRevision = ref(0)
const detailReady = ref(false)
const detailLoading = ref(false)
let editGeneration = 0
const formData = ref({
  name: '',
  iri: '',
  labelZh: '',
  labelEn: '',
  definitionZh: '',
  definitionEn: '',
})

const rules = computed<FormRules>(() => ({
  // 编辑态机读名只读，不再校验 pattern，避免禁用字段卡住提交
  name:
    mode.value === 'edit'
      ? []
      : [
          { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
          {
            pattern: /^[A-Z][A-Za-z0-9]*$/,
            message: t('ontology.namePattern'),
            trigger: ['blur', 'input'],
          },
        ],
  iri:
    mode.value === 'edit'
      ? []
      : [{ required: true, message: t('common.required'), trigger: ['blur', 'input'] }],
  labelZh: { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
}))

/** 状态色与校验四态同一套语义：已发布=pass / 草稿=notrun / 归档=na。 */
const STATUS_VAR: Record<string, string> = {
  PUBLISHED: 'var(--s-pass)',
  DRAFT: 'var(--s-notrun)',
  ARCHIVED: 'var(--s-na)',
}

function displayLabel(row: Ontology): string {
  const labels = row.label_i18n ?? {}
  return labels[locale.value]?.trim() || t('enumDictionaries.untranslated')
}

function renderStatus(status: Ontology['status']) {
  return h('span', { class: 'status-tag', style: { '--dot': STATUS_VAR[status] } }, [
    h('i', { class: 'status-dot' }),
    t(`resourceStatus.${status}`),
  ])
}

function openDesigner(row: Ontology) {
  void router.push({ name: 'designer', query: { ontology: String(row.id) } })
}

const columns = computed<DataTableColumns<Ontology>>(() => [
  {
    title: t('common.displayName'),
    key: 'name',
    minWidth: 200,
    render(row) {
      const label = displayLabel(row)
      return h('div', { class: 'cell-name' }, [
        h('span', { class: 'cell-primary' }, label),
        label === row.name ? null : h('span', { class: 'cell-sub mono' }, row.name),
      ])
    },
  },
  {
    title: t('common.iri'),
    key: 'iri',
    minWidth: 300,
    render: (row) => h('span', { class: 'iri', title: row.iri }, row.iri),
  },
  {
    title: t('common.status'),
    key: 'status',
    width: 110,
    render: (row) => renderStatus(row.status),
  },
  {
    title: t('common.revision'),
    key: 'current_revision',
    width: 90,
    render: (row) => h('span', { class: 'mono rev' }, `v${row.current_revision}`),
  },
  {
    title: t('common.actions'),
    key: 'actions',
    fixed: 'right',
    width: 320,
    render: (row) =>
      h(UiSpace, { size: 4, wrap: false }, () => [
        h(
          UiButton,
          { size: 'small', quaternary: true, onClick: () => openDesigner(row) },
          { default: () => t('ontology.openDesigner') },
        ),
        // 草稿才能编辑/发布：发布即冻结，之后不可再改
        canWrite.value && row.status === 'DRAFT'
          ? h(
              UiButton,
              { size: 'small', quaternary: true, onClick: () => openEdit(row) },
              { default: () => t('common.edit') },
            )
          : null,
        canWrite.value && row.status === 'DRAFT'
          ? h(
              UiButton,
              {
                size: 'small',
                type: 'primary',
                quaternary: true,
                loading: publishingId.value === row.id,
                disabled: publishingId.value !== null && publishingId.value !== row.id,
                onClick: () => void publish(row),
              },
              { default: () => t('common.publish') },
            )
          : null,
        h(
          UiPopconfirm,
          { onPositiveClick: () => void remove(row) },
          {
            default: () => t('ontology.deleteConfirm', { name: displayLabel(row) }),
            trigger: () =>
              h(
                UiButton,
                {
                  size: 'small',
                  quaternary: true,
                  type: 'error',
                  loading: removingId.value === row.id,
                  disabled:
                    !canWrite.value || (removingId.value !== null && removingId.value !== row.id),
                },
                { default: () => t('common.delete') },
              ),
          },
        ),
      ]),
  },
])

async function loadList() {
  if (!alive) return
  const generation = ++listGeneration
  loading.value = true
  error.value = ''
  try {
    const next = await ontologyApi.list({ q: appliedQuery.value })
    if (generation === listGeneration) items.value = next
  } catch (err) {
    if (generation === listGeneration) {
      items.value = []
      error.value = toMessage(err)
    }
  } finally {
    if (generation === listGeneration) loading.value = false
  }
}

async function publish(row: Ontology) {
  if (!canWrite.value) return
  if (publishingId.value !== null) return
  publishingId.value = row.id
  error.value = ''
  notice.value = ''
  try {
    await ontologyApi.publish(row.id, row.edit_revision)
    if (!alive) return
    notice.value = t('ontology.published')
    await loadList()
  } catch (err) {
    if (alive) error.value = toMessage(err)
  } finally {
    if (alive) publishingId.value = null
  }
}

async function remove(row: Ontology) {
  if (!canWrite.value) return
  if (removingId.value !== null) return
  removingId.value = row.id
  error.value = ''
  notice.value = ''
  try {
    await ontologyApi.remove(row.id)
    if (!alive) return
    notice.value = t('ontology.deleted', { name: displayLabel(row) })
    await loadList()
  } catch (err) {
    if (alive) error.value = toMessage(err)
  } finally {
    if (alive) removingId.value = null
  }
}

/** 机读名与 IRI 是资源身份，编辑态只读；两种模式下的说明文案不同。 */
const nameFeedback = computed(() =>
  mode.value === 'edit' ? t('ontology.nameImmutable') : t('ontology.nameHint'),
)

function emptyForm() {
  return { name: '', iri: '', labelZh: '', labelEn: '', definitionZh: '', definitionEn: '' }
}

/** 打开抽屉即重置表单与校验态，避免上一轮报错残留。 */
function openCreate() {
  if (!canWrite.value) return
  creating.value = false
  editGeneration += 1
  detailReady.value = true
  detailLoading.value = false
  mode.value = 'create'
  editingId.value = null
  formData.value = emptyForm()
  createError.value = ''
  showCreate.value = true
  formRef.value?.restoreValidation()
}

/**
 * 编辑本体：后端 `PUT /ontologies/{id}` 一直存在，此前没有任何入口
 * —— 本体建好之后标签与定义就再也改不了，与实体类型同一类缺口。
 */
function openEdit(row: Ontology) {
  if (!canWrite.value) return
  creating.value = false
  editGeneration += 1
  detailReady.value = false
  mode.value = 'edit'
  editingId.value = row.id
  editingRevision.value = row.current_revision
  editingEditRevision.value = row.edit_revision
  formData.value = {
    name: row.name,
    iri: row.iri,
    labelZh: row.label_i18n?.['zh-CN'] ?? '',
    labelEn: row.label_i18n?.['en-US'] ?? '',
    definitionZh: '',
    definitionEn: '',
  }
  createError.value = ''
  showCreate.value = true
  formRef.value?.restoreValidation()
  void loadEditDetail()
}

async function loadEditDetail() {
  const id = editingId.value
  if (id === null) return
  const generation = ++editGeneration
  detailReady.value = false
  detailLoading.value = true
  createError.value = ''
  try {
    const info = await ontologyApi.get(id)
    if (generation !== editGeneration || !showCreate.value) return
    formData.value.labelZh = info.label_i18n?.['zh-CN'] ?? ''
    formData.value.labelEn = info.label_i18n?.['en-US'] ?? ''
    formData.value.definitionZh = info.definition_i18n?.['zh-CN'] ?? ''
    formData.value.definitionEn = info.definition_i18n?.['en-US'] ?? ''
    editingRevision.value = info.current_revision
    editingEditRevision.value = info.edit_revision
    detailReady.value = true
  } catch (err) {
    if (generation === editGeneration) createError.value = toMessage(err)
  } finally {
    if (generation === editGeneration) detailLoading.value = false
  }
}

watch(
  showCreate,
  (show) => {
    if (!show) editGeneration += 1
  },
  { flush: 'sync' },
)
onBeforeUnmount(() => {
  editGeneration += 1
})

async function handleSubmit() {
  if (!canWrite.value) return
  if (!detailReady.value || creating.value || !showCreate.value) return
  const generation = editGeneration
  createError.value = ''
  creating.value = true
  try {
    await formRef.value?.validate()
  } catch {
    if (generation === editGeneration) creating.value = false
    return
  }
  if (generation !== editGeneration || !detailReady.value || !showCreate.value) return
  const f = formData.value
  const labelZh = f.labelZh.trim()
  const label: Record<string, string> = { 'zh-CN': labelZh }
  if (f.labelEn.trim()) label['en-US'] = f.labelEn.trim()
  const definition: Record<string, string> = {}
  if (f.definitionZh.trim()) definition['zh-CN'] = f.definitionZh.trim()
  if (f.definitionEn.trim()) definition['en-US'] = f.definitionEn.trim()

  creating.value = true
  try {
    if (mode.value === 'edit' && editingId.value !== null) {
      await ontologyApi.update(
        editingId.value,
        { label_i18n: label, definition_i18n: definition, if_match: editingRevision.value },
        editingEditRevision.value,
      )
      if (generation !== editGeneration) return
      showCreate.value = false
      notice.value = t('ontology.updated')
      await loadList()
      return
    }

    const created = await ontologyApi.create({
      name: f.name.trim(),
      iri: f.iri.trim(),
      label_i18n: label,
      definition_i18n: definition,
      ref_resource_ids: [],
      rule_ids: [],
    })
    if (generation !== editGeneration) return
    showCreate.value = false
    notice.value = t('ontology.created')
    await loadList()
    // 新建后直接进设计器装配，省掉一次「再点一下」
    void router.push({ name: 'designer', query: { ontology: String(created.id) } })
  } catch (err) {
    if (generation === editGeneration) createError.value = toMessage(err)
  } finally {
    if (generation === editGeneration || !showCreate.value) creating.value = false
  }
}

onMounted(() => void loadList())

const editorVisible = useDraftGuard(
  showCreate,
  () => formData.value,
  () => mode.value === 'create' || detailReady.value,
)
watch(statusFilter, () => {
  page.value = 1
})
function submitSearch(query: string) {
  appliedQuery.value = query
  page.value = 1
  void loadList()
}
function clearSearch() {
  appliedQuery.value = ''
  page.value = 1
  void loadList()
}
function resetSearch() {
  searchQuery.value = ''
  statusFilter.value = null
  clearSearch()
}
</script>

<template>
  <section class="page">
    <PageHeader
      :title="t('page.ontologies')"
      :eyebrow="t('studio.ontologyLedger')"
      :description="t('ontology.description')"
    >
      <template #actions>
        <UiButton type="primary" :disabled="!canWrite" @click="openCreate">{{
          t('ontology.create')
        }}</UiButton>
      </template>
    </PageHeader>
    <UiAlert v-if="!canWrite" type="info" class="alert">{{ t('ui.readonly') }}</UiAlert>

    <div class="ledger-readouts" :aria-label="t('common.status')">
      <button
        v-for="entry in statusCounts"
        :key="entry.status"
        type="button"
        :aria-pressed="statusFilter === entry.status"
        :style="{ '--state-color': STATUS_VAR[entry.status] }"
        @click="statusFilter = statusFilter === entry.status ? null : entry.status"
      >
        <span>{{ t(`resourceStatus.${entry.status}`) }}</span
        ><strong>{{
          loading || error ? t('common.noneValue') : numbers.format(entry.count)
        }}</strong>
      </button>
      <p>{{ t('studio.freezeBoundary') }}</p>
    </div>

    <UiAlert v-if="error" type="error" role="alert" class="feedback"
      >{{ error }} <UiButton @click="loadList">{{ t('ui.retry') }}</UiButton></UiAlert
    >
    <UiAlert v-if="notice" type="success" role="status" class="feedback">{{ notice }}</UiAlert>

    <SearchPanel
      v-model:query="searchQuery"
      :loading="loading"
      class="toolbar"
      @submit="submitSearch"
      @clear="clearSearch"
      @reset="resetSearch"
    >
      <template #filter
        ><UiSelect
          v-model:value="statusFilter"
          clearable
          class="status-filter"
          :aria-label="t('common.status')"
          :placeholder="t('common.status')"
          :options="
            statusCounts.map((entry) => ({
              value: entry.status,
              label: t('resourceStatus.' + entry.status),
            }))
          "
      /></template>
      <template #actions
        ><UiButton attr-type="submit">{{ t('common.search') }}</UiButton
        ><UiButton @click="resetSearch">{{ t('ds.search.reset') }}</UiButton
        ><UiButton :loading="loading" @click="loadList">{{
          t('graph.refresh')
        }}</UiButton></template
      >
    </SearchPanel>

    <UiSpin :show="loading">
      <div class="card">
        <UiDataTable
          mode="local"
          :page="page"
          :columns="columns"
          :rows="visibleItems"
          size="small"
          :bordered="false"
          :pagination="{ pageSize: 20 }"
          :scroll-x="890"
          :max-height="560"
          :row-key="(row: Ontology) => row.id"
          @update:page="page = $event"
        >
          <template #empty>
            <UiEmpty v-if="!error && !loading" :description="t('ontology.empty')">
              <template #extra>
                <UiButton type="primary" size="small" :disabled="!canWrite" @click="openCreate">
                  {{ t('ontology.create') }}
                </UiButton>
              </template>
            </UiEmpty>
          </template>
        </UiDataTable>
      </div>
    </UiSpin>

    <UiDrawer
      v-model:show="editorVisible"
      :width="520"
      :mask-closable="!creating"
      :close-on-esc="!creating"
    >
      <UiDrawerContent
        :title="mode === 'edit' ? t('ontology.edit') : t('ontology.create')"
        :closable="!creating"
      >
        <UiAlert v-if="createError" type="error" role="alert" class="create-error">{{
          createError
        }}</UiAlert>
        <UiButton
          v-if="mode === 'edit' && !detailReady"
          :loading="detailLoading"
          @click="loadEditDetail"
        >
          {{ t('graph.refresh') }}
        </UiButton>
        <FormContainer
          ref="formRef"
          :model="formData"
          :rules="rules"
          :disabled="creating || !detailReady"
          label-placement="top"
        >
          <div class="form-section-title">{{ t('studio.identity') }}</div>
          <FormField :label="t('common.name')" path="name">
            <UiInput
              v-model:value="formData.name"
              :disabled="mode === 'edit'"
              placeholder="EnterpriseOntology"
            />
            <template #feedback>{{ nameFeedback }}</template>
          </FormField>
          <FormField :label="t('common.iri')" path="iri">
            <UiInput
              v-model:value="formData.iri"
              :disabled="mode === 'edit'"
              placeholder="urn:knowledge:ontology:enterprise"
            />
          </FormField>
          <div class="form-section-title">{{ t('studio.labels') }}</div>
          <FormField :label="t('common.labelZh')" path="labelZh">
            <UiInput v-model:value="formData.labelZh" />
          </FormField>
          <FormField :label="t('common.labelEn')" path="labelEn">
            <UiInput v-model:value="formData.labelEn" />
          </FormField>
          <div class="form-section-title">{{ t('studio.definition') }}</div>
          <FormField :label="t('common.definitionZh')" path="definitionZh">
            <UiInput
              v-model:value="formData.definitionZh"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
            />
          </FormField>
          <FormField :label="t('common.definitionEn')" path="definitionEn">
            <UiInput
              v-model:value="formData.definitionEn"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
            />
          </FormField>
        </FormContainer>
        <p v-if="mode === 'create'" class="create-hint">{{ t('ontology.createHint') }}</p>
        <template #footer>
          <div class="drawer-actions">
            <UiButton :disabled="creating" @click="editorVisible = false">
              {{ t('common.cancel') }}
            </UiButton>
            <UiButton
              type="primary"
              :loading="creating"
              :disabled="!detailReady"
              @click="handleSubmit"
            >
              {{ t('common.save') }}
            </UiButton>
          </div>
        </template>
      </UiDrawerContent>
    </UiDrawer>
  </section>
</template>

<style scoped>
.page {
  min-width: 0;
  padding-bottom: var(--space-5);
}

.feedback {
  margin-bottom: var(--space-3);
}

.toolbar {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  margin-bottom: var(--space-3);
}

.search-field {
  min-width: 0;
}

.search {
  max-width: 280px;
}

.spacer {
  flex: 1;
}

.card {
  overflow: hidden;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 9px;
}

.ledger-readouts {
  display: flex;
  gap: 0;
  align-items: stretch;
  margin-bottom: 16px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-panel);
  overflow: hidden;
}
.ledger-readouts button {
  display: flex;
  gap: 24px;
  align-items: center;
  padding: 14px 18px;
  border: 0;
  border-right: 1px solid var(--border);
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  cursor: pointer;
}
.ledger-readouts strong {
  color: var(--state-color);
  font: 600 22px var(--font-mono, monospace);
}
.ledger-readouts button[aria-pressed='true'] {
  background: var(--bg-inset);
  box-shadow: inset 0 -2px var(--state-color);
}
.ledger-readouts p {
  margin: 0;
  padding: 14px 18px;
  align-self: center;
  color: var(--text-secondary);
  font-size: 12px;
}
.status-filter {
  width: 170px;
}
.form-section-title {
  padding: 12px 0 8px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--border);
  color: var(--text-primary);
  font-weight: 600;
}
@media (max-width: 768px) {
  .ledger-readouts {
    flex-wrap: wrap;
  }
  .ledger-readouts button {
    flex: 1;
    gap: 12px;
    padding: 12px;
  }
  .toolbar {
    flex-wrap: wrap;
  }
  .search-field {
    flex: 1 1 100%;
  }
}

:deep(.cell-name) {
  display: flex;
  gap: 8px;
  align-items: baseline;
}

:deep(.cell-primary) {
  font-weight: 500;
}

:deep(.cell-sub) {
  color: var(--text-tertiary);
  font-size: 11px;
}

:deep(.rev) {
  color: var(--text-tertiary);
  font-size: 11px;
}

:deep(.status-tag) {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  padding: 2px 9px;
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-pill);
}

:deep(.status-dot) {
  width: 6px;
  height: 6px;
  background: var(--dot);
  border-radius: 50%;
}

.create-error {
  margin-bottom: var(--space-3);
}

.create-hint {
  margin: 0;
  color: var(--text-tertiary);
  font-size: var(--font-caption);
}

.drawer-actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
}
</style>
