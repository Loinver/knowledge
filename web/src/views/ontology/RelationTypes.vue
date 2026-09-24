<script setup lang="ts">
import type { DataTableColumns, FormInst, FormRules } from 'naive-ui'
import {
  NAlert,
  NButton,
  NCheckbox,
  NDataTable,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NSelect,
  NSpace,
  NSpin,
} from 'naive-ui'
import { computed, h, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { EntityTypeBrief, ResourceStatus } from '@/api/entity-types'
import { entityTypesApi } from '@/api/entity-types'
import type { Namespace } from '@/api/namespaces'
import { namespacesApi } from '@/api/namespaces'
import type { RelationTypeBrief, RelationTypeDetail } from '@/api/relations'
import { relationsApi } from '@/api/relations'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'

const { t, locale } = useI18n()
const { toMessage } = useApiError()

const loading = ref(false)
const detailsLoading = ref(false)
const items = ref<RelationTypeBrief[]>([])
const details = ref<Record<number, RelationTypeDetail>>({})
const namespaces = ref<Namespace[]>([])
const typeList = ref<EntityTypeBrief[]>([])
const showCreate = ref(false)
const showEdit = ref(false)
const creating = ref(false)
const editing = ref(false)
const createError = ref('')
const editError = ref('')
const actionError = ref('')
const publishingId = ref<number | null>(null)
const editingDetail = ref<RelationTypeDetail | null>(null)
const statusFilter = ref<ResourceStatus | ''>('')
const view = ref<'table' | 'card'>('table')

const STATUS_ORDER: ResourceStatus[] = ['PUBLISHED', 'DRAFT', 'ARCHIVED']
const STATUS_VAR: Record<ResourceStatus, string> = {
  PUBLISHED: 'var(--s-pass)',
  DRAFT: 'var(--s-notrun)',
  ARCHIVED: 'var(--s-na)',
}
/** 卡片视图最多补多少条详情，避免列表很长时打出一串请求。 */
const DETAIL_CAP = 40

function pickLabel(labels: Record<string, string> | null | undefined, fallback: string): string {
  return labels?.[locale.value] ?? labels?.['zh-CN'] ?? fallback
}

const typeNameById = computed(() => {
  const map: Record<number, string> = {}
  for (const tp of typeList.value) map[tp.id] = pickLabel(tp.label_i18n, tp.name)
  return map
})

/** 图上节点放不下长名字，截断到 5 个字并补省略号。 */
function shortLabel(text: string): string {
  return text.length > 5 ? `${text.slice(0, 5)}…` : text
}

/**
 * max = -1 表示无上界，按惯例显示成 N。
 *
 * 参数只取 min/max：详情接口返回的基数还带 `role_label_i18n`（可能为 null），
 * 结构上比本地 `CardinalitySpec` 更宽，直接声明最小需求即可，不必跟着放宽本地类型。
 */
function cardinalityText(spec?: { min: number; max: number }): string {
  if (!spec) return '—'
  return `${spec.min} : ${spec.max === -1 ? 'N' : spec.max}`
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

const columns = computed<DataTableColumns<RelationTypeBrief>>(() => [
  {
    title: t('common.displayName'),
    key: 'name',
    // 固定列宽合计 + 这两列的 minWidth = scroll-x。窗口变窄时表格在容器内
    // 横向滚动，而不是把「名称」列压到几十像素逐字换行、末列被切掉。
    minWidth: 180,
    render(row) {
      const label = pickLabel(row.label_i18n, row.name)
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
    title: t('relation.owl'),
    key: 'owl',
    width: 190,
    render: (row) => {
      const detail = details.value[row.id]
      const tags = detail ? owlTags(detail) : []
      if (!detail) return h('span', { class: 'muted' }, '—')
      if (!tags.length) return h('span', { class: 'muted' }, '—')
      return h(
        'div',
        { class: 'tag-row' },
        tags.map((key) => h('span', { class: 'mini-tag' }, t(`relation.${key}`))),
      )
    },
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
    width: 86,
    render: (row) => h('span', { class: 'mono rev' }, `v${row.current_revision}`),
  },
  {
    title: t('common.actions'),
    key: 'actions',
    width: 168,
    render: (row) =>
      h(NSpace, { size: 4, wrap: false }, () => [
        h(
          NButton,
          { size: 'small', quaternary: true, onClick: () => void openEdit(row.id) },
          { default: () => t('common.edit') },
        ),
        // 草稿才能发布：发布即冻结，之后不可再改。已发布的没有「重新发布」语义。
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
      ]),
  },
])

function owlTags(detail: RelationTypeDetail): string[] {
  const out: string[] = []
  if (detail.owl?.functional) out.push('functional')
  if (detail.owl?.inverse_functional) out.push('inverseFunctional')
  if (detail.owl?.symmetric) out.push('symmetric')
  if (detail.owl?.transitive) out.push('transitive')
  return out
}

function renderStatus(status: ResourceStatus) {
  return h('span', { class: 'status-tag', style: { '--dot': STATUS_VAR[status] } }, [
    h('i', { class: 'status-dot' }),
    t(`resourceStatus.${status}`),
  ])
}

const formData = ref({
  name: '',
  namespace_id: null as number | null,
  labelZh: '',
  labelEn: '',
  domainType: null as number | null,
  rangeType: null as number | null,
  enableAttrs: false,
})

const nsOptions = computed(() => namespaces.value.map((ns) => ({ label: ns.prefix, value: ns.id })))
const typeOptions = computed(() =>
  typeList.value.map((tp) => ({ label: pickLabel(tp.label_i18n, tp.name), value: tp.id })),
)

const createFormRef = ref<FormInst | null>(null)
const editFormRef = ref<FormInst | null>(null)

/** 定义域与值域都是必选的实体类型引用；基数在创建时固定为 0:N，编辑不改。 */
const endpointRules: FormRules = {
  domainType: {
    required: true,
    type: 'number',
    message: t('common.required'),
    trigger: ['blur', 'change'],
  },
  rangeType: {
    required: true,
    type: 'number',
    message: t('common.required'),
    trigger: ['blur', 'change'],
  },
}

const createRules = computed<FormRules>(() => ({
  name: [
    { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
    {
      pattern: /^[A-Z][A-Za-z0-9]*$/,
      message: t('relation.namePattern'),
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
  ...endpointRules,
}))

const editRules = computed<FormRules>(() => ({
  labelZh: { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
  ...endpointRules,
}))

async function load() {
  loading.value = true
  try {
    items.value = await relationsApi.list()
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

/**
 * 列表接口只返回 brief（不含定义域/值域），卡片上的迷你图谱需要详情。
 * 按需补齐，已取过的进缓存，切回表格再切回来不会重复请求。
 */
async function loadDetails() {
  const missing = items.value
    .slice(0, DETAIL_CAP)
    .map((row) => row.id)
    .filter((id) => !details.value[id])
  if (!missing.length) return
  detailsLoading.value = true
  try {
    const results = await Promise.all(
      missing.map((id) =>
        relationsApi
          .get(id)
          .then((d) => d)
          .catch(() => null),
      ),
    )
    const next = { ...details.value }
    for (const d of results) if (d) next[d.id] = d
    details.value = next
  } finally {
    detailsLoading.value = false
  }
}

watch(view, (v) => {
  if (v === 'card') void loadDetails()
})

async function handleCreate() {
  createError.value = ''
  try {
    await createFormRef.value?.validate()
  } catch {
    return
  }
  const f = formData.value
  creating.value = true
  try {
    await relationsApi.create({
      name: f.name,
      namespace_id: f.namespace_id as number,
      label_i18n: { 'zh-CN': f.labelZh, 'en-US': f.labelEn || f.name },
      domain_spec: { type_id: f.domainType as number, cardinality: { min: 0, max: -1 } },
      range_spec: { type_id: f.rangeType as number, cardinality: { min: 0, max: -1 } },
      enable_attributes: f.enableAttrs,
    })
    showCreate.value = false
    formData.value = {
      name: '',
      namespace_id: null,
      labelZh: '',
      labelEn: '',
      domainType: null,
      rangeType: null,
      enableAttrs: false,
    }
    await load()
    await loadDetails()
  } catch (err) {
    createError.value = toMessage(err)
  } finally {
    creating.value = false
  }
}

async function openEdit(id: number) {
  editError.value = ''
  try {
    const detail = await relationsApi.get(id)
    editingDetail.value = detail
    formData.value = {
      name: detail.name,
      namespace_id: detail.namespace_id,
      labelZh: detail.label_i18n?.['zh-CN'] ?? detail.name,
      labelEn: detail.label_i18n?.['en-US'] ?? detail.name,
      domainType: detail.domain_spec.type_id,
      rangeType: detail.range_spec.type_id,
      enableAttrs: detail.enable_attributes,
    }
    showEdit.value = true
  } catch (err) {
    editError.value = (err as { code?: string }).code || t('relation.loadFailed')
  }
}

async function handleEdit() {
  const detail = editingDetail.value
  editError.value = ''
  try {
    await editFormRef.value?.validate()
  } catch {
    return
  }
  const f = formData.value
  if (!detail) return
  editing.value = true
  try {
    const updated = await relationsApi.update(detail.id, {
      label_i18n: { 'zh-CN': f.labelZh, 'en-US': f.labelEn || f.name },
      domain_spec: { ...detail.domain_spec, type_id: f.domainType as number },
      range_spec: { ...detail.range_spec, type_id: f.rangeType as number },
      enable_attributes: f.enableAttrs,
      owl: detail.owl,
      if_match: detail.current_revision,
      edit_revision: detail.edit_revision,
    })
    details.value = { ...details.value, [updated.id]: updated }
    showEdit.value = false
    await load()
  } catch (err) {
    editError.value = toMessage(err)
  } finally {
    editing.value = false
  }
}

/**
 * 发布关系类型：冻结当前草稿为不可变版本。
 *
 * 没有这一步，草稿态关系永远进不了本体装配——后端一直有 publish 接口，
 * 前端此前没有封装，等于把工作流断在列表页。
 */
async function publish(row: RelationTypeBrief) {
  if (publishingId.value !== null) return
  publishingId.value = row.id
  actionError.value = ''
  try {
    await relationsApi.publish(row.id)
    await load()
    await loadDetails()
  } catch (err) {
    actionError.value = toMessage(err)
  } finally {
    publishingId.value = null
  }
}

/** 打开抽屉即重置校验态，避免上一轮报错残留。 */
watch(showCreate, (open) => {
  if (!open) return
  createError.value = ''
  createFormRef.value?.restoreValidation()
})
watch(showEdit, (open) => {
  if (!open) return
  editError.value = ''
  editFormRef.value?.restoreValidation()
})

onMounted(async () => {
  await Promise.all([
    load(),
    namespacesApi
      .list()
      .then((r) => {
        namespaces.value = r
      })
      .catch(() => undefined),
    entityTypesApi
      .list()
      .then((r) => {
        typeList.value = r
      })
      .catch(() => undefined),
  ])
  await loadDetails()
})
</script>

<template>
  <section class="page">
    <PageHeader :title="t('page.relationTypes')" :description="t('relation.description')">
      <template #actions>
        <NButton type="primary" @click="showCreate = true">{{ t('common.create') }}</NButton>
      </template>
    </PageHeader>

    <NAlert v-if="actionError" type="error" role="alert" class="action-alert">{{
      actionError
    }}</NAlert>

    <div class="stats">
      <button
        type="button"
        class="stat"
        :class="{ active: statusFilter === '' }"
        @click="statusFilter = ''"
      >
        <span class="stat-value mono">{{ counts[''] ?? 0 }}</span>
        <span class="stat-label">{{ t('relation.total') }}</span>
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

    <NSpin :show="loading || detailsLoading">
      <div v-if="view === 'table'" class="card">
        <NDataTable
          :columns="columns"
          :data="filtered"
          :bordered="false"
          :pagination="{ pageSize: 20 }"
          :scroll-x="1040"
          :row-key="(row: RelationTypeBrief) => row.id"
        >
          <template #empty>
            <NEmpty :description="t('common.empty')" />
          </template>
        </NDataTable>
      </div>

      <!-- 卡片视图：每条关系用一张迷你图谱表达「定义域 → 值域」 -->
      <div v-else-if="filtered.length" class="cards">
        <article v-for="row in filtered" :key="row.id" class="rel-card">
          <header class="rel-head">
            <span class="cell-primary">{{ pickLabel(row.label_i18n, row.name) }}</span>
            <span class="cell-sub mono">{{ row.name }}</span>
            <span class="mono rev">{{ `v${row.current_revision}` }}</span>
          </header>

          <svg class="rel-graph" viewBox="0 0 268 64" fill="none" aria-hidden="true">
            <path
              d="M56 32H212"
              :stroke="row.status === 'PUBLISHED' ? 'var(--g-relation)' : 'var(--border-strong)'"
              stroke-width="1.5"
              :stroke-dasharray="row.status === 'PUBLISHED' ? undefined : '4 5'"
              marker-end="url(#rel-arrow)"
            />
            <text x="134" y="24" text-anchor="middle" class="graph-label">
              {{ shortLabel(pickLabel(row.label_i18n, row.name)) }}
            </text>

            <circle
              cx="34"
              cy="32"
              r="18"
              fill="var(--accent-soft)"
              :stroke="row.status === 'PUBLISHED' ? 'var(--g-entity)' : 'var(--border-strong)'"
              stroke-width="1"
            />
            <text x="34" y="36" text-anchor="middle" class="graph-node">
              {{ shortLabel(typeNameById[details[row.id]?.domain_spec?.type_id ?? -1] ?? '?') }}
            </text>

            <circle
              cx="234"
              cy="32"
              r="18"
              fill="var(--accent-soft)"
              :stroke="row.status === 'PUBLISHED' ? 'var(--g-entity)' : 'var(--border-strong)'"
              stroke-width="1"
            />
            <text x="234" y="36" text-anchor="middle" class="graph-node">
              {{ shortLabel(typeNameById[details[row.id]?.range_spec?.type_id ?? -1] ?? '?') }}
            </text>
          </svg>

          <footer class="rel-foot">
            <span class="mini-tag mono">{{
              cardinalityText(details[row.id]?.domain_spec?.cardinality)
            }}</span>
            <span
              v-if="row.enable_attributes"
              class="mini-tag"
              style="color: var(--g-derived); border-color: rgba(167, 139, 250, 0.35)"
            >
              {{ t('relation.assocEntity') }}
            </span>
            <span
              v-for="key in details[row.id] ? owlTags(details[row.id]) : []"
              :key="key"
              class="mini-tag"
            >
              {{ t(`relation.${key}`) }}
            </span>
            <span class="spacer" />
            <span class="status-tag" :style="{ '--dot': STATUS_VAR[row.status] }">
              <i class="status-dot" />
              {{ t(`resourceStatus.${row.status}`) }}
            </span>
          </footer>
        </article>
      </div>

      <div v-else class="card empty-card">
        <NEmpty :description="t('common.empty')" />
      </div>
    </NSpin>

    <!-- 迷你图谱的箭头只定义一次，供所有卡片共用 -->
    <svg width="0" height="0" aria-hidden="true" style="position: absolute">
      <defs>
        <marker
          id="rel-arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path
            d="M2 1L8 5L2 9"
            fill="none"
            stroke="var(--g-relation)"
            stroke-width="1.5"
            stroke-linecap="round"
          />
        </marker>
      </defs>
    </svg>

    <NDrawer v-model:show="showCreate" :width="520">
      <NDrawerContent :title="t('relation.create')" closable>
        <NForm
          ref="createFormRef"
          :model="formData"
          :rules="createRules"
          :disabled="creating"
          label-placement="top"
        >
          <NFormItem :label="t('common.name')" path="name">
            <NInput v-model:value="formData.name" placeholder="WorksIn" />
            <template #feedback>{{ t('relation.nameHint') }}</template>
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
          <NFormItem :label="t('relation.domain')" path="domainType">
            <NSelect v-model:value="formData.domainType" :options="typeOptions" filterable />
          </NFormItem>
          <NFormItem :label="t('relation.range')" path="rangeType">
            <NSelect v-model:value="formData.rangeType" :options="typeOptions" filterable />
          </NFormItem>
          <NFormItem :label="t('relation.enableAttributes')" path="enableAttrs">
            <NCheckbox v-model:checked="formData.enableAttrs" />
          </NFormItem>
        </NForm>
        <NAlert v-if="createError" type="error" class="create-error">{{ createError }}</NAlert>
        <template #footer>
          <div class="drawer-actions">
            <NButton :disabled="creating" @click="showCreate = false">
              {{ t('common.cancel') }}
            </NButton>
            <NButton type="primary" :loading="creating" @click="handleCreate">
              {{ t('common.save') }}
            </NButton>
          </div>
        </template>
      </NDrawerContent>
    </NDrawer>

    <NDrawer v-model:show="showEdit" :width="520">
      <NDrawerContent :title="t('relation.edit')" closable>
        <NForm
          ref="editFormRef"
          :model="formData"
          :rules="editRules"
          :disabled="editing"
          label-placement="top"
        >
          <NFormItem :label="t('common.name')">
            <NInput v-model:value="formData.name" disabled />
            <template #feedback>{{ t('entityType.nameImmutable') }}</template>
          </NFormItem>
          <NFormItem :label="t('common.labelZh')" path="labelZh">
            <NInput v-model:value="formData.labelZh" />
          </NFormItem>
          <NFormItem :label="t('common.labelEn')" path="labelEn">
            <NInput v-model:value="formData.labelEn" />
          </NFormItem>
          <NFormItem :label="t('relation.domain')" path="domainType">
            <NSelect v-model:value="formData.domainType" :options="typeOptions" filterable />
          </NFormItem>
          <NFormItem :label="t('relation.range')" path="rangeType">
            <NSelect v-model:value="formData.rangeType" :options="typeOptions" filterable />
          </NFormItem>
        </NForm>
        <NAlert v-if="editError" type="error" class="create-error">{{ editError }}</NAlert>
        <template #footer>
          <div class="drawer-actions">
            <NButton :disabled="editing" @click="showEdit = false">
              {{ t('common.cancel') }}
            </NButton>
            <NButton type="primary" :loading="editing" @click="handleEdit">
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

.toolbar {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  margin-bottom: var(--space-3);
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

.card {
  padding: var(--space-2) var(--space-3);
  background: var(--bg-surface);
  border-radius: var(--r-lg);
  box-shadow: var(--elev-1);
}

.empty-card {
  padding: var(--space-6);
}

/* ── 卡片视图 ───────────────────────────────────────────── */
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(288px, 1fr));
  gap: var(--space-3);
}

.rel-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: var(--space-3) var(--space-4) var(--space-4);
  background: var(--bg-surface);
  border-radius: var(--r-lg);
  box-shadow: var(--elev-1);
}

.rel-head {
  display: flex;
  gap: 8px;
  align-items: baseline;
}

.rel-head .rev {
  margin-left: auto;
}

.rel-graph {
  width: 100%;
  height: auto;
}

.rel-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  align-items: center;
}

/* ── 共享单元（表格 render 与卡片模板共用，需 :deep 才覆盖到 render 出来的节点） */
:deep(.cell-name) {
  display: flex;
  gap: 8px;
  align-items: baseline;
}

:deep(.cell-primary),
.cell-primary {
  font-weight: 500;
}

:deep(.cell-sub),
.cell-sub {
  color: var(--text-tertiary);
  font-size: 11px;
}

:deep(.rev),
.rev {
  color: var(--text-tertiary);
  font-size: 11px;
}

:deep(.muted) {
  color: var(--text-disabled);
}

:deep(.status-tag),
.status-tag {
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

:deep(.status-dot),
.status-dot {
  width: 6px;
  height: 6px;
  background: var(--dot);
  border-radius: 50%;
}

:deep(.mini-tag),
.mini-tag {
  padding: 1px 8px;
  font-size: 10px;
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-pill);
}

:deep(.tag-row) {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.graph-label {
  font-size: 10px;
  fill: var(--g-relation);
}

.graph-node {
  font-size: 10px;
  fill: var(--text-secondary);
}

.create-error {
  margin-bottom: var(--space-3);
}

.action-alert {
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
