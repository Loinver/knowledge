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
  NSelect,
  NSpin,
} from 'naive-ui'
import { computed, h, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import type { EntityTypeBrief, ResourceStatus } from '@/api/entity-types'
import { entityTypesApi } from '@/api/entity-types'
import type { Namespace } from '@/api/namespaces'
import { namespacesApi } from '@/api/namespaces'
import PageHeader from '@/components/PageHeader.vue'

const { t, locale } = useI18n()
const router = useRouter()

const loading = ref(false)
const items = ref<EntityTypeBrief[]>([])
const searchQuery = ref('')
const showCreate = ref(false)
const namespaces = ref<Namespace[]>([])
const creating = ref(false)
const createError = ref('')

/** 空串表示「全部」。统计条本身即筛选入口，不额外占一行控件。 */
const statusFilter = ref<ResourceStatus | ''>('')
const view = ref<'table' | 'card'>('table')

const STATUS_ORDER: ResourceStatus[] = ['PUBLISHED', 'DRAFT', 'ARCHIVED']

/** 状态色取自设计令牌，与校验四态同一套语义（已发布=pass / 草稿=notrun / 归档=na）。 */
const STATUS_VAR: Record<ResourceStatus, string> = {
  PUBLISHED: 'var(--s-pass)',
  DRAFT: 'var(--s-notrun)',
  ARCHIVED: 'var(--s-na)',
}

function displayLabel(row: EntityTypeBrief): string {
  const labels = row.label_i18n ?? {}
  return labels[locale.value] ?? labels['zh-CN'] ?? row.name
}

const counts = computed(() => {
  const base: Record<string, number> = { '': items.value.length }
  for (const s of STATUS_ORDER) base[s] = 0
  for (const row of items.value) base[row.status] = (base[row.status] ?? 0) + 1
  return base
})

const filtered = computed(() =>
  statusFilter.value ? items.value.filter((row) => row.status === statusFilter.value) : items.value,
)

const columns = computed<DataTableColumns<EntityTypeBrief>>(() => [
  {
    title: t('common.displayName'),
    key: 'name',
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
    render: (row) => h('span', { class: 'iri' }, row.iri),
  },
  {
    title: t('common.status'),
    key: 'status',
    width: 120,
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
    width: 100,
    render: (row) =>
      h(
        NButton,
        { size: 'small', quaternary: true, onClick: () => goToDetail(row.id) },
        { default: () => t('common.edit') },
      ),
  },
])

function renderStatus(status: ResourceStatus) {
  return h('span', { class: 'status-tag', style: { '--dot': STATUS_VAR[status] } }, [
    h('i', { class: 'status-dot' }),
    t(`resourceStatus.${status}`),
  ])
}

const formData = ref({ name: '', namespace_id: null as number | null, labelZh: '', labelEn: '' })
const formRef = ref<FormInst | null>(null)

/**
 * 字段级校验：错误贴着字段显示，blur 即校验，校验不通过不发请求。
 * 机读名沿用后端的 PascalCase 约定（与属性编辑器同一套规则）。
 */
const rules = computed<FormRules>(() => ({
  name: [
    { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
    {
      pattern: /^[A-Z][A-Za-z0-9]*$/,
      message: t('entityType.namePattern'),
      trigger: ['blur', 'input'],
    },
  ],
  namespace_id: {
    required: true,
    type: 'number',
    message: t('common.required'),
    trigger: ['blur', 'change'],
  },
  labelZh: { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
}))

const nsOptions = computed(() => namespaces.value.map((ns) => ({ label: ns.prefix, value: ns.id })))

function goToDetail(id: number) {
  void router.push({ name: 'entity-detail', params: { id } })
}

async function loadList() {
  loading.value = true
  try {
    items.value = await entityTypesApi.list({ q: searchQuery.value })
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

async function loadNamespaces() {
  try {
    namespaces.value = await namespacesApi.list()
  } catch {
    namespaces.value = []
  }
}

async function handleCreate() {
  createError.value = ''
  try {
    await formRef.value?.validate()
  } catch {
    // 校验失败时 naive 已在字段下方给出提示，不再补一条汇总文案
    return
  }
  creating.value = true
  try {
    await entityTypesApi.create({
      name: formData.value.name,
      namespace_id: formData.value.namespace_id as number,
      label_i18n: {
        'zh-CN': formData.value.labelZh,
        'en-US': formData.value.labelEn || formData.value.name,
      },
    })
    showCreate.value = false
    formData.value = { name: '', namespace_id: null, labelZh: '', labelEn: '' }
    formRef.value?.restoreValidation()
    await loadList()
  } catch (err) {
    createError.value = (err as { code?: string }).code || t('common.save')
  } finally {
    creating.value = false
  }
}

/** 打开抽屉即重置表单与校验态，避免上一轮的报错残留到下一次新建。 */
watch(showCreate, (open) => {
  if (!open) return
  formData.value = { name: '', namespace_id: null, labelZh: '', labelEn: '' }
  createError.value = ''
  formRef.value?.restoreValidation()
})

onMounted(async () => {
  await Promise.all([loadList(), loadNamespaces()])
})
</script>

<template>
  <section class="page">
    <PageHeader :title="t('page.entityTypes')" :description="t('entityType.description')">
      <template #actions>
        <NButton type="primary" @click="showCreate = true">{{ t('common.create') }}</NButton>
      </template>
    </PageHeader>

    <!-- 统计条：本身就是筛选入口，点击即过滤 -->
    <div class="stats">
      <button
        type="button"
        class="stat"
        :class="{ active: statusFilter === '' }"
        @click="statusFilter = ''"
      >
        <span class="stat-value mono">{{ counts[''] ?? 0 }}</span>
        <span class="stat-label">{{ t('entityType.total') }}</span>
      </button>
      <button
        v-for="s in STATUS_ORDER"
        :key="s"
        type="button"
        class="stat"
        :class="{ active: statusFilter === s }"
        @click="statusFilter = statusFilter === s ? '' : s"
      >
        <span class="stat-value mono" :style="{ color: counts[s] ? STATUS_VAR[s] : undefined }">
          {{ counts[s] ?? 0 }}
        </span>
        <span class="stat-label">{{ t(`resourceStatus.${s}`) }}</span>
      </button>
    </div>

    <div class="toolbar">
      <NInput
        v-model:value="searchQuery"
        :placeholder="t('common.search')"
        clearable
        class="search"
        @keyup.enter="loadList"
        @clear="loadList"
      />
      <span class="spacer" />
      <div class="seg" role="group" :aria-label="t('common.viewMode')">
        <button type="button" :class="{ on: view === 'table' }" @click="view = 'table'">
          {{ t('common.viewTable') }}
        </button>
        <button type="button" :class="{ on: view === 'card' }" @click="view = 'card'">
          {{ t('common.viewCard') }}
        </button>
      </div>
    </div>

    <NSpin :show="loading">
      <div v-if="view === 'table'" class="card">
        <NDataTable
          :columns="columns"
          :data="filtered"
          :bordered="false"
          :pagination="{ pageSize: 20 }"
          :row-key="(row: EntityTypeBrief) => row.id"
        >
          <template #empty>
            <NEmpty :description="t('common.empty')" />
          </template>
        </NDataTable>
      </div>

      <!-- 卡片视图：同一份数据换一种扫读方式，IRI 仍然可见 -->
      <div v-else-if="filtered.length" class="cards">
        <button
          v-for="row in filtered"
          :key="row.id"
          type="button"
          class="type-card"
          @click="goToDetail(row.id)"
        >
          <span class="type-head">
            <i class="type-dot" :style="{ background: STATUS_VAR[row.status] }" />
            <span class="cell-primary">{{ displayLabel(row) }}</span>
            <span class="mono rev">{{ `v${row.current_revision}` }}</span>
          </span>
          <span class="cell-sub mono">{{ row.name }}</span>
          <!-- IRI 在窄卡片里会被截断，用 title 保留完整值可悬停查看 -->
          <span class="iri type-iri" :title="row.iri">{{ row.iri }}</span>
          <span class="status-tag" :style="{ '--dot': STATUS_VAR[row.status] }">
            <i class="status-dot" />
            {{ t(`resourceStatus.${row.status}`) }}
          </span>
        </button>
      </div>

      <div v-else class="card empty-card">
        <NEmpty :description="t('common.empty')" />
      </div>
    </NSpin>

    <NDrawer v-model:show="showCreate" :width="460">
      <NDrawerContent :title="t('entityType.create')" closable>
        <NForm ref="formRef" :model="formData" :rules="rules" label-placement="top">
          <NFormItem :label="t('common.name')" path="name">
            <NInput v-model:value="formData.name" placeholder="Employee" />
            <template #feedback>{{ t('entityType.nameHint') }}</template>
          </NFormItem>
          <NFormItem :label="t('common.namespace')" path="namespace_id">
            <NSelect v-model:value="formData.namespace_id" :options="nsOptions" />
          </NFormItem>
          <NFormItem :label="t('common.labelZh')" path="labelZh">
            <NInput v-model:value="formData.labelZh" />
          </NFormItem>
          <NFormItem :label="t('common.labelEn')" path="labelEn">
            <NInput v-model:value="formData.labelEn" />
          </NFormItem>
        </NForm>
        <NAlert v-if="createError" type="error" class="create-error">{{ createError }}</NAlert>
        <template #footer>
          <div class="drawer-actions">
            <NButton @click="showCreate = false">{{ t('common.cancel') }}</NButton>
            <NButton type="primary" :loading="creating" @click="handleCreate">
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

/* ── 统计条 ─────────────────────────────────────────────── */
.stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 11px 14px;
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  background: var(--bg-surface);
  border: 0;
  border-radius: var(--r-md);
  box-shadow: var(--elev-1);
  transition:
    box-shadow var(--dur-base) var(--ease-out),
    background-color var(--dur-base) var(--ease-out);
}

.stat:hover {
  box-shadow: var(--elev-2);
}

.stat.active {
  background: var(--accent-soft);
  box-shadow: var(--glow);
}

.stat-value {
  font-size: 20px;
  font-weight: 500;
  line-height: 1.25;
}

.stat-label {
  color: var(--text-tertiary);
  font-size: var(--font-caption);
}

/* ── 工具条 ─────────────────────────────────────────────── */
.toolbar {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  margin-bottom: var(--space-3);
}

.search {
  max-width: 280px;
}

.spacer {
  flex: 1;
}

.seg {
  display: flex;
  gap: 2px;
  padding: 2px;
  background: var(--bg-inset);
  border-radius: var(--r-md);
  box-shadow: 0 0 0 1px var(--border-subtle);
}

.seg button {
  padding: 3px 11px;
  font: inherit;
  font-size: 11px;
  color: var(--text-tertiary);
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: 6px;
}

.seg button.on {
  color: var(--text);
  background: var(--bg-active);
}

/* ── 容器 ───────────────────────────────────────────────── */
.card {
  padding: var(--space-2) var(--space-3);
  background: var(--bg-surface);
  border-radius: var(--r-lg);
  box-shadow: var(--elev-1);
}

.empty-card {
  padding: var(--space-6);
}

/* 表格内的单元格样式（NDataTable 的 render 里用 class，必须非 scoped 才生效，见下方 :deep） */
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

/* ── 卡片视图 ───────────────────────────────────────────── */
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(232px, 1fr));
  gap: var(--space-3);
}

.type-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
  padding: var(--space-3) var(--space-4);
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  background: var(--bg-surface);
  border: 0;
  border-radius: var(--r-lg);
  box-shadow: var(--elev-1);
  transition:
    box-shadow var(--dur-base) var(--ease-out),
    transform var(--dur-base) var(--ease-out);
}

.type-card:hover {
  box-shadow: var(--glow);
  transform: translateY(-1px);
}

.type-head {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 100%;
}

.type-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.type-head .rev {
  margin-left: auto;
}

.type-iri {
  max-width: 100%;
}

/* ── 抽屉 ───────────────────────────────────────────────── */
.create-error {
  margin-bottom: var(--space-3);
}

.drawer-actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
}

@media (max-width: 720px) {
  .stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
