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

import type { DomainBrief } from '@/api/domains'
import { domainsApi } from '@/api/domains'
import type { EntityTypeBrief, EntityTypeStats, ResourceStatus } from '@/api/entity-types'
import { entityTypesApi } from '@/api/entity-types'
import type { Namespace } from '@/api/namespaces'
import { namespacesApi } from '@/api/namespaces'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'

import NamespaceCreateModal from './components/NamespaceCreateModal.vue'

const { t, locale } = useI18n()
const { toMessage } = useApiError()
const router = useRouter()

const loading = ref(false)
const items = ref<EntityTypeBrief[]>([])
const searchQuery = ref('')
const showCreate = ref(false)
const namespaces = ref<Namespace[]>([])
const domains = ref<DomainBrief[]>([])
const creating = ref(false)
const createError = ref('')
const stats = ref<EntityTypeStats | null>(null)

/** 空串表示「全部」。统计条本身即筛选入口，不额外占一行控件。 */
const statusFilter = ref<ResourceStatus | ''>('')
/** 第四张卡：只看最近一次资产层校验里判为违反的类型。 */
const violationOnly = ref(false)
const domainFilter = ref<number | null>(null)
const view = ref<'table' | 'card'>('table')

/** 统计条点击即筛选：三个状态卡与「校验违反」互斥，统一在这里收口。 */
function selectAllStatuses() {
  statusFilter.value = ''
  violationOnly.value = false
}

function selectStatus(status: ResourceStatus) {
  violationOnly.value = false
  statusFilter.value = statusFilter.value === status ? '' : status
}

function toggleViolationOnly() {
  statusFilter.value = ''
  violationOnly.value = !violationOnly.value
}

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

const filtered = computed(() =>
  items.value.filter((row) => {
    if (statusFilter.value && row.status !== statusFilter.value) return false
    if (violationOnly.value && !row.has_violation) return false
    return true
  }),
)

const domainOptions = computed(() =>
  domains.value.map((domain) => ({
    label: domain.label_i18n?.[locale.value] ?? domain.label_i18n?.['zh-CN'] ?? domain.name,
    value: domain.id,
  })),
)

/** 列表只到分钟；跨天数据看的是「最近改过没有」，不需要秒。 */
function formatUpdated(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const columns = computed<DataTableColumns<EntityTypeBrief>>(() => [
  {
    title: t('common.displayName'),
    key: 'name',
    // 固定列宽合计 + 这两列的 minWidth 就是 scroll-x：窗口变窄时表格在容器内
    // 横向滚动，而不是把「名称」列压到只剩几十像素、逐字换行。
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
    title: t('entityType.propCount'),
    key: 'data_prop_count',
    width: 80,
    render: (row) => h('span', { class: 'mono count' }, String(row.data_prop_count ?? 0)),
  },
  {
    title: t('entityType.relationCount'),
    key: 'relation_count',
    width: 80,
    render: (row) => h('span', { class: 'mono count' }, String(row.relation_count ?? 0)),
  },
  {
    title: t('common.status'),
    key: 'status',
    width: 150,
    render: (row) =>
      h('div', { class: 'status-cell' }, [
        renderStatus(row.status),
        // 状态与校验是两个维度：状态照常显示，违反另起一个徽标
        row.has_violation
          ? h('span', { class: 'status-tag', style: { '--dot': 'var(--s-violation)' } }, [
              h('i', { class: 'status-dot' }),
              t('entityType.violation'),
            ])
          : null,
      ]),
  },
  {
    title: t('common.revision'),
    key: 'current_revision',
    width: 90,
    render: (row) => h('span', { class: 'mono rev' }, `v${row.current_revision}`),
  },
  {
    title: t('entityType.updatedAt'),
    key: 'updated_at',
    width: 110,
    render: (row) => h('span', { class: 'mono rev' }, formatUpdated(row.updated_at)),
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
const showNamespaceCreate = ref(false)

/** 就地登记的命名空间直接选中，空库也能在一个抽屉里完成第一个类型的创建。 */
function onNamespaceCreated(ns: Namespace) {
  namespaces.value = [...namespaces.value, ns]
  formData.value.namespace_id = ns.id
  // 程序赋值不会触发字段校验；只重校这一项，清掉此前残留的「必填」提示。
  void formRef.value?.validate(undefined, ['namespace_id']).catch(() => undefined)
}

function goToDetail(id: number) {
  void router.push({ name: 'entity-detail', params: { id } })
}

async function loadList() {
  loading.value = true
  try {
    items.value = await entityTypesApi.list({
      q: searchQuery.value,
      domain_id: domainFilter.value ?? undefined,
    })
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

/** 统计条走库级统计接口，不能拿当前页去数（分页后会失真）。 */
async function loadStats() {
  try {
    stats.value = await entityTypesApi.stats()
  } catch {
    stats.value = null
  }
}

async function loadDomains() {
  try {
    domains.value = await domainsApi.list()
  } catch {
    domains.value = []
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
    createError.value = toMessage(err)
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
  await Promise.all([loadList(), loadStats(), loadNamespaces(), loadDomains()])
})

watch(domainFilter, () => void loadList())
</script>

<template>
  <section class="page">
    <PageHeader :title="t('page.entityTypes')" :description="t('entityType.description')">
      <template #actions>
        <NButton type="primary" @click="showCreate = true">{{ t('common.create') }}</NButton>
      </template>
    </PageHeader>

    <!-- 统计条：本身就是筛选入口，点击即过滤。数值取库级统计，不受分页影响 -->
    <div class="stats">
      <button
        type="button"
        class="stat"
        :class="{ active: statusFilter === '' && !violationOnly }"
        @click="selectAllStatuses"
      >
        <span class="stat-value mono">{{ stats?.total ?? 0 }}</span>
        <span class="stat-label">{{ t('entityType.total') }}</span>
      </button>
      <button
        v-for="s in ['PUBLISHED', 'DRAFT'] as ResourceStatus[]"
        :key="s"
        type="button"
        class="stat"
        :class="{ active: statusFilter === s && !violationOnly }"
        @click="selectStatus(s)"
      >
        <span
          class="stat-value mono"
          :style="{ color: statusFilter === s ? STATUS_VAR[s] : undefined }"
        >
          {{ s === 'PUBLISHED' ? (stats?.published ?? 0) : (stats?.draft ?? 0) }}
        </span>
        <span class="stat-label">
          {{ s === 'DRAFT' ? t('entityType.draftUnpublished') : t(`resourceStatus.${s}`) }}
        </span>
      </button>
      <!-- 第四项按设计稿是「校验违反」：取最近一次资产层校验报告的结果 -->
      <button
        type="button"
        class="stat"
        :class="{ active: violationOnly }"
        @click="toggleViolationOnly"
      >
        <span
          class="stat-value mono"
          :style="{ color: stats?.violation ? 'var(--s-violation)' : undefined }"
        >
          {{ stats?.violation ?? 0 }}
        </span>
        <span class="stat-label">{{ t('entityType.violation') }}</span>
      </button>
    </div>

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
      <NFormItem
        :label="t('page.domains')"
        label-placement="left"
        :label-width="72"
        :show-feedback="false"
      >
        <NSelect
          v-model:value="domainFilter"
          :options="domainOptions"
          clearable
          :placeholder="t('entityType.allDomains')"
          class="domain-filter"
        />
      </NFormItem>
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
          :scroll-x="1150"
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
            <div class="ns-field">
              <NSelect v-model:value="formData.namespace_id" :options="nsOptions" />
              <NButton @click="showNamespaceCreate = true">{{
                t('namespace.createShort')
              }}</NButton>
            </div>
          </NFormItem>
          <NAlert v-if="!namespaces.length" type="info" class="ns-hint">
            {{ t('namespace.emptyHint') }}
          </NAlert>
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
    <NamespaceCreateModal v-model:show="showNamespaceCreate" @created="onNamespaceCreated" />
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
  /*
   * 用 1px 实描边而不是 --glow。--glow 带 14px 扩散光晕，那是图谱节点/画布
   * 的「星图」语义色，用在卡片上会向外晕开、压到上方页面说明文字上。
   */
  box-shadow: 0 0 0 1px var(--accent);
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

.search-field {
  min-width: 0;
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

:deep(.count) {
  color: var(--text-secondary);
  font-size: 12px;
}

/* 状态列可能同时放「状态」与「校验违反」两个徽标 */
:deep(.status-cell) {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.domain-filter {
  width: 200px;
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
.ns-field {
  display: flex;
  gap: var(--space-2);
  width: 100%;
}

.ns-hint {
  margin-bottom: var(--space-3);
}

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
