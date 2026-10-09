<script setup lang="ts">
import type { DataTableColumns, FormInst, FormRules } from 'naive-ui'
import {
  NAlert,
  NButton,
  NDataTable,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NPopconfirm,
  NSpace,
  NSpin,
} from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import type { Ontology } from '@/api/ontology'
import { ontologyApi } from '@/api/ontology'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'

/**
 * 本体库。
 *
 * 本体是「实体类型 + 关系类型 + 业务域」装配出来的产物，此前只能在设计器的
 * 下拉里选，没有列表页、也没有直接新建的入口——`ontologyApi.create` 在 API 层
 * 存在但从未被任何页面调用，设计器空态却写着「或直接创建一个本体」。
 */

const { t, locale } = useI18n()
const { toMessage } = useApiError()
const router = useRouter()

const loading = ref(false)
const items = ref<Ontology[]>([])
const searchQuery = ref('')
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
  return labels[locale.value] ?? labels['zh-CN'] ?? row.name
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
    render: (row) => h('span', { class: 'iri' }, row.iri),
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
    width: 320,
    render: (row) =>
      h(NSpace, { size: 4, wrap: false }, () => [
        h(
          NButton,
          { size: 'small', quaternary: true, onClick: () => openDesigner(row) },
          { default: () => t('ontology.openDesigner') },
        ),
        // 草稿才能编辑/发布：发布即冻结，之后不可再改
        row.status === 'DRAFT'
          ? h(
              NButton,
              { size: 'small', quaternary: true, onClick: () => openEdit(row) },
              { default: () => t('common.edit') },
            )
          : null,
        row.status === 'DRAFT'
          ? h(
              NButton,
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
          NPopconfirm,
          { onPositiveClick: () => void remove(row) },
          {
            default: () => t('ontology.deleteConfirm', { name: displayLabel(row) }),
            trigger: () =>
              h(
                NButton,
                {
                  size: 'small',
                  quaternary: true,
                  type: 'error',
                  loading: removingId.value === row.id,
                  disabled: removingId.value !== null && removingId.value !== row.id,
                },
                { default: () => t('common.delete') },
              ),
          },
        ),
      ]),
  },
])

async function loadList() {
  loading.value = true
  error.value = ''
  try {
    items.value = await ontologyApi.list({ q: searchQuery.value })
  } catch (err) {
    items.value = []
    error.value = toMessage(err)
  } finally {
    loading.value = false
  }
}

async function publish(row: Ontology) {
  if (publishingId.value !== null) return
  publishingId.value = row.id
  error.value = ''
  notice.value = ''
  try {
    await ontologyApi.publish(row.id, row.edit_revision)
    notice.value = t('ontology.published')
    await loadList()
  } catch (err) {
    error.value = toMessage(err)
  } finally {
    publishingId.value = null
  }
}

async function remove(row: Ontology) {
  if (removingId.value !== null) return
  removingId.value = row.id
  error.value = ''
  notice.value = ''
  try {
    await ontologyApi.remove(row.id)
    notice.value = t('ontology.deleted', { name: displayLabel(row) })
    await loadList()
  } catch (err) {
    error.value = toMessage(err)
  } finally {
    removingId.value = null
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
  // 列表只返回 brief，定义要取详情
  void ontologyApi
    .get(row.id)
    .then((info) => {
      if (editingId.value !== row.id) return
      formData.value.definitionZh = info.definition_i18n?.['zh-CN'] ?? ''
      formData.value.definitionEn = info.definition_i18n?.['en-US'] ?? ''
    })
    .catch(() => undefined)
}

async function handleSubmit() {
  createError.value = ''
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  const f = formData.value
  const labelZh = f.labelZh.trim()
  const label: Record<string, string> = { 'zh-CN': labelZh, 'en-US': f.labelEn.trim() || labelZh }
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
    showCreate.value = false
    notice.value = t('ontology.created')
    await loadList()
    // 新建后直接进设计器装配，省掉一次「再点一下」
    void router.push({ name: 'designer', query: { ontology: String(created.id) } })
  } catch (err) {
    createError.value = toMessage(err)
  } finally {
    creating.value = false
  }
}

onMounted(() => void loadList())
</script>

<template>
  <section class="page">
    <PageHeader :title="t('page.ontologies')" :description="t('ontology.description')">
      <template #actions>
        <NButton type="primary" @click="openCreate">{{ t('ontology.create') }}</NButton>
      </template>
    </PageHeader>

    <NAlert v-if="error" type="error" role="alert" class="feedback">{{ error }}</NAlert>
    <NAlert v-if="notice" type="success" role="status" class="feedback">{{ notice }}</NAlert>

    <div class="toolbar">
      <NFormItem
        :label="t('common.search')"
        label-placement="left"
        :label-width="72"
        :show-feedback="false"
        class="search-field"
      >
        <NInput
          v-model:value="searchQuery"
          :placeholder="t('common.search')"
          clearable
          class="search"
          @keyup.enter="loadList"
          @clear="loadList"
        />
      </NFormItem>
      <span class="spacer" />
      <NButton :loading="loading" @click="loadList">{{ t('graph.refresh') }}</NButton>
    </div>

    <NSpin :show="loading">
      <div class="card">
        <NDataTable
          :columns="columns"
          :data="items"
          :bordered="false"
          :pagination="{ pageSize: 20 }"
          :scroll-x="890"
          :row-key="(row: Ontology) => row.id"
        >
          <template #empty>
            <NEmpty :description="t('ontology.empty')">
              <template #extra>
                <NButton type="primary" size="small" @click="openCreate">
                  {{ t('ontology.create') }}
                </NButton>
              </template>
            </NEmpty>
          </template>
        </NDataTable>
      </div>
    </NSpin>

    <NDrawer
      v-model:show="showCreate"
      :width="520"
      :mask-closable="!creating"
      :close-on-esc="!creating"
    >
      <NDrawerContent
        :title="mode === 'edit' ? t('ontology.edit') : t('ontology.create')"
        :closable="!creating"
      >
        <NAlert v-if="createError" type="error" class="create-error">{{ createError }}</NAlert>
        <NForm
          ref="formRef"
          :model="formData"
          :rules="rules"
          :disabled="creating"
          label-placement="top"
        >
          <NFormItem :label="t('common.name')" path="name">
            <NInput
              v-model:value="formData.name"
              :disabled="mode === 'edit'"
              placeholder="EnterpriseOntology"
            />
            <template #feedback>{{ nameFeedback }}</template>
          </NFormItem>
          <NFormItem :label="t('common.iri')" path="iri">
            <NInput
              v-model:value="formData.iri"
              :disabled="mode === 'edit'"
              placeholder="urn:knowledge:ontology:enterprise"
            />
          </NFormItem>
          <NFormItem :label="t('common.labelZh')" path="labelZh">
            <NInput v-model:value="formData.labelZh" />
          </NFormItem>
          <NFormItem :label="t('common.labelEn')" path="labelEn">
            <NInput v-model:value="formData.labelEn" />
          </NFormItem>
          <NFormItem :label="t('common.definitionZh')" path="definitionZh">
            <NInput
              v-model:value="formData.definitionZh"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
            />
          </NFormItem>
          <NFormItem :label="t('common.definitionEn')" path="definitionEn">
            <NInput
              v-model:value="formData.definitionEn"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
            />
          </NFormItem>
        </NForm>
        <p v-if="mode === 'create'" class="create-hint">{{ t('ontology.createHint') }}</p>
        <template #footer>
          <div class="drawer-actions">
            <NButton :disabled="creating" @click="showCreate = false">
              {{ t('common.cancel') }}
            </NButton>
            <NButton type="primary" :loading="creating" @click="handleSubmit">
              {{ t('common.save') }}
            </NButton>
          </div>
        </template>
      </NDrawerContent>
    </NDrawer>
  </section>
</template>

<style scoped>
.page {
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
  padding: var(--space-2) var(--space-3);
  background: var(--bg-surface);
  border-radius: var(--r-lg);
  box-shadow: var(--elev-1);
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
