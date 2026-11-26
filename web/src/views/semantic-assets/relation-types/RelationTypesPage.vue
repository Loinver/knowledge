<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import type { DomainBrief } from '@/api/domains'
import { domainsApi } from '@/api/domains'
import type { EntityTypeBrief, ResourceStatus } from '@/api/entity-types'
import { entityTypesApi } from '@/api/entity-types'
import type { Namespace } from '@/api/namespaces'
import { namespacesApi } from '@/api/namespaces'
import type {
  RelationTypeBrief,
  RelationTypeCreate,
  RelationTypeDetail,
  RelationTypeUpdate,
} from '@/api/relations'
import { relationsApi } from '@/api/relations'
import SearchPanel from '@/components/business/SearchPanel.vue'
import SearchTable from '@/components/business/SearchTable.vue'
import PageHeader from '@/components/PageHeader.vue'
import type { DataTableColumns, FormInst, FormRule, FormRules } from '@/components/ui'
import {
  FormContainer,
  FormField,
  UiAlert,
  UiButton,
  UiCheckbox,
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

import AssetDomainFilter from '../components/AssetDomainFilter.vue'
import AssetInspector from '../components/AssetInspector.vue'
import NamespaceCreateModal from '../components/NamespaceCreateModal.vue'
import RelationSemanticFields from './components/RelationSemanticFields.vue'

const auth = useAuthStore()
const canWrite = computed(() => ['ADMIN', 'EDITOR'].includes(auth.user?.role ?? ''))
const { t, locale } = useI18n()
const { toMessage } = useApiError()
const router = useRouter()
const route = useRoute()

const loading = ref(false)
const detailsLoading = ref(false)
const items = ref<RelationTypeBrief[]>([])
const details = ref<Record<number, RelationTypeDetail>>({})
const namespaces = ref<Namespace[]>([])
const typeList = ref<EntityTypeBrief[]>([])
const inverseRelations = ref<RelationTypeBrief[]>([])
const referencesLoading = ref(false)
const referencesError = ref('')
let referenceGeneration = 0
const showCreate = ref(false)
const showEdit = ref(false)
const creating = ref(false)
const createValidating = ref(false)
let createGeneration = 0
let alive = true
const editing = ref(false)
const editValidating = ref(false)
const createError = ref('')
const editError = ref('')
const actionError = ref('')
const loadError = ref('')
const publishingId = ref<number | null>(null)
const removingId = ref<number | null>(null)
const notice = ref('')
const editingDetail = ref<RelationTypeDetail | null>(null)
type RelationEditSession = {
  id: number
  generation: number
  controller: AbortController
}
let editGeneration = 0
let editSession: RelationEditSession | null = null
const statusFilter = ref<ResourceStatus | ''>(
  ['DRAFT', 'PUBLISHED', 'ARCHIVED'].includes(String(route.query.status))
    ? (route.query.status as ResourceStatus)
    : '',
)
const domains = ref<DomainBrief[]>([])
const domainsError = ref('')
const domainsLoading = ref(false)
const domainFilter = ref<number | null>(Number(route.query.domain) || null)
const domainMembers = ref<number[] | null>(null)
const domainMembersLoading = ref(false)
const domainMembersError = ref('')
const previewDetail = ref<RelationTypeDetail | null>(null)
const previewLoading = ref(false)
const previewError = ref('')
let domainController: AbortController | undefined
let previewController: AbortController | undefined
const page = ref(Math.max(1, Number(route.query.page) || 1))
const pageSize = ref(20)
const view = ref<'table' | 'card'>(route.query.view === 'card' ? 'card' : 'table')
/** 列表搜索词。后端 /relations 支持 q（按机读名过滤），此前页面没接。 */
const searchQuery = ref(String(route.query.q ?? ''))
watch(
  [searchQuery, statusFilter, view, page, domainFilter],
  () =>
    void router.replace({
      query: {
        ...route.query,
        q: searchQuery.value || undefined,
        status: statusFilter.value || undefined,
        domain: domainFilter.value || undefined,
        view: view.value,
        page: page.value > 1 ? page.value : undefined,
      },
    }),
)

watch([searchQuery, statusFilter, domainFilter], () => {
  page.value = 1
})

const STATUS_ORDER: ResourceStatus[] = ['PUBLISHED', 'DRAFT', 'ARCHIVED']
const STATUS_VAR: Record<ResourceStatus, string> = {
  PUBLISHED: 'var(--s-pass)',
  DRAFT: 'var(--s-notrun)',
  ARCHIVED: 'var(--s-na)',
}
/** 卡片视图最多补多少条详情，避免列表很长时打出一串请求。 */
const DETAIL_CAP = 40
let listGeneration = 0
let detailGeneration = 0
onBeforeUnmount(() => {
  domainController?.abort()
  previewController?.abort()
  alive = false
  createGeneration++
  listGeneration++
  detailGeneration++
  referenceGeneration++
  invalidateEditSession()
})

function invalidateEditSession() {
  editGeneration++
  editSession?.controller.abort()
  editSession = null
  editingDetail.value = null
  editing.value = false
  editValidating.value = false
}

function isCurrentEdit(session: RelationEditSession) {
  return (
    editSession === session &&
    session.generation === editGeneration &&
    !session.controller.signal.aborted &&
    showEdit.value &&
    editingDetail.value?.id === session.id
  )
}

function pickLabel(labels: Record<string, string> | null | undefined, _fallback: string): string {
  return labels?.[locale.value]?.trim() || t('enumDictionaries.untranslated')
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
  items.value.filter(
    (row) =>
      (!statusFilter.value || row.status === statusFilter.value) &&
      (domainFilter.value === null || (domainMembers.value?.includes(row.id) ?? false)),
  ),
)
const selected = computed(() =>
  filtered.value.find((row) => row.id === Number(route.query.preview)),
)
function preview(id: number | null) {
  void router.replace({ query: { ...route.query, preview: id ?? undefined } })
}
async function loadDomains() {
  domainsLoading.value = true
  domainsError.value = ''
  try {
    const next = await domainsApi.list()
    if (alive) domains.value = next
  } catch (error) {
    if (alive) domainsError.value = toMessage(error)
  } finally {
    if (alive) domainsLoading.value = false
  }
}
async function loadDomainMembers() {
  domainController?.abort()
  domainMembers.value = null
  domainMembersError.value = ''
  domainMembersLoading.value = false
  if (domainFilter.value === null) return
  const controller = new AbortController()
  domainController = controller
  domainMembersLoading.value = true
  try {
    const members = await domainsApi.members(domainFilter.value, controller.signal)
    if (!controller.signal.aborted)
      domainMembers.value = members.map((member) => member.resource_id)
  } catch (error) {
    if (!controller.signal.aborted) domainMembersError.value = toMessage(error)
  } finally {
    if (!controller.signal.aborted) domainMembersLoading.value = false
  }
}
async function loadPreview() {
  previewController?.abort()
  previewDetail.value = null
  previewError.value = ''
  previewLoading.value = false
  if (!selected.value) return
  const controller = new AbortController()
  previewController = controller
  previewLoading.value = true
  try {
    const detail = await relationsApi.get(selected.value.id, controller.signal)
    if (!controller.signal.aborted) previewDetail.value = detail
  } catch (error) {
    if (!controller.signal.aborted) previewError.value = toMessage(error)
  } finally {
    if (!controller.signal.aborted) previewLoading.value = false
  }
}
watch(domainFilter, () => void loadDomainMembers(), { immediate: true })
watch(selected, () => void loadPreview())

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
        h('button', { class: 'name-link', onClick: () => preview(row.id) }, label),
        label === row.name ? null : h('span', { class: 'cell-sub mono' }, row.name),
      ])
    },
  },
  {
    title: t('ontologyUi.endpoints'),
    key: 'endpoints',
    minWidth: 250,
    render: (row) => {
      const detail = details.value[row.id]
      return detail
        ? `${typeNameById.value[detail.domain_spec.type_id] ?? `#${detail.domain_spec.type_id}`} → ${typeNameById.value[detail.range_spec.type_id] ?? `#${detail.range_spec.type_id}`}`
        : h(UiButton, { size: 'tiny', quaternary: true, onClick: () => goToDetail(row.id) }, () =>
            t('common.view'),
          )
    },
  },
  {
    title: t('common.iri'),
    key: 'iri',
    minWidth: 300,
    render: (row) => h('span', { class: 'iri', title: row.iri }, row.iri),
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
    fixed: 'right',
    width: 300,
    render: (row) =>
      h(UiSpace, { size: 4, wrap: false }, () => [
        h(
          UiButton,
          { size: 'small', quaternary: true, onClick: () => goToDetail(row.id) },
          { default: () => t('common.view') },
        ),
        h(
          UiButton,
          {
            size: 'small',
            quaternary: true,
            disabled: !canWrite.value || row.status !== 'DRAFT',
            onClick: () => void openEdit(row.id),
          },
          { default: () => t('common.edit') },
        ),
        // 草稿才能发布：发布即冻结，之后不可再改。已发布的没有「重新发布」语义。
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
        canDelete(row)
          ? h(
              UiPopconfirm,
              { onPositiveClick: () => void remove(row) },
              {
                default: () =>
                  t('relation.deleteConfirm', { name: pickLabel(row.label_i18n, row.name) }),
                trigger: () =>
                  h(
                    UiButton,
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
            )
          : null,
      ]),
  },
])

function canDelete(row: RelationTypeBrief): boolean {
  return canWrite.value && row.status === 'DRAFT' && row.current_revision === 0
}

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

function emptyForm() {
  return {
    name: '',
    namespace_id: null as number | null,
    labelZh: '',
    labelEn: '',
    definitionZh: '',
    definitionEn: '',
    domainType: null as number | null,
    rangeType: null as number | null,
    domainCardinality: { min: 0, max: -1 } as NonNullable<
      RelationTypeDetail['domain_spec']['cardinality']
    >,
    rangeCardinality: { min: 0, max: -1 } as NonNullable<
      RelationTypeDetail['range_spec']['cardinality']
    >,
    inverseOf: null as number | null,
    owl: {
      functional: false,
      inverse_functional: false,
      symmetric: false,
      transitive: false,
    } as RelationTypeDetail['owl'],
    enableAttrs: false,
  }
}
const formData = ref(emptyForm())

function snapshotForm() {
  return {
    ...formData.value,
    domainCardinality: { ...formData.value.domainCardinality },
    rangeCardinality: { ...formData.value.rangeCardinality },
    owl: { ...formData.value.owl },
  }
}

function semanticPayload(f: ReturnType<typeof snapshotForm>) {
  const label_i18n: Record<string, string> = { 'zh-CN': f.labelZh.trim() }
  if (f.labelEn.trim()) label_i18n['en-US'] = f.labelEn.trim()
  const definition_i18n: Record<string, string> = {}
  if (f.definitionZh.trim()) definition_i18n['zh-CN'] = f.definitionZh.trim()
  if (f.definitionEn.trim()) definition_i18n['en-US'] = f.definitionEn.trim()
  return { label_i18n, definition_i18n, inverse_of: f.inverseOf, owl: f.owl }
}

function validCardinality(value: unknown) {
  if (value === null || typeof value !== 'object') return false
  const spec = value as { min?: unknown; max?: unknown }
  return (
    typeof spec.min === 'number' &&
    typeof spec.max === 'number' &&
    Number.isSafeInteger(spec.min) &&
    Number.isSafeInteger(spec.max) &&
    spec.min >= 0 &&
    (spec.max === -1 || spec.max >= spec.min)
  )
}

const inverseOptions = computed(() => {
  const options = inverseRelations.value.map((item) => ({
    value: item.id,
    label: `${item.name} · ${pickLabel(item.label_i18n, item.name)}`,
  }))
  const id = formData.value.inverseOf
  if (id !== null && !options.some((item) => item.value === id))
    options.push({ value: id, label: `#${id}` })
  return options
})

async function loadReferences() {
  const generation = ++referenceGeneration
  referencesLoading.value = true
  referencesError.value = ''
  try {
    const [types, relations] = await Promise.all([entityTypesApi.list(), relationsApi.list()])
    if (generation !== referenceGeneration) return
    typeList.value = types
    inverseRelations.value = relations
  } catch (cause) {
    if (generation === referenceGeneration) referencesError.value = toMessage(cause)
  } finally {
    if (generation === referenceGeneration) referencesLoading.value = false
  }
}

const nsOptions = computed(() => namespaces.value.map((ns) => ({ label: ns.prefix, value: ns.id })))
const showNamespaceCreate = ref(false)

/** 就地登记的命名空间直接选中，并只重校该字段，清掉此前残留的「必填」提示。 */
function onNamespaceCreated(ns: Namespace) {
  namespaces.value = [...namespaces.value, ns]
  formData.value.namespace_id = ns.id
  void createFormRef.value?.validate(undefined, ['namespace_id']).catch(() => undefined)
}
const typeOptions = computed(() =>
  typeList.value.map((tp) => ({ label: pickLabel(tp.label_i18n, tp.name), value: tp.id })),
)

const createFormRef = ref<FormInst | null>(null)
const editFormRef = ref<FormInst | null>(null)

/** 定义域与值域是实体引用；两端基数按当前 schema 验证。 */
const endpointRules = computed<FormRules>(() => ({
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
}))

function cardinalityRule(side: 'domainCardinality' | 'rangeCardinality'): FormRule {
  // Both field errors depend on the pair, so correcting either bound revalidates both.
  const cardinality = { ...formData.value[side] }
  return {
    validator: () => validCardinality(cardinality),
    message: t('relation.cardinalityInvalid'),
    trigger: 'change',
  }
}

const cardinalityRules = computed<FormRules>(() => ({
  'domainCardinality.min': cardinalityRule('domainCardinality'),
  'domainCardinality.max': cardinalityRule('domainCardinality'),
  'rangeCardinality.min': cardinalityRule('rangeCardinality'),
  'rangeCardinality.max': cardinalityRule('rangeCardinality'),
}))

const createRules = computed<FormRules>(() => ({
  name: [
    { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
    {
      pattern: formData.value.enableAttrs ? /^[A-Z][A-Za-z0-9]*$/ : /^[A-Za-z][A-Za-z0-9]*$/,
      message: t(
        formData.value.enableAttrs ? 'relation.namePattern' : 'relation.objectNamePattern',
      ),
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
  ...endpointRules.value,
  ...cardinalityRules.value,
}))

const editRules = computed<FormRules>(() => ({
  name: {
    required: true,
    pattern: editingDetail.value?.enable_attributes
      ? /^[A-Z][A-Za-z0-9]*$/
      : /^[A-Za-z][A-Za-z0-9]*$/,
    message: t(
      editingDetail.value?.enable_attributes
        ? 'relation.namePattern'
        : 'relation.objectNamePattern',
    ),
    trigger: ['blur', 'input'],
  },
  labelZh: { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
  ...endpointRules.value,
  ...cardinalityRules.value,
}))

async function load() {
  if (!alive) return
  const generation = ++listGeneration
  detailGeneration++
  details.value = {}
  loading.value = true
  loadError.value = ''
  try {
    const next = await relationsApi.list({ q: searchQuery.value })
    if (generation !== listGeneration) return
    items.value = next
    void loadDetails()
  } catch (err) {
    // 加载失败静默清空会让用户以为「没有数据」；至少给出可见的错误提示
    if (generation === listGeneration) {
      items.value = []
      loadError.value = toMessage(err)
    }
  } finally {
    if (generation === listGeneration) loading.value = false
  }
}

function search() {
  page.value = 1
  void load()
}

function resetFilters() {
  searchQuery.value = ''
  statusFilter.value = ''
  domainFilter.value = null
  search()
}

function changePageSize(value: number) {
  pageSize.value = value
  page.value = 1
}

function countText(value: number, domainScoped = false) {
  return loading.value ||
    loadError.value ||
    (domainScoped && (domainMembersLoading.value || domainMembersError.value))
    ? t('ui.unknown')
    : new Intl.NumberFormat(locale.value).format(value)
}

/**
 * 列表接口只返回 brief（不含定义域/值域），卡片上的迷你图谱需要详情。
 * 按需补齐，已取过的进缓存，切回表格再切回来不会重复请求。
 */
async function loadDetails() {
  if (!alive) return
  const generation = ++detailGeneration
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
    if (generation !== detailGeneration) return
    const next = { ...details.value }
    for (const d of results) if (d) next[d.id] = d
    details.value = next
  } finally {
    if (generation === detailGeneration) detailsLoading.value = false
  }
}

watch(view, (v) => {
  if (v === 'card') void loadDetails()
})

async function handleCreate() {
  if (!alive || !canWrite.value || creating.value || createValidating.value) return
  const generation = createGeneration
  const current = () => alive && generation === createGeneration
  createError.value = ''
  const f = snapshotForm()
  createValidating.value = true
  try {
    try {
      await createFormRef.value?.validate()
    } catch {
      return
    }
    if (!current() || !canWrite.value) return
    if (!validCardinality(f.domainCardinality) || !validCardinality(f.rangeCardinality)) {
      createError.value = t('relation.cardinalityInvalid')
      return
    }
    createValidating.value = false
    creating.value = true
    const payload: RelationTypeCreate = {
      name: f.name.trim(),
      namespace_id: f.namespace_id as number,
      ...semanticPayload(f),
      domain_spec: { type_id: f.domainType as number, cardinality: f.domainCardinality },
      range_spec: { type_id: f.rangeType as number, cardinality: f.rangeCardinality },
      enable_attributes: f.enableAttrs,
    }
    await relationsApi.create(payload)
    if (!current()) return
    showCreate.value = false
    formData.value = emptyForm()
    createFormRef.value?.restoreValidation()
    await load()
    await loadDetails()
  } catch (err) {
    if (current()) createError.value = toMessage(err)
  } finally {
    if (current()) {
      creating.value = false
      createValidating.value = false
    }
  }
}

/** 详情页与实体类型对齐：端点、基数、OWL 特征、规则命中与引用面。 */
function goToDetail(id: number) {
  void router.push({ name: 'relation-detail', params: { id }, query: route.query })
}

async function openEdit(id: number) {
  if (!canWrite.value) return

  if (showEdit.value) {
    editVisible.value = false
    if (showEdit.value) return
  }
  invalidateEditSession()
  const session: RelationEditSession = {
    id,
    generation: editGeneration,
    controller: new AbortController(),
  }
  editSession = session
  editingDetail.value = null
  editError.value = ''
  showEdit.value = true
  try {
    const detail = await relationsApi.get(id, session.controller.signal)
    if (editSession !== session || session.controller.signal.aborted || showCreate.value) return
    editingDetail.value = detail
    formData.value = {
      name: detail.name,
      namespace_id: detail.namespace_id,
      labelZh: detail.label_i18n?.['zh-CN'] ?? '',
      labelEn: detail.label_i18n?.['en-US'] ?? '',
      definitionZh: detail.definition_i18n?.['zh-CN'] ?? '',
      definitionEn: detail.definition_i18n?.['en-US'] ?? '',
      domainType: detail.domain_spec.type_id,
      rangeType: detail.range_spec.type_id,
      domainCardinality: {
        ...detail.domain_spec.cardinality,
        min: detail.domain_spec.cardinality?.min ?? 0,
        max: detail.domain_spec.cardinality?.max ?? -1,
      },
      rangeCardinality: {
        ...detail.range_spec.cardinality,
        min: detail.range_spec.cardinality?.min ?? 0,
        max: detail.range_spec.cardinality?.max ?? -1,
      },
      inverseOf: detail.inverse_of ?? null,
      owl: { ...detail.owl },
      enableAttrs: detail.enable_attributes,
    }
  } catch (err) {
    if (editSession !== session || session.controller.signal.aborted) return
    editError.value = (err as { code?: string }).code || t('relation.loadFailed')
  }
}

function openCreate() {
  if (!canWrite.value || showCreate.value) return
  if (showEdit.value) {
    editVisible.value = false
    if (showEdit.value) return
  }
  invalidateEditSession()
  formData.value = emptyForm()
  showCreate.value = true
}

async function handleEdit() {
  if (!canWrite.value) return
  const session = editSession
  const detail = editingDetail.value
  if (
    !session ||
    !detail ||
    detail.id !== session.id ||
    detail.status !== 'DRAFT' ||
    editing.value ||
    editValidating.value
  )
    return
  if (!isCurrentEdit(session)) return
  const f = snapshotForm()
  if (f.enableAttrs !== detail.enable_attributes) {
    editError.value = t('relation.attributeModeImmutable')
    return
  }
  const payload: RelationTypeUpdate = {
    ...semanticPayload(f),
    domain_spec: {
      ...detail.domain_spec,
      type_id: f.domainType as number,
      cardinality: f.domainCardinality,
    },
    range_spec: {
      ...detail.range_spec,
      type_id: f.rangeType as number,
      cardinality: f.rangeCardinality,
    },
    if_match: detail.current_revision,
    edit_revision: detail.edit_revision,
  }
  editError.value = ''
  editValidating.value = true
  try {
    await editFormRef.value?.validate()
  } catch {
    if (isCurrentEdit(session)) editValidating.value = false
    return
  }
  if (!canWrite.value || !isCurrentEdit(session)) {
    if (isCurrentEdit(session)) editValidating.value = false
    return
  }
  if (!validCardinality(f.domainCardinality) || !validCardinality(f.rangeCardinality)) {
    editError.value = t('relation.cardinalityInvalid')
    editValidating.value = false
    return
  }
  editValidating.value = false
  editing.value = true
  try {
    let updated = await relationsApi.update(detail.id, payload)
    // 草稿态改机读名：重建 IRI 并同步规则引用面（与实体类型详情页对齐）
    const nextName = f.name.trim()
    if (detail.status === 'DRAFT' && nextName && nextName !== detail.name) {
      updated = await relationsApi.rename(detail.id, nextName)
    }
    if (!isCurrentEdit(session)) return
    details.value = { ...details.value, [updated.id]: updated }
    showEdit.value = false
    await load()
  } catch (err) {
    if (isCurrentEdit(session)) editError.value = toMessage(err)
  } finally {
    if (isCurrentEdit(session)) editing.value = false
  }
}

/**
 * 发布关系类型：冻结当前草稿为不可变版本。
 *
 * 没有这一步，草稿态关系永远进不了本体装配——后端一直有 publish 接口，
 * 前端此前没有封装，等于把工作流断在列表页。
 */
async function publish(row: RelationTypeBrief) {
  if (!alive || !canWrite.value) return
  if (publishingId.value !== null) return
  publishingId.value = row.id
  actionError.value = ''
  try {
    await relationsApi.publish(row.id)
    if (!alive) return
    await load()
    await loadDetails()
  } catch (err) {
    if (alive) actionError.value = toMessage(err)
  } finally {
    if (alive) publishingId.value = null
  }
}

async function remove(row: RelationTypeBrief) {
  if (!alive || !canDelete(row) || removingId.value !== null) return
  removingId.value = row.id
  actionError.value = ''
  notice.value = ''
  try {
    await relationsApi.remove(row.id)
    if (!alive) return
    notice.value = t('relation.deleted', { name: pickLabel(row.label_i18n, row.name) })
    await load()
    await loadDetails()
  } catch (err) {
    if (alive) actionError.value = toMessage(err)
  } finally {
    if (alive) removingId.value = null
  }
}

/** 打开抽屉即重置校验态，避免上一轮报错残留。 */
watch(
  showCreate,
  (open) => {
    createGeneration++
    creating.value = false
    createValidating.value = false
    createError.value = ''
    if (!open) return
    showEdit.value = false
    invalidateEditSession()
    createError.value = ''
    createFormRef.value?.restoreValidation()
  },
  { flush: 'sync' },
)
watch(
  showEdit,
  (open) => {
    if (!open) invalidateEditSession()
    if (!open) return
    editError.value = ''
    editFormRef.value?.restoreValidation()
  },
  { flush: 'sync' },
)

watch(
  () => route.query.edit,
  (value) => {
    const id = Number(value)
    if (Number.isSafeInteger(id) && id > 0) void openEdit(id)
  },
  { immediate: true },
)

onMounted(async () => {
  await Promise.all([
    load(),
    loadDomains(),
    namespacesApi
      .list()
      .then((r) => {
        namespaces.value = r
      })
      .catch(() => undefined),
    loadReferences(),
  ])
  await loadDetails()
})

const createVisible = useDraftGuard(showCreate, () => formData.value)

const editVisible = useDraftGuard(
  showEdit,
  () => formData.value,
  () => editingDetail.value !== null,
)
</script>

<template>
  <section class="page asset-page asset-catalog">
    <PageHeader :title="t('page.relationTypes')" :description="t('relation.description')">
      <template #actions>
        <UiButton type="primary" :disabled="!canWrite" @click="openCreate">{{
          t('common.create')
        }}</UiButton>
      </template>
    </PageHeader>
    <UiAlert v-if="!canWrite" type="info" class="alert">{{ t('ui.readonly') }}</UiAlert>

    <UiAlert v-if="actionError" type="error" role="alert" class="action-alert">{{
      actionError
    }}</UiAlert>
    <UiAlert v-if="notice" type="success" role="status" class="action-alert">{{ notice }}</UiAlert>

    <div class="ledger-workspace" :class="{ 'has-selection': selected }">
      <AssetDomainFilter
        v-model:value="domainFilter"
        :domains="domains"
        :loading="domainsLoading"
        :error="domainsError"
        @retry="loadDomains"
      />
      <div class="ledger-main">
        <div class="stats" role="group" :aria-label="t('common.status')">
          <button
            type="button"
            class="stat"
            :class="{ active: statusFilter === '' }"
            @click="statusFilter = ''"
          >
            <span class="stat-value mono">{{ countText(counts[''] ?? 0) }}</span>
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
              {{ countText(counts[s] ?? 0) }}
            </span>
            <span class="stat-label">{{ t(`resourceStatus.${s}`) }}</span>
          </button>
        </div>

        <div class="toolbar">
          <SearchPanel
            v-model:query="searchQuery"
            class="relation-search"
            :loading="loading"
            @submit="search"
            @clear="search"
            @reset="resetFilters"
          />
          <div class="seg" role="group" :aria-label="t('common.viewMode')">
            <button type="button" :class="{ on: view === 'table' }" @click="view = 'table'">
              {{ t('common.viewTable') }}
            </button>
            <button type="button" :class="{ on: view === 'card' }" @click="view = 'card'">
              {{ t('common.viewCard') }}
            </button>
          </div>
        </div>

        <UiAlert v-if="domainMembersError && view === 'card'" type="error" role="alert"
          >{{ domainMembersError
          }}<UiButton @click="loadDomainMembers">{{ t('ui.retry') }}</UiButton></UiAlert
        >
        <UiSpin :show="loading || detailsLoading || domainMembersLoading">
          <UiAlert v-if="loadError && view === 'card'" type="error" class="list-error"
            >{{ loadError }} <UiButton @click="load">{{ t('ui.retry') }}</UiButton></UiAlert
          >
          <div v-if="view === 'table'" class="card">
            <header class="ledger-caption">
              <h2>{{ t('page.relationTypes') }}</h2>
              <span>{{
                t('assetLedger.resultCount', { count: countText(filtered.length, true) })
              }}</span>
            </header>
            <SearchTable
              v-model:page="page"
              :searchable="false"
              :columns="columns"
              :rows="domainMembersError || domainMembersLoading ? [] : filtered"
              mode="local"
              :page-size="pageSize"
              :loading="loading || domainMembersLoading"
              :error="loadError || domainMembersError"
              :bordered="false"
              size="small"
              :pagination="{ showSizePicker: true }"
              :scroll-x="1040"
              :selection="selected ? [selected.id] : []"
              :row-key="(row: RelationTypeBrief) => row.id"
              @row-click="(row: RelationTypeBrief) => preview(row.id)"
              @update:page-size="changePageSize"
              @retry="domainMembersError ? loadDomainMembers() : load()"
            >
              <template #empty>
                <UiEmpty
                  :description="
                    t(searchQuery || statusFilter ? 'ui.emptyFiltered' : 'common.empty')
                  "
                />
              </template>
            </SearchTable>
          </div>

          <!-- 卡片视图：每条关系用一张迷你图谱表达「定义域 → 值域」 -->
          <div v-else-if="filtered.length" class="cards">
            <article
              v-for="row in filtered"
              :key="row.id"
              class="rel-card"
              :class="{ selected: selected?.id === row.id }"
            >
              <header class="rel-head">
                <button class="name-link cell-primary" @click="preview(row.id)">
                  {{ pickLabel(row.label_i18n, row.name) }}
                </button>
                <span class="cell-sub mono">{{ row.name }}</span>
                <span class="mono rev">{{ `v${row.current_revision}` }}</span>
              </header>

              <svg class="rel-graph" viewBox="0 0 268 64" fill="none" aria-hidden="true">
                <path
                  d="M56 32H212"
                  :stroke="
                    row.status === 'PUBLISHED' ? 'var(--g-relation)' : 'var(--border-strong)'
                  "
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
                  style="color: var(--g-derived); border-color: var(--g-derived)"
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

          <div v-else-if="!loading && !loadError" class="card empty-card">
            <UiEmpty
              :description="t(searchQuery || statusFilter ? 'ui.emptyFiltered' : 'common.empty')"
            />
          </div>
        </UiSpin>
      </div>
      <AssetInspector
        v-if="selected"
        :label="pickLabel(selected.label_i18n, selected.name)"
        :name="selected.name"
        :iri="selected.iri"
        :status="selected.status"
        :revision="selected.current_revision"
        @close="preview(null)"
        @open="goToDetail(selected.id)"
      >
        <UiAlert v-if="previewError" type="error" role="alert"
          >{{ previewError }}<UiButton @click="loadPreview">{{ t('ui.retry') }}</UiButton></UiAlert
        >
        <UiSpin :show="previewLoading">
          <dl v-if="previewDetail" class="preview-meta">
            <dt>{{ t('relation.domain') }}</dt>
            <dd>
              {{
                typeNameById[previewDetail.domain_spec.type_id] ??
                `#${previewDetail.domain_spec.type_id}`
              }}
            </dd>
            <dt>{{ t('relation.range') }}</dt>
            <dd>
              {{
                typeNameById[previewDetail.range_spec.type_id] ??
                `#${previewDetail.range_spec.type_id}`
              }}
            </dd>
            <dt>{{ t('relation.cardinality') }}</dt>
            <dd>
              {{ cardinalityText(previewDetail.domain_spec.cardinality) }} /
              {{ cardinalityText(previewDetail.range_spec.cardinality) }}
            </dd>
            <dt>{{ t('relation.owl') }}</dt>
            <dd>
              {{
                owlTags(previewDetail)
                  .map((key) => t(`relation.${key}`))
                  .join(' / ') || t('common.noneValue')
              }}
            </dd>
          </dl>
        </UiSpin>
        <template #actions
          ><UiButton
            v-if="canWrite && selected.status === 'DRAFT'"
            @click="openEdit(selected.id)"
            >{{ t('common.edit') }}</UiButton
          ></template
        >
      </AssetInspector>
    </div>

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

    <UiDrawer v-model:show="createVisible" width="min(520px, 100vw)">
      <UiDrawerContent class="asset-editor" :title="t('relation.create')" closable>
        <FormContainer
          ref="createFormRef"
          :model="formData"
          :rules="createRules"
          :disabled="creating || !canWrite"
          :submitting="creating"
          label-placement="top"
        >
          <fieldset class="form-section">
            <legend>{{ t('common.name') }}</legend>
            <FormField :label="t('common.name')" path="name">
              <UiInput v-model:value="formData.name" placeholder="WorksIn" />
              <template #feedback>{{
                t(formData.enableAttrs ? 'relation.nameHint' : 'relation.objectNameHint')
              }}</template>
            </FormField>
            <FormField :label="t('common.namespace')" path="namespace_id">
              <div class="ns-field">
                <UiSelect
                  v-model:value="formData.namespace_id"
                  :options="nsOptions"
                  :aria-label="t('common.namespace')"
                />
                <UiButton @click="showNamespaceCreate = true">{{
                  t('namespace.createShort')
                }}</UiButton>
              </div>
            </FormField>
            <UiAlert v-if="!namespaces.length" type="info" class="ns-hint">
              {{ t('namespace.emptyHint') }}
            </UiAlert>
          </fieldset>
          <fieldset class="form-section">
            <legend>{{ t('common.label') }}</legend>
            <div class="form-grid">
              <FormField :label="t('common.labelZh')" path="labelZh">
                <UiInput v-model:value="formData.labelZh" />
              </FormField>
              <FormField :label="t('common.labelEn')" path="labelEn">
                <UiInput v-model:value="formData.labelEn" />
              </FormField>
            </div>
          </fieldset>
          <fieldset class="form-section">
            <legend>{{ t('relationDetail.endpoints') }}</legend>
            <FormField :label="t('relation.domain')" path="domainType" data-endpoint="domain">
              <UiSelect
                v-model:value="formData.domainType"
                :options="typeOptions"
                :aria-label="t('relation.domain')"
                filterable
              />
            </FormField>
            <FormField :label="t('relation.range')" path="rangeType" data-endpoint="range">
              <UiSelect
                v-model:value="formData.rangeType"
                :options="typeOptions"
                :aria-label="t('relation.range')"
                filterable
              />
            </FormField>
            <UiAlert v-if="referencesError" type="warning"
              >{{ referencesError }}
              <UiButton @click="loadReferences">{{ t('ui.retry') }}</UiButton></UiAlert
            >
            <RelationSemanticFields
              v-model:definition-zh="formData.definitionZh"
              v-model:definition-en="formData.definitionEn"
              v-model:domain-cardinality="formData.domainCardinality"
              v-model:range-cardinality="formData.rangeCardinality"
              v-model:inverse-of="formData.inverseOf"
              v-model:owl="formData.owl"
              :inverse-options="inverseOptions"
              :references-loading="referencesLoading"
            />
            <FormField :label="t('relation.enableAttributes')" path="enableAttrs">
              <UiCheckbox v-model:checked="formData.enableAttrs" />
            </FormField></fieldset
        ></FormContainer>
        <UiAlert v-if="createError" type="error" class="create-error">{{ createError }}</UiAlert>
        <template #footer>
          <div class="drawer-actions">
            <UiButton :disabled="creating" @click="createVisible = false">
              {{ t('common.cancel') }}
            </UiButton>
            <UiButton type="primary" :loading="creating || createValidating" @click="handleCreate">
              {{ t('common.save') }}
            </UiButton>
          </div>
        </template>
      </UiDrawerContent>
    </UiDrawer>

    <UiDrawer v-model:show="editVisible" width="min(520px, 100vw)">
      <UiDrawerContent class="asset-editor" :title="t('relation.edit')" closable>
        <UiAlert v-if="editingDetail && editingDetail.status !== 'DRAFT'" type="info">{{
          t('ui.frozen')
        }}</UiAlert>
        <p v-if="!editingDetail && !editError" role="status">{{ t('common.loading') }}</p>
        <FormContainer
          v-if="editingDetail"
          ref="editFormRef"
          :disabled="editing || !canWrite || editingDetail?.status !== 'DRAFT'"
          :submitting="editing"
          :model="formData"
          :rules="editRules"
          label-placement="top"
        >
          <fieldset class="form-section">
            <legend>{{ t('common.name') }}</legend>
            <FormField :label="t('common.name')" path="name">
              <UiInput
                v-model:value="formData.name"
                :disabled="editingDetail?.status !== 'DRAFT'"
              />
              <template #feedback>{{
                editingDetail?.status === 'DRAFT'
                  ? t('relation.nameDraftHint')
                  : t('entityType.nameImmutable')
              }}</template>
            </FormField>
            <FormField :label="t('common.labelZh')" path="labelZh">
              <UiInput v-model:value="formData.labelZh" />
            </FormField>
            <FormField :label="t('common.labelEn')" path="labelEn">
              <UiInput v-model:value="formData.labelEn" />
            </FormField>
          </fieldset>
          <fieldset class="form-section">
            <legend>{{ t('relationDetail.endpoints') }}</legend>
            <FormField :label="t('relation.domain')" path="domainType" data-endpoint="domain">
              <UiSelect
                v-model:value="formData.domainType"
                :options="typeOptions"
                :aria-label="t('relation.domain')"
                filterable
              />
            </FormField>
            <FormField :label="t('relation.range')" path="rangeType" data-endpoint="range">
              <UiSelect
                v-model:value="formData.rangeType"
                :options="typeOptions"
                :aria-label="t('relation.range')"
                filterable
              />
            </FormField>
            <UiAlert v-if="referencesError" type="warning"
              >{{ referencesError }}
              <UiButton @click="loadReferences">{{ t('ui.retry') }}</UiButton></UiAlert
            >
          </fieldset>
          <RelationSemanticFields
            v-model:definition-zh="formData.definitionZh"
            v-model:definition-en="formData.definitionEn"
            v-model:domain-cardinality="formData.domainCardinality"
            v-model:range-cardinality="formData.rangeCardinality"
            v-model:inverse-of="formData.inverseOf"
            v-model:owl="formData.owl"
            :inverse-options="inverseOptions"
            :references-loading="referencesLoading"
          />
          <FormField :label="t('relation.enableAttributes')">
            <UiCheckbox :checked="formData.enableAttrs" disabled />
            <template #feedback>{{ t('relation.attributeModeImmutable') }}</template>
          </FormField>
          <UiAlert
            v-if="editingDetail.union_of?.length || editingDetail.intersection_of?.length"
            type="warning"
            >{{ t('relation.unsupportedSetExpression') }}</UiAlert
          >
        </FormContainer>
        <UiAlert v-if="editError" type="error" class="create-error">{{ editError }}</UiAlert>
        <template #footer>
          <div class="drawer-actions">
            <UiButton :disabled="editing" @click="editVisible = false">
              {{ t('common.cancel') }}
            </UiButton>
            <UiButton
              type="primary"
              :loading="editing || editValidating"
              :disabled="!canWrite || editingDetail?.status !== 'DRAFT'"
              @click="handleEdit"
            >
              {{ t('common.save') }}
            </UiButton>
          </div>
        </template>
      </UiDrawerContent>
    </UiDrawer>
    <NamespaceCreateModal v-model:show="showNamespaceCreate" @created="onNamespaceCreated" />
  </section>
</template>

<style scoped>
.name-link {
  border: 0;
  background: none;
  color: var(--pri);
  padding: 0;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
}
.page {
  padding-bottom: var(--space-5);
}

.ns-field {
  display: flex;
  gap: var(--space-2);
  width: 100%;
}

.ns-hint {
  margin-bottom: var(--space-3);
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
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  margin-bottom: var(--space-3);
}

.relation-search {
  flex: 1 1 360px;
  min-width: 0;
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

.list-error {
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

<style scoped src="../styles/observatory.css"></style>
