<script setup lang="ts">
import { FocusScope } from 'reka-ui'
import type { ComponentPublicInstance } from 'vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'

import type { DomainBrief, DomainMember } from '@/api/domains'
import { domainsApi } from '@/api/domains'
import type { EntityType, EntityTypeBrief, ResourceStatus } from '@/api/entity-types'
import { entityTypesApi } from '@/api/entity-types'
import { type Rule, rulesApi } from '@/api/governance'
import type { Namespace } from '@/api/namespaces'
import { namespacesApi } from '@/api/namespaces'
import type { CanvasPositions, Ontology, OntologyDetail, OntologyRef } from '@/api/ontology'
import { ontologyApi } from '@/api/ontology'
import type { ModelingApplication } from '@/api/ontology-modeling'
import type { RelationTypeBrief, RelationTypeDetail } from '@/api/relations'
import { relationsApi } from '@/api/relations'
import type { ValidationReport, ValidationResultItem } from '@/api/validation'
import { validationApi } from '@/api/validation'
import { fieldRules, readField, validateFieldValue } from '@/components/business/formValidation'
import { dragPosition, isDrag, wheelCamera, zoomAt } from '@/components/graph/viewport'
import {
  FormContainer,
  FormField,
  UiAlert,
  UiButton,
  UiDrawer,
  UiDrawerContent,
  UiEmpty,
  UiInput,
  UiModal,
  UiSelect,
  UiSpin,
  useMessage,
} from '@/components/ui'
import type { FormInst, FormRules } from '@/components/ui/formTypes'
import { useApiError } from '@/composables/useApiError'
import { usePageIdentity } from '@/layout/navigation/usePageIdentity'
import { useAuthStore } from '@/stores/auth'
import AiSuggestions from '@/views/ontology/designer/components/AiSuggestions.vue'
import { designerEdges } from '@/views/ontology/designer/components/designerGeometry'
import AiModeling from '@/views/ontology/designer/components/modeling/AiModeling.vue'
import { useDesignerHistory } from '@/views/ontology/designer/composables/useDesignerHistory'

const { t, te, locale } = useI18n()
const message = useMessage()
const { toMessage } = useApiError()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const history = useDesignerHistory(toMessage)
const { revision: frozenRevision, loading: historyLoading, error: historyError } = history
const roleCanWrite = computed(() => auth.user?.role === 'ADMIN' || auth.user?.role === 'EDITOR')
const poolOpen = ref(true)
const focusMode = ref(false)
let focusOrigin: HTMLElement | null = null
watch(focusMode, async (active) => {
  if (active) {
    focusOrigin = document.activeElement instanceof HTMLElement ? document.activeElement : null
  } else {
    await nextTick()
    if (focusOrigin?.isConnected) focusOrigin.focus({ preventScroll: true })
  }
})
function toggleResources() {
  poolOpen.value = !poolOpen.value
  focusMode.value = false
}
function toggleInspector() {
  focusMode.value = false
  if (inspectorOpen.value) closeInspector()
  else inspectorOpen.value = true
}
const inspectorOpen = ref(false)
const legendOpen = ref(false)
const legendButton = ref<HTMLButtonElement | null>(null)
function setLegendButton(value: Element | ComponentPublicInstance | null) {
  legendButton.value = (value && '$el' in value ? value.$el : value) as HTMLButtonElement | null
}
const poolSearch = ref('')
function onViewportResize() {
  if (window.innerWidth < 1024) poolOpen.value = false
  if (window.innerWidth < 768) inspectorOpen.value = false
}
watch(inspectorOpen, (open) => {
  if (open && typeof window !== 'undefined' && window.innerWidth < 1024) poolOpen.value = false
})
watch(poolOpen, (open) => {
  if (open && typeof window !== 'undefined' && window.innerWidth < 1024) inspectorOpen.value = false
})
const previousCamera = ref<{ x: number; y: number; scale: number } | null>(null)
const savedPositions = ref<CanvasPositions>({})
const layoutDirty = ref(false)
const showDiscard = ref(false)
let discardAnswer: ((answer: boolean) => void) | undefined
let discardPromise: Promise<boolean> | undefined

function confirmDiscard(): Promise<boolean> {
  if (discardPromise) return discardPromise
  if (!layoutDirty.value && !createDirty.value && !rulesDirty.value) return Promise.resolve(true)
  showDiscard.value = true
  discardPromise = new Promise((resolve) => {
    discardAnswer = resolve
  })
  return discardPromise
}
function answerDiscard(answer: boolean) {
  showDiscard.value = false
  discardAnswer?.(answer)
  discardAnswer = undefined
  discardPromise = undefined
}
function cancelLayout() {
  onPointerCancel()
  positions.value = copyPositions(savedPositions.value)
  layoutDirty.value = false
  saveError.value = ''
}
function copyPositions(value: CanvasPositions): CanvasPositions {
  return Object.fromEntries(Object.entries(value).map(([key, point]) => [key, { ...point }]))
}
function closeInspector() {
  inspectorOpen.value = false
  const key = selectedKey.value
  void nextTick(() => {
    const target = Array.from(
      canvasEl.value?.querySelectorAll<HTMLElement>('[data-selection]') ?? [],
    ).find((element) => element.dataset.selection === key)
    ;(target ?? canvasEl.value)?.focus({ preventScroll: true })
  })
}
function closeLegend() {
  legendOpen.value = false
  void nextTick(() => legendButton.value?.focus({ preventScroll: true }))
}

/** 画布世界尺寸固定，视口通过 transform 平移缩放 —— 拖动因此可以用纯 CSS 像素计算。 */
const WORLD_W = 2200
const WORLD_H = 1500
const NODE_W = 180
const NODE_H = 76

const loading = ref(false)
const catalogLoading = ref(true)
const saving = ref(false)
const working = ref(false)
const catalogError = ref('')
const loadError = ref('')
const saveError = ref('')
const actionError = ref('')
const needsRefresh = ref(false)
const ontologies = ref<Ontology[]>([])
const ontologyId = ref<number | null>(null)
const detail = ref<OntologyDetail | null>(null)
const refs = ref<OntologyRef[]>([])
const positions = ref<CanvasPositions>({})
const selectedKey = ref<string | null>(null)
const zoom = ref(1)
const pan = ref({ x: 0, y: 0 })

const entityTypes = ref<EntityTypeBrief[]>([])
const relations = ref<RelationTypeBrief[]>([])
const relationDetails = ref<Record<number, RelationTypeDetail>>({})
const domains = ref<DomainBrief[]>([])
const domainMembers = ref<Record<number, DomainMember[]>>({})

/** 选中实体节点的详情（含数据属性）。列表接口只给 brief，属性要按需取。 */
const typeDetail = ref<EntityType | null>(null)
const typeDetailLoading = ref(false)

/** 资产层校验（A01–A08）。装配完直接在设计器里看能不能发布。 */
const validationReport = ref<ValidationReport | null>(null)
const validationResults = ref<ValidationResultItem[]>([])
const validating = ref(false)
let validationGeneration = 0
const validationError = ref('')
const showValidation = ref(false)
const showAi = ref(false)
const showModeling = ref(false)
const showRules = ref(false)
const ruleLoading = ref(false)
const ruleError = ref('')
const ruleCatalog = ref<Rule[]>([])
const selectedRules = ref<number[]>([])
const savedRules = ref<number[]>([])
const rulesForm = ref<FormInst | null>(null)
const rulesModel = computed(() => ({ selectedRules: selectedRules.value }))
const rulesValidation = computed<FormRules>(() => ({
  selectedRules: {
    type: 'array',
    validator: (_, value) =>
      Array.isArray(value) && value.every((id) => Number.isSafeInteger(id) && id > 0),
    message: t('common.required'),
  },
}))
const rulesValidating = ref(false)
let rulesSession = 0
watch(
  showRules,
  () => {
    rulesSession++
    rulesValidating.value = false
    rulesForm.value?.restoreValidation()
  },
  { flush: 'sync' },
)
const rulesDirty = computed(
  () =>
    showRules.value &&
    JSON.stringify([...selectedRules.value].sort()) !==
      JSON.stringify([...savedRules.value].sort()),
)
const ruleOptions = computed(() =>
  ruleCatalog.value.map((rule) => ({
    value: rule.id,
    label: `${rule.identifier} · r${rule.revision}`,
  })),
)

async function openRules() {
  const context = selection
  if (!context || !canEdit.value) return
  showRules.value = true
  const session = ++rulesSession
  ruleLoading.value = true
  ruleError.value = ''
  selectedRules.value = []
  try {
    const [catalog, attached] = await Promise.all([
      rulesApi.all(context.controller.signal),
      ontologyApi.rules(context.id, context.controller.signal),
    ])
    if (!isCurrentSelection(context) || session !== rulesSession) return
    ruleCatalog.value = catalog
    selectedRules.value = attached.map((rule) => rule.rule_id)
    savedRules.value = [...selectedRules.value]
  } catch (err) {
    if (isCurrentSelection(context) && session === rulesSession) ruleError.value = toMessage(err)
  } finally {
    if (isCurrentSelection(context) && session === rulesSession) ruleLoading.value = false
  }
}

async function saveRules() {
  if (
    ruleLoading.value ||
    ruleError.value ||
    !detail.value ||
    rulesValidating.value ||
    !canEdit.value
  )
    return
  const context = selection
  const session = rulesSession
  const version = detail.value.current_revision
  const ids = [...selectedRules.value]
  rulesValidating.value = true
  try {
    await rulesForm.value?.validate()
  } catch {
    return
  } finally {
    if (session === rulesSession) rulesValidating.value = false
  }
  if (
    !context ||
    !isCurrentSelection(context) ||
    session !== rulesSession ||
    !canEdit.value ||
    JSON.stringify(ids) !== JSON.stringify(selectedRules.value)
  )
    return
  const saved = await updateOntology((id, editRevision) =>
    ontologyApi.update(
      id,
      {
        if_match: version,
        rule_ids: ids,
      },
      editRevision,
    ),
  )
  if (saved && context && isCurrentSelection(context) && session === rulesSession)
    showRules.value = false
}

const canvasEl = ref<HTMLElement | null>(null)
const worldEl = ref<HTMLElement | null>(null)
const dragging = ref<{
  key: string
  start: { x: number; y: number }
  origin: { x: number; y: number }
  moved: boolean
} | null>(null)
const panning = ref<{ start: { x: number; y: number }; origin: { x: number; y: number } } | null>(
  null,
)
let activePointer: { id: number; element: HTMLElement } | null = null

type OntologySelection = { id: number; controller: AbortController }
let selection: OntologySelection | undefined
let catalogController: AbortController | undefined
let alive = true
const pendingWrites = new Map<number, Promise<unknown>>()
const canEdit = computed(
  () =>
    roleCanWrite.value &&
    frozenRevision.value === null &&
    detail.value?.id === ontologyId.value &&
    !!detail.value &&
    !catalogLoading.value &&
    !catalogError.value &&
    !loading.value &&
    !loadError.value &&
    !saving.value &&
    !working.value &&
    !needsRefresh.value &&
    !validating.value,
)
const canValidate = computed(() =>
  frozenRevision.value === null
    ? canEdit.value
    : roleCanWrite.value &&
      !!detail.value &&
      detail.value.id === ontologyId.value &&
      !loading.value &&
      !historyLoading.value &&
      !historyError.value &&
      !validating.value,
)

function isCurrentSelection(context: OntologySelection) {
  return (
    alive &&
    selection === context &&
    ontologyId.value === context.id &&
    !context.controller.signal.aborted
  )
}

const STATUS_VAR: Record<ResourceStatus, string> = {
  PUBLISHED: 'var(--status-pass)',
  DRAFT: 'var(--status-not-run)',
  ARCHIVED: 'var(--status-na)',
}

function pickLabel(labels: Record<string, string> | null | undefined, fallback: string): string {
  return labels?.[locale.value]?.trim() || `${fallback} (${t('enumDictionaries.untranslated')})`
}

const typeById = computed(() => {
  const map: Record<
    number,
    Pick<EntityTypeBrief, 'id' | 'name' | 'iri' | 'label_i18n' | 'status'>
  > = {}
  if (frozenRevision.value !== null) {
    for (const { snapshot } of Object.values(history.resources.value)) {
      if (snapshot.kind === 'ENTITY' || snapshot.kind === 'ASSOC') {
        map[snapshot.id] = { ...snapshot, status: 'PUBLISHED' }
      }
    }
    return map
  }
  for (const tp of entityTypes.value) map[tp.id] = tp
  return map
})

const relationById = computed(() => {
  const map: Record<
    number,
    Pick<RelationTypeBrief, 'id' | 'name' | 'iri' | 'label_i18n' | 'status'>
  > = {}
  if (frozenRevision.value !== null) {
    for (const { snapshot } of Object.values(history.resources.value)) {
      if (snapshot.kind === 'OBJECT_PROP') map[snapshot.id] = { ...snapshot, status: 'PUBLISHED' }
    }
    return map
  }
  for (const r of relations.value) map[r.id] = r
  return map
})

const domainById = computed(() => {
  const map: Record<number, DomainBrief> = {}
  for (const domain of domains.value) map[domain.id] = domain
  return map
})

/** 引用里哪些是实体类型（画布节点）、哪些是对象属性（画布连线）。 */
const displayedRefIds = computed(() =>
  frozenRevision.value === null
    ? refs.value.map((r) => r.resource_id)
    : (history.contents.value?.resources.map((r) => r.resource_id) ?? []),
)
const canvasTypeIds = computed(() =>
  displayedRefIds.value.filter((id) => typeById.value[id] !== undefined),
)
const canvasRelationIds = computed(() =>
  displayedRefIds.value.filter((id) => relationById.value[id] !== undefined),
)
const canvasDomainIds = computed(() =>
  (frozenRevision.value === null ? domains.value : [])
    .filter((domain) => {
      const members = domainMembers.value[domain.id] ?? []
      return (
        members.length > 0 &&
        members.every((member) => refs.value.some((ref) => ref.resource_id === member.resource_id))
      )
    })
    .map((domain) => domain.id),
)

const nodes = computed(() =>
  canvasTypeIds.value.map((id) => {
    const tp = typeById.value[id]
    const pos = positions.value[String(id)] ?? { x: 0, y: 0 }
    return {
      key: String(id),
      id,
      label: pickLabel(tp.label_i18n, tp.name),
      name: tp.name,
      iri: tp.iri,
      status: tp.status,
      x: pos.x,
      y: pos.y,
    }
  }),
)

/** 业务域分区：把域的成员节点圈成一块背景带，域因此在画布上可见。 */
const BAND_PAD = 24
const BAND_HEAD = 24
const EMPTY_BAND_W = 220
const EMPTY_BAND_H = 76

const domainBands = computed(() => {
  const bands: {
    id: number
    label: string
    status: ResourceStatus
    x: number
    y: number
    w: number
    h: number
    count: number
  }[] = []
  const empty: typeof bands = []

  for (const id of canvasDomainIds.value) {
    const domain = domainById.value[id]
    if (!domain) continue
    const memberIds = (domainMembers.value[id] ?? []).map((member) => member.resource_id)
    const members = nodes.value.filter((node) => memberIds.includes(node.id))
    const label = pickLabel(domain.label_i18n, domain.name)
    if (!members.length) {
      empty.push({
        id,
        label,
        status: domain.status,
        x: 0,
        y: 0,
        w: EMPTY_BAND_W,
        h: EMPTY_BAND_H,
        count: 0,
      })
      continue
    }
    const left = Math.min(...members.map((n) => n.x)) - BAND_PAD
    const top = Math.min(...members.map((n) => n.y)) - BAND_PAD - BAND_HEAD
    const right = Math.max(...members.map((n) => n.x + NODE_W)) + BAND_PAD
    const bottom = Math.max(...members.map((n) => n.y + NODE_H)) + BAND_PAD
    bands.push({
      id,
      label,
      status: domain.status,
      x: left,
      y: top,
      w: right - left,
      h: bottom - top,
      count: members.length,
    })
  }

  // 成员还没上画布的域排在内容下方一行 —— 「已入画布」的域必须在画布上找得到，
  // 否则列表说在、画布上没有，是明确的状态不一致。
  const maxBottom = bands.length ? Math.max(...bands.map((b) => b.y + b.h)) : 0
  empty.forEach((band, index) => {
    band.x = 40 + index * (EMPTY_BAND_W + 24)
    band.y = maxBottom + 48
  })
  return [...bands, ...empty]
})

/** Frozen endpoints come only from that revision's references, never the live catalog. */
const relationEndpoints = computed(() => {
  const out: Record<number, { source: number; target: number }> = {}
  for (const id of canvasRelationIds.value) {
    if (frozenRevision.value !== null) {
      const snapshot = history.resources.value[id]?.snapshot
      const endpoint = (role: string, legacy: string) =>
        snapshot?.resource_refs.find((ref) => ref.role === role)?.target_id ??
        Object.values(typeById.value).find(
          (type) => type.iri === snapshot?.definition_i18n?.[legacy],
        )?.id
      const source = endpoint('relation_domain', 'domain_iri')
      const target = endpoint('relation_range', 'range_iri')
      if (source !== undefined && target !== undefined) out[id] = { source, target }
    } else {
      const relation = relationDetails.value[id]
      if (relation)
        out[id] = { source: relation.domain_spec.type_id, target: relation.range_spec.type_id }
    }
  }
  return out
})
const edges = computed(() =>
  designerEdges(
    canvasRelationIds.value.flatMap((id) => {
      const endpoints = relationEndpoints.value[id]
      return endpoints &&
        canvasTypeIds.value.includes(endpoints.source) &&
        canvasTypeIds.value.includes(endpoints.target)
        ? [
            {
              id,
              ...endpoints,
              labelWidth: relationLabel(
                pickLabel(relationById.value[id]?.label_i18n, relationById.value[id]?.name ?? ''),
              ).labelWidth,
            },
          ]
        : []
    }),
    positions.value,
    NODE_W,
    NODE_H,
  ).map((edge) => {
    const relation = relationById.value[edge.id]!
    const label = pickLabel(relation.label_i18n, relation.name)
    return {
      ...edge,
      key: `rel-${edge.id}`,
      label,
      ...relationLabel(label),
      status: relation.status,
    }
  }),
)
function relationLabel(label: string) {
  const chars = [...label]
  const displayLabel = chars.length > 18 ? `${chars.slice(0, 17).join('')}…` : label
  return {
    displayLabel,
    labelWidth: Math.max(
      60,
      [...displayLabel].reduce((size, char) => size + (char.codePointAt(0)! > 255 ? 13 : 7), 24),
    ),
  }
}

const availableTypes = computed(() =>
  entityTypes.value.filter((tp) => !canvasTypeIds.value.includes(tp.id)),
)
const availableRelations = computed(() =>
  relations.value.filter((r) => !canvasRelationIds.value.includes(r.id)),
)
const availableDomains = computed(() =>
  domains.value.filter((domain) => !canvasDomainIds.value.includes(domain.id)),
)

/** 端点没有全部在画布上的关系：画不出连线，标成「未配置」而不是静默丢掉。 */
const unconfiguredRelationIds = computed(() =>
  canvasRelationIds.value.filter((id) => !edges.value.some((edge) => edge.id === id)),
)

type PoolItem = { id: number; label: string; status: ResourceStatus; unconfigured: boolean }
type PoolCategory = { kind: 'type' | 'relation' | 'domain'; label: string; items: PoolItem[] }

function poolLabel(labels: Record<string, string> | null | undefined, fallback: string): string {
  return pickLabel(labels, fallback)
}

/** 资源池按「类型 / 关系 / 域」分类并计数 —— 一眼看出还剩哪类没装配。 */
const canvasCategories = computed<PoolCategory[]>(() => [
  {
    kind: 'type',
    label: t('designer.categoryTypes'),
    items: canvasTypeIds.value.map((id) => {
      const tp = typeById.value[id]
      return {
        id,
        label: poolLabel(tp?.label_i18n, String(id)),
        status: tp?.status ?? 'DRAFT',
        unconfigured: false,
      }
    }),
  },
  {
    kind: 'relation',
    label: t('designer.categoryRelations'),
    items: canvasRelationIds.value.map((id) => {
      const rel = relationById.value[id]
      return {
        id,
        label: poolLabel(rel?.label_i18n, String(id)),
        status: rel?.status ?? 'DRAFT',
        unconfigured: unconfiguredRelationIds.value.includes(id),
      }
    }),
  },
  {
    kind: 'domain',
    label: t('designer.categoryDomains'),
    items: canvasDomainIds.value.map((id) => {
      const domain = domainById.value[id]
      return {
        id,
        label: poolLabel(domain?.label_i18n, String(id)),
        status: domain?.status ?? 'DRAFT',
        unconfigured: false,
      }
    }),
  },
])

const availableCategories = computed<PoolCategory[]>(() => [
  {
    kind: 'type',
    label: t('designer.categoryTypes'),
    items: availableTypes.value.map((tp) => ({
      id: tp.id,
      label: poolLabel(tp.label_i18n, tp.name),
      status: tp.status,
      unconfigured: false,
    })),
  },
  {
    kind: 'relation',
    label: t('designer.categoryRelations'),
    items: availableRelations.value.map((r) => ({
      id: r.id,
      label: poolLabel(r.label_i18n, r.name),
      status: r.status,
      unconfigured: false,
    })),
  },
  {
    kind: 'domain',
    label: t('designer.categoryDomains'),
    items: availableDomains.value.map((domain) => ({
      id: domain.id,
      label: poolLabel(domain.label_i18n, domain.name),
      status: domain.status,
      unconfigured: false,
    })),
  },
])

const canvasTotal = computed(() =>
  canvasCategories.value.reduce((sum, cat) => sum + cat.items.length, 0),
)
function filterPool(categories: PoolCategory[]) {
  const query = poolSearch.value.trim().toLocaleLowerCase()
  return categories.map((category) => ({
    ...category,
    items: category.items.filter((item) => item.label.toLocaleLowerCase().includes(query)),
  }))
}
const filteredCanvasCategories = computed(() => filterPool(canvasCategories.value))
const filteredAvailableCategories = computed(() => filterPool(availableCategories.value))
const inspectedProperties = computed(() => {
  if (frozenRevision.value !== null) {
    return selected.value?.kind === 'entity'
      ? (history.resources.value[selected.value.id]?.snapshot.datatype_props ?? [])
      : []
  }
  return typeDetail.value?.data_props ?? []
})
const inspectedRevision = computed(() =>
  selected.value && frozenRevision.value !== null
    ? history.resources.value[selected.value.id]?.revision
    : undefined,
)
const pinnedRevision = computed(
  () => refs.value.find((ref) => ref.resource_id === selected.value?.id)?.pinned_revision,
)
const revisionOptions = computed(() => [
  { value: 0, label: t('designerUi.workingContent') },
  ...Array.from({ length: detail.value?.current_revision ?? 0 }, (_, index) => ({
    value: index + 1,
    label: t('designerUi.frozenVersion', { revision: index + 1 }),
  })).reverse(),
])
let workingView: {
  positions: CanvasPositions
  camera: { x: number; y: number; scale: number }
  selected: string | null
} | null = null
async function changeRevision(version: number) {
  const context = selection
  if (!context || !detail.value || saving.value || working.value) return
  validationGeneration++
  validating.value = false
  validationReport.value = null
  validationResults.value = []
  validationError.value = ''
  showValidation.value = false
  if (version === 0) {
    history.reset()
    if (workingView) {
      positions.value = workingView.positions
      setCamera(workingView.camera)
      selectedKey.value = workingView.selected
      workingView = null
    }
    return
  }
  if (!(await confirmDiscard()) || !isCurrentSelection(context)) return
  if (frozenRevision.value === null) {
    cancelLayout()
    workingView = {
      positions: copyPositions(positions.value),
      camera: camera(),
      selected: selectedKey.value,
    }
  }
  showRules.value = false
  showCreate.value = false
  showAi.value = false
  showModeling.value = false
  selectedKey.value = null
  showValidation.value = false
  if (await history.load(context.id, version)) {
    if (!isCurrentSelection(context)) return
    ensurePositions()
    await nextTick()
    fitView()
  }
}

/** 池子里点一下：类型/域直接选中，关系要补详情。 */
function selectPoolItem(kind: PoolCategory['kind'], id: number) {
  inspectorOpen.value = true
  if (kind === 'relation') selectRelation(id)
  else if (kind === 'domain') selectNode(`domain-${id}`)
  else selectNode(String(id))
}

function isPoolItemActive(kind: PoolCategory['kind'], id: number): boolean {
  if (kind === 'relation') return selectedKey.value === `rel-${id}`
  if (kind === 'domain') return selectedKey.value === `domain-${id}`
  return selectedKey.value === String(id)
}

type SelectedInspector =
  | {
      kind: 'entity'
      key: string
      id: number
      label: string
      name: string
      iri: string
      status: ResourceStatus
      x: number
      y: number
      domainLabels: string[]
    }
  | {
      kind: 'relation'
      key: string
      id: number
      label: string
      name: string
      iri: string
      status: ResourceStatus
      domainLabel: string
      rangeLabel: string
    }
  | {
      kind: 'domain'
      key: string
      id: number
      label: string
      name: string
      iri: string
      status: ResourceStatus
      memberCount: number
    }

const selected = computed<SelectedInspector | null>(() => {
  const key = selectedKey.value
  if (!key) return null

  if (key.startsWith('rel-')) {
    const id = Number(key.slice(4))
    const relation = relationById.value[id]
    const endpoints = relationEndpoints.value[id]
    if (!relation) return null
    return {
      kind: 'relation',
      key,
      id,
      label: pickLabel(relation.label_i18n, relation.name),
      name: relation.name,
      iri: relation.iri,
      status: relation.status,
      domainLabel: endpoints
        ? pickLabel(
            typeById.value[endpoints.source]?.label_i18n,
            typeById.value[endpoints.source]?.name ?? '',
          )
        : '',
      rangeLabel: endpoints
        ? pickLabel(
            typeById.value[endpoints.target]?.label_i18n,
            typeById.value[endpoints.target]?.name ?? '',
          )
        : '',
    }
  }

  if (key.startsWith('domain-')) {
    const id = Number(key.slice(7))
    const domain = domainById.value[id]
    if (!domain) return null
    return {
      kind: 'domain',
      key,
      id,
      label: pickLabel(domain.label_i18n, domain.name),
      name: domain.name,
      iri: domain.iri,
      status: domain.status,
      memberCount: domainMembers.value[id]?.length ?? 0,
    }
  }

  const node = nodes.value.find((item) => item.key === key)
  if (!node) return null
  const domainLabels = (frozenRevision.value === null ? domains.value : [])
    .filter((domain) =>
      domainMembers.value[domain.id]?.some((member) => member.resource_id === node.id),
    )
    .map((domain) => pickLabel(domain.label_i18n, domain.name))
  return { kind: 'entity', ...node, domainLabels }
})

const worldStyle = computed(() => ({
  width: `${WORLD_W}px`,
  height: `${WORLD_H}px`,
  transform: `translate(${pan.value.x}px, ${pan.value.y}px) scale(${zoom.value})`,
}))

// ── 加载 ───────────────────────────────────────────────────

async function loadCatalog(preserveSelection?: OntologySelection) {
  if (!alive) return
  catalogController?.abort()
  const controller = new AbortController()
  catalogController = controller
  catalogLoading.value = true
  catalogError.value = ''
  try {
    const [types, rels, domainList, ontologyList] = await Promise.all([
      entityTypesApi.list({}, controller.signal),
      relationsApi.list({}, controller.signal),
      domainsApi.list({}, controller.signal),
      ontologyApi.list({}, controller.signal),
    ])
    if (!alive || controller.signal.aborted) return
    const members = await Promise.all(
      domainList.map((domain) => domainsApi.members(domain.id, controller.signal)),
    )
    if (!alive || controller.signal.aborted) return
    entityTypes.value = types
    relations.value = rels
    domains.value = domainList
    domainMembers.value = Object.fromEntries(
      domainList.map((domain, index) => [domain.id, members[index]]),
    )
    ontologies.value = ontologyList
    catalogLoading.value = false
    const id = ontologyList.find((item) => item.id === ontologyId.value)?.id ?? ontologyList[0]?.id
    if (preserveSelection) {
      if (isCurrentSelection(preserveSelection)) await loadOntology(preserveSelection, true)
      return
    }
    await selectOntology(id ?? null)
  } catch (err) {
    if (alive && !controller.signal.aborted) catalogError.value = toMessage(err)
  } finally {
    if (alive && !controller.signal.aborted) catalogLoading.value = false
  }
}

/** 没有布局记录的资源按环形铺开，避免全部叠在原点。 */
function ensurePositions() {
  const missing = nodes.value.filter((n) => !positions.value[n.key])
  if (!missing.length) return
  const next = { ...positions.value }
  const total = nodes.value.length
  missing.forEach((node) => {
    const i = nodes.value.findIndex((n) => n.key === node.key)
    const angle = (2 * Math.PI * i) / Math.max(total, 1) - Math.PI / 2
    const radius = Math.min(420, 170 + total * 24)
    next[node.key] = {
      x: Math.round(WORLD_W / 2 + radius * Math.cos(angle) - NODE_W / 2),
      y: Math.round(WORLD_H / 2 + radius * Math.sin(angle) - NODE_H / 2),
    }
  })
  positions.value = next
}

async function selectOntology(id: number | null) {
  if (!alive || catalogLoading.value || catalogError.value) return false
  if (!(await confirmDiscard())) return false
  history.reset()
  workingView = null
  layoutDirty.value = false
  showCreate.value = false
  showRules.value = false
  showAi.value = false
  showModeling.value = false
  previousCamera.value = null
  selection?.controller.abort()
  validationReport.value = null
  validationResults.value = []
  validationError.value = ''
  validating.value = false
  validationGeneration++
  showValidation.value = false
  selection = id === null ? undefined : { id, controller: new AbortController() }
  stopDragging()
  ontologyId.value = id
  selectedKey.value = null
  inspectorOpen.value = false
  saving.value = false
  working.value = false
  needsRefresh.value = false
  saveError.value = ''
  actionError.value = ''
  loadError.value = ''
  detail.value = null
  refs.value = []
  positions.value = {}
  loading.value = false
  return selection ? loadOntology(selection) : false
}

async function loadOntology(context: OntologySelection, preserveView = false) {
  if (!isCurrentSelection(context)) return false
  validationGeneration++
  validating.value = false
  const retainedPositions = copyPositions(positions.value)
  const retainedSavedPositions = copyPositions(savedPositions.value)
  const retainedDirty = layoutDirty.value
  const retainedSelection = selectedKey.value
  showRules.value = false
  validationReport.value = null
  validationResults.value = []
  validationError.value = ''
  showValidation.value = false
  loading.value = true
  loadError.value = ''
  selectedKey.value = null
  detail.value = null
  refs.value = []
  positions.value = {}
  relationDetails.value = {}
  try {
    // 返回同一本体时，先等已发出的写请求完成，再读取其内容和编辑版本。
    await pendingWrites.get(context.id)?.catch(() => undefined)
    if (!isCurrentSelection(context)) return false
    const signal = context.controller.signal
    // 先读版本再读引用；并发修改最多造成保守的 409，不能把新版本绑定到旧引用。
    const onto = await ontologyApi.get(context.id, signal)
    if (!isCurrentSelection(context)) return false
    const [refList, canvas] = await Promise.all([
      ontologyApi.refs(context.id, signal),
      ontologyApi.getCanvas(context.id, signal),
    ])
    if (!isCurrentSelection(context)) return false
    // 连线需要定义域/值域，而列表接口只返回 brief，按需补详情
    const relIds = refList
      .map((r) => r.resource_id)
      .filter((rid) => relations.value.some((r) => r.id === rid))
    const relationItems = await Promise.all(relIds.map((id) => relationsApi.get(id, signal)))
    if (!isCurrentSelection(context)) return false
    detail.value = onto
    refs.value = refList
    positions.value = {
      ...((canvas.positions ?? {}) as CanvasPositions),
      ...(preserveView ? retainedPositions : {}),
    }
    relationDetails.value = Object.fromEntries(relationItems.map((item) => [item.id, item]))
    ensurePositions()
    savedPositions.value =
      preserveView && retainedDirty ? retainedSavedPositions : copyPositions(positions.value)
    layoutDirty.value = preserveView && retainedDirty
    if (preserveView) selectedKey.value = retainedSelection
    await nextTick()
    if (!isCurrentSelection(context)) return false
    if (!preserveView) fitView()
    return true
  } catch (err) {
    if (isCurrentSelection(context)) loadError.value = toMessage(err)
    return false
  } finally {
    if (isCurrentSelection(context)) loading.value = false
  }
}

async function trackWrite(id: number, write: Promise<unknown>) {
  pendingWrites.set(id, write)
  try {
    await write
  } finally {
    if (pendingWrites.get(id) === write) pendingWrites.delete(id)
  }
}

async function modelingApplied(receipt: ModelingApplication) {
  const context = selection
  if (
    !context ||
    !isCurrentSelection(context) ||
    frozenRevision.value !== null ||
    receipt.target_draft_id !== detail.value?.working_draft_id
  )
    return
  showModeling.value = false
  await loadCatalog(context)
}

// ── 布局持久化 ─────────────────────────────────────────────

async function persist() {
  const context = selection
  if (!context || !isCurrentSelection(context) || !canEdit.value) return
  await persistLayout(context)
}

async function persistLayout(context: OntologySelection) {
  if (!isCurrentSelection(context) || !roleCanWrite.value || frozenRevision.value !== null) return
  const snapshot: CanvasPositions = Object.fromEntries(
    Object.entries(positions.value).map(([key, position]) => [key, { ...position }]),
  )
  saving.value = true
  saveError.value = ''
  try {
    await trackWrite(context.id, ontologyApi.saveCanvas(context.id, snapshot))
    if (isCurrentSelection(context)) {
      savedPositions.value = copyPositions(snapshot)
      layoutDirty.value = false
    }
  } catch (err) {
    if (isCurrentSelection(context)) saveError.value = toMessage(err)
  } finally {
    if (isCurrentSelection(context)) saving.value = false
  }
}

/**
 * 自动布局：按业务域分组排布。
 *
 * 每个域占一组列（组内竖排、列满换列），组间留出间距 —— 分区带才能把
 * 同一域的成员圈在一起。不属于任何「已入画布」域的节点排在最后一组。
 */
function autoLayout() {
  if (!canEdit.value) return
  const list = nodes.value
  if (!list.length) return
  const next = { ...positions.value }

  const groups: number[][] = []
  const assigned = new Set<number>()
  for (const id of canvasDomainIds.value) {
    const memberIds = (domainMembers.value[id] ?? []).map((member) => member.resource_id)
    const ids = list
      .filter((node) => memberIds.includes(node.id) && !assigned.has(node.id))
      .map((node) => node.id)
    if (!ids.length) continue
    for (const nodeId of ids) assigned.add(nodeId)
    groups.push(ids)
  }
  const rest = list.filter((node) => !assigned.has(node.id)).map((node) => node.id)
  if (rest.length) groups.push(rest)

  const COL_STEP = NODE_W + 40
  const ROW_STEP = NODE_H + 34
  const GROUP_GAP = 64
  const MARGIN = 130
  const ROWS_PER_COL = 3

  let x = MARGIN
  let y = MARGIN
  let tallest = 1
  for (const ids of groups) {
    if (x + COL_STEP > WORLD_W - MARGIN) {
      x = MARGIN
      y += tallest * ROW_STEP + GROUP_GAP + BAND_HEAD
      tallest = 1
    }
    ids.forEach((id, index) => {
      const col = Math.floor(index / ROWS_PER_COL)
      const row = index % ROWS_PER_COL
      next[String(id)] = {
        x: Math.round(x + col * COL_STEP),
        y: Math.round(y + row * ROW_STEP),
      }
    })
    const cols = Math.ceil(ids.length / ROWS_PER_COL)
    x += cols * COL_STEP + GROUP_GAP
    tallest = Math.max(tallest, Math.min(ids.length, ROWS_PER_COL))
  }

  positions.value = next
  layoutDirty.value = true
  fitView()
}

function fitView() {
  measuredCanvas = visibleCanvas()
  previousCamera.value = camera()
  let viewportWidth = canvasEl.value?.clientWidth || 800
  const viewportHeight = Math.max(100, (canvasEl.value?.clientHeight || 520) - 60)
  let leftInset = 0
  const rect = canvasEl.value?.getBoundingClientRect()
  if (rect) {
    const inspector = canvasEl.value?.parentElement
      ?.querySelector('.inspector')
      ?.getBoundingClientRect()
    const pool = canvasEl.value?.parentElement?.querySelector('.pool')?.getBoundingClientRect()
    if (inspector) viewportWidth -= Math.max(0, rect.right - Math.max(rect.left, inspector.left))
    if (pool) {
      leftInset = Math.max(0, Math.min(rect.right, pool.right) - rect.left)
      viewportWidth -= leftInset
    }
  }
  const list = nodes.value
  if (!list.length) {
    zoom.value = 0.55
    pan.value = {
      x: leftInset + viewportWidth / 2 - (WORLD_W / 2) * zoom.value,
      y: viewportHeight / 2 - (WORLD_H / 2) * zoom.value,
    }
    return
  }

  const minX = Math.min(
    ...list.map((node) => node.x),
    ...edges.value.map((edge) => edge.lx - edge.labelWidth / 2 - 12),
    ...domainBands.value.map((band) => band.x),
  )
  const minY = Math.min(
    ...list.map((node) => node.y),
    ...edges.value.map((edge) => edge.ly - 28),
    ...domainBands.value.map((band) => band.y),
  )
  const maxX = Math.max(
    ...list.map((node) => node.x + NODE_W),
    ...edges.value.map((edge) => edge.lx + edge.labelWidth / 2 + 12),
    ...domainBands.value.map((band) => band.x + band.w),
  )
  const maxY = Math.max(
    ...list.map((node) => node.y + NODE_H),
    ...edges.value.map((edge) => edge.ly + 28),
    ...domainBands.value.map((band) => band.y + band.h),
  )
  const boundsWidth = Math.max(1, maxX - minX)
  const boundsHeight = Math.max(1, maxY - minY)
  const scale = Math.min(
    1.5,
    (viewportWidth - 64) / boundsWidth,
    (viewportHeight - 64) / boundsHeight,
  )
  zoom.value = Math.max(0.2, scale)
  pan.value = {
    x: leftInset + (viewportWidth - boundsWidth * zoom.value) / 2 - minX * zoom.value,
    y: (viewportHeight - boundsHeight * zoom.value) / 2 - minY * zoom.value,
  }
}

function stepZoom(delta: number) {
  setCamera(
    zoomAt(
      camera(),
      { x: (canvasEl.value?.clientWidth ?? 800) / 2, y: (canvasEl.value?.clientHeight ?? 520) / 2 },
      zoom.value + delta,
    ),
  )
}
function camera() {
  return { ...pan.value, scale: zoom.value }
}
function setCamera(value: { x: number; y: number; scale: number }) {
  pan.value = { x: value.x, y: value.y }
  zoom.value = value.scale
}
function restoreView() {
  if (!previousCamera.value) return
  setCamera(previousCamera.value)
  previousCamera.value = null
}

/** The visible camera region excludes overlay panels without changing saved node positions. */
function visibleCanvas() {
  const element = canvasEl.value
  const width = element?.clientWidth ?? 800
  const height = element?.clientHeight ?? 520
  const rect = element?.getBoundingClientRect?.()
  let left = 0
  let right = 0
  if (rect) {
    const body = element?.parentElement
    const pool = body?.querySelector('.pool')?.getBoundingClientRect()
    const inspector = body?.querySelector('.inspector')?.getBoundingClientRect()
    if (pool) left = Math.max(0, Math.min(rect.right, pool.right) - rect.left)
    if (inspector) right = Math.max(0, rect.right - Math.max(rect.left, inspector.left))
  }
  return {
    x: left,
    y: 0,
    width: Math.max(1, width - left - right),
    height: Math.max(1, height - 60),
  }
}
let measuredCanvas: ReturnType<typeof visibleCanvas> | null = null
function measureCanvas() {
  if (!canvasEl.value) return
  const next = visibleCanvas()
  if (measuredCanvas && !dragging.value && !panning.value) {
    const dx = next.x + next.width / 2 - (measuredCanvas.x + measuredCanvas.width / 2)
    const dy = next.y + next.height / 2 - (measuredCanvas.y + measuredCanvas.height / 2)
    if (dx || dy) {
      pan.value = { x: pan.value.x + dx, y: pan.value.y + dy }
      if (previousCamera.value)
        previousCamera.value = {
          ...previousCamera.value,
          x: previousCamera.value.x + dx,
          y: previousCamera.value.y + dy,
        }
    }
  }
  measuredCanvas = next
}
function focusSelection() {
  const key = selectedKey.value
  if (!key) return false
  const node = nodes.value.find((item) => item.key === key)
  const edge = edges.value.find((item) => item.key === key)
  const band = key.startsWith('domain-')
    ? domainBands.value.find((item) => item.id === Number(key.slice(7)))
    : undefined
  const point = node
    ? { x: node.x + NODE_W / 2, y: node.y + NODE_H / 2 }
    : edge
      ? { x: edge.lx, y: edge.ly }
      : band
        ? { x: band.x + band.w / 2, y: band.y + band.h / 2 }
        : null
  if (!point) return false
  // Native Tab can scroll an overflow-hidden ancestor to an offscreen card.
  // Camera translation owns this viewport; clear that implicit scroll first.
  if (canvasEl.value) {
    canvasEl.value.scrollLeft = 0
    canvasEl.value.scrollTop = 0
  }
  const region = visibleCanvas()
  // Focus already uses the new panel geometry; the observer must not apply
  // that same center adjustment again on its next delivery.
  measuredCanvas = region
  previousCamera.value = camera()
  zoom.value = Math.max(0.8, zoom.value)
  pan.value = {
    x: region.x + region.width / 2 - point.x * zoom.value,
    y: region.y + region.height / 2 - point.y * zoom.value,
  }
  return true
}
watch([poolOpen, inspectorOpen, selectedKey], () => {
  void nextTick(measureCanvas)
})
let canvasObserver: ResizeObserver | undefined
watch(
  canvasEl,
  (element) => {
    canvasObserver?.disconnect()
    measuredCanvas = null
    if (!element || typeof ResizeObserver === 'undefined') return
    measureCanvas()
    canvasObserver = new ResizeObserver(measureCanvas)
    canvasObserver.observe(element)
  },
  { flush: 'post' },
)

// ── 拖拽 ───────────────────────────────────────────────────

function selectNode(key: string, focusView = true) {
  selectedKey.value = key
  inspectorOpen.value = true
  if (focusView) void nextTick(focusSelection)
}
function capturePointer(event: PointerEvent): boolean {
  const element = canvasEl.value
  if (!element) return false
  try {
    element.setPointerCapture(event.pointerId)
  } catch {
    return false
  }
  activePointer = { id: event.pointerId, element }
  return true
}
function onNodeDown(key: string, event: PointerEvent) {
  if (event.button !== 0 || !event.isPrimary || activePointer) return
  event.stopPropagation()
  selectNode(key, false)
  if (!canEdit.value) return
  event.preventDefault()
  canvasEl.value?.focus({ preventScroll: true })
  if (!capturePointer(event)) return
  dragging.value = {
    key,
    start: { x: event.clientX, y: event.clientY },
    origin: { ...(positions.value[key] ?? { x: 0, y: 0 }) },
    moved: false,
  }
}
function onBackgroundDown(event: PointerEvent) {
  if (
    event.button !== 0 ||
    !event.isPrimary ||
    activePointer ||
    (event.target as Element).closest('button, [role="button"], .canvas-tools, .legend')
  )
    return
  event.preventDefault()
  canvasEl.value?.focus({ preventScroll: true })
  if (!capturePointer(event)) return
  panning.value = { start: { x: event.clientX, y: event.clientY }, origin: { ...pan.value } }
}
function onNodeMove(event: PointerEvent) {
  if (event.pointerId !== activePointer?.id) return
  const current = { x: event.clientX, y: event.clientY }
  if (panning.value) {
    pan.value = dragPosition(panning.value.origin, panning.value.start, current, 1)
    return
  }
  const drag = dragging.value
  if (!drag || !canEdit.value || (!drag.moved && !isDrag(drag.start, current))) return
  drag.moved = true
  positions.value = {
    ...positions.value,
    [drag.key]: dragPosition(drag.origin, drag.start, current, zoom.value),
  }
}
function stopDragging() {
  const pointer = activePointer
  activePointer = null
  dragging.value = null
  panning.value = null
  if (pointer?.element.hasPointerCapture(pointer.id))
    pointer.element.releasePointerCapture(pointer.id)
}
function onNodeUp(event: PointerEvent) {
  if (event.pointerId !== activePointer?.id) return
  if (dragging.value?.moved) layoutDirty.value = true
  const selectOnly = dragging.value && !dragging.value.moved
  stopDragging()
  if (selectOnly) void nextTick(focusSelection)
}
function onPointerCancel(event?: PointerEvent) {
  if (event && event.pointerId !== activePointer?.id) return
  if (dragging.value)
    positions.value = { ...positions.value, [dragging.value.key]: dragging.value.origin }
  if (panning.value) pan.value = panning.value.origin
  stopDragging()
}
function onEditorEscape(event: KeyboardEvent) {
  // Pointer capture can retain the pointer while a toolbar control owns focus.
  // Cancel the dirty gesture first; Escape only closes the inspector afterwards.
  if (
    !dragging.value &&
    !panning.value &&
    !legendOpen.value &&
    !inspectorOpen.value &&
    !focusMode.value
  )
    return
  event.preventDefault?.()
  event.stopPropagation?.()
  if (dragging.value || panning.value) {
    onPointerCancel()
    canvasEl.value?.focus({ preventScroll: true })
    return
  }
  if (legendOpen.value) {
    closeLegend()
    return
  }
  if (focusMode.value) {
    focusMode.value = false
    return
  }
  closeInspector()
}
function onCanvasKey(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    onEditorEscape(event)
    return
  }
  const shifts: Record<string, { x: number; y: number }> = {
    ArrowLeft: { x: 48, y: 0 },
    ArrowRight: { x: -48, y: 0 },
    ArrowUp: { x: 0, y: 48 },
    ArrowDown: { x: 0, y: -48 },
  }
  if (shifts[event.key]) {
    event.preventDefault()
    pan.value = { x: pan.value.x + shifts[event.key]!.x, y: pan.value.y + shifts[event.key]!.y }
  } else if (event.key === '+' || event.key === '=') {
    event.preventDefault()
    stepZoom(0.15)
  } else if (event.key === '-') {
    event.preventDefault()
    stepZoom(-0.15)
  } else if (event.key === 'Home') {
    event.preventDefault()
    fitView()
  }
}
function onWheel(event: WheelEvent) {
  event.preventDefault()
  const rect = canvasEl.value?.getBoundingClientRect()
  if (!rect) return
  setCamera(
    wheelCamera(
      camera(),
      event,
      { x: event.clientX - rect.left, y: event.clientY - rect.top },
      { width: rect.width, height: rect.height },
    ),
  )
}
function selectRelation(id: number) {
  selectNode(`rel-${id}`)
}

// ── 装配 ───────────────────────────────────────────────────

async function updateOntology(
  write: (id: number, editRevision: number) => Promise<unknown>,
  saveLayout = false,
) {
  const context = selection
  if (!context || !isCurrentSelection(context) || !canEdit.value || !detail.value) return false
  const revision = detail.value.edit_revision
  working.value = true
  actionError.value = ''
  try {
    await trackWrite(context.id, write(context.id, revision))
    if (!isCurrentSelection(context)) return false
    const loaded = await loadOntology(context, true)
    if (!loaded || !isCurrentSelection(context)) return false
    if (saveLayout) {
      await persistLayout(context)
    }
    return isCurrentSelection(context)
  } catch (err) {
    if (isCurrentSelection(context)) {
      actionError.value = toMessage(err)
      needsRefresh.value = (err as { code?: string })?.code === 'KG.REVISION_CONFLICT'
    }
    return false
  } finally {
    if (isCurrentSelection(context)) working.value = false
  }
}

async function addToCanvas(resourceId: number) {
  return updateOntology(
    (id, revision) => ontologyApi.addRef(id, resourceId, undefined, revision),
    true,
  )
}

async function addPoolItem(kind: PoolCategory['kind'], id: number) {
  if (kind !== 'domain') {
    await addToCanvas(id)
    return
  }
  const domain = domainById.value[id]
  if (!domain?.current_revision) return
  await updateOntology(
    (ontologyId, editRevision) =>
      ontologyApi.addDomainMembers(ontologyId, {
        domain_id: domain.id,
        domain_revision: domain.current_revision,
        if_edit_match: editRevision,
      }),
    true,
  )
}

// B-7 画布直接建模：在资源池新建实体类型并加入画布（关系类型需端点，引导到关系类型库）
const showCreate = ref(false)
const createNamespace = ref<number | null>(null)
const createName = ref('')
const createLabelZh = ref('')
const namespaceList = ref<Namespace[]>([])
const createLoading = ref(false)
const createValidating = ref(false)
const createForm = ref<FormInst | null>(null)
const createModel = computed(() => ({
  namespace: createNamespace.value,
  name: createName.value,
  labelZh: createLabelZh.value,
}))
const createRules = computed<FormRules>(() => ({
  namespace: { required: true, type: 'integer', min: 1, message: t('common.required') },
  name: [
    { required: true, message: t('common.required') },
    { pattern: /^[A-Z][A-Za-z0-9]*$/, message: t('entityType.namePattern') },
  ],
}))
let createSession = 0
watch(
  [showCreate, ontologyId],
  () => {
    createSession++
    createLoading.value = false
    createValidating.value = false
    createForm.value?.restoreValidation()
  },
  { flush: 'sync' },
)
const createError = ref('')
const createdResourceId = ref<number | null>(null)
const createDirty = computed(
  () =>
    showCreate.value &&
    (!!createNamespace.value || !!createName.value.trim() || !!createLabelZh.value.trim()),
)
const namespaceOptions = computed(() =>
  namespaceList.value.map((ns) => ({ label: `${ns.prefix} → ${ns.iri}`, value: ns.id })),
)
async function openCreate() {
  if (!canEdit.value) return
  const context = selection
  const session = ++createSession
  createNamespace.value = null
  createName.value = ''
  createLabelZh.value = ''
  createError.value = ''
  createdResourceId.value = null
  if (!namespaceList.value.length) {
    try {
      const namespaces = await namespacesApi.list()
      if (!context || !isCurrentSelection(context) || session !== createSession) return
      namespaceList.value = namespaces
    } catch (err) {
      if (context && isCurrentSelection(context) && session === createSession)
        createError.value = toMessage(err)
    }
  }
  if (context && isCurrentSelection(context) && session === createSession) showCreate.value = true
}
async function submitCreate() {
  if (!canEdit.value || createLoading.value || createValidating.value) return
  const context = selection
  const session = createSession
  const snapshot = JSON.stringify(createModel.value)
  createValidating.value = true
  try {
    if (createForm.value) await createForm.value.validate()
    else {
      for (const path of Object.keys(createRules.value)) {
        if (
          await validateFieldValue(
            readField(createModel.value, path),
            fieldRules(createRules.value, path),
            t('common.required'),
          )
        )
          return
      }
    }
  } catch {
    return
  } finally {
    if (session === createSession) createValidating.value = false
  }
  if (
    !context ||
    !isCurrentSelection(context) ||
    session !== createSession ||
    !canEdit.value ||
    snapshot !== JSON.stringify(createModel.value)
  )
    return
  createLoading.value = true
  createError.value = ''
  try {
    const labelZh = createLabelZh.value.trim() || createName.value.trim()
    const created =
      createdResourceId.value === null
        ? await entityTypesApi.create({
            name: createName.value.trim(),
            namespace_id: createNamespace.value!,
            label_i18n: { 'zh-CN': labelZh },
          })
        : null
    if (!isCurrentSelection(context) || session !== createSession) return
    if (created) {
      createdResourceId.value = created.id
      entityTypes.value = [
        ...entityTypes.value.filter((item) => item.id !== created.id),
        {
          ...created,
          data_prop_count: created.data_props?.length ?? 0,
          relation_count: 0,
          has_violation: false,
        },
      ]
    }
    if (!context || !isCurrentSelection(context)) return
    const added = await addToCanvas(createdResourceId.value!)
    if (!isCurrentSelection(context)) return
    if (added) showCreate.value = false
    else createError.value = actionError.value || loadError.value
  } catch (err) {
    if (context && isCurrentSelection(context) && session === createSession)
      createError.value = toMessage(err)
  } finally {
    if (session === createSession) createLoading.value = false
  }
}

async function removeFromCanvas(resourceId: number) {
  const ref = refs.value.find((r) => r.resource_id === resourceId)
  if (!ref) return
  await updateOntology((id, revision) => ontologyApi.removeRef(id, ref.id, revision))
}

async function publish() {
  const context = selection
  const updated = await updateOntology((id, revision) => ontologyApi.publish(id, revision))
  if (updated && context && isCurrentSelection(context)) {
    message.success(t('common.publish'))
  }
}

// ── 选中节点的数据属性 ─────────────────────────────────────

/** 画布节点只带 brief，装配时要看这个类型有哪些属性，得按需取详情。 */
const typeDetailError = ref('')
watch([selectedKey, frozenRevision], async ([key], _oldKey, onCleanup) => {
  typeDetail.value = null
  typeDetailError.value = ''
  typeDetailLoading.value = false
  if (key) inspectorOpen.value = true
  const context = selection
  if (frozenRevision.value !== null || !key || key.startsWith('rel-') || key.startsWith('domain-'))
    return
  const id = Number(key)
  if (!Number.isSafeInteger(id) || id <= 0) return
  const request = new AbortController()
  onCleanup(() => request.abort())
  typeDetailLoading.value = true
  try {
    const info = await entityTypesApi.get(id, request.signal)
    if (alive && context === selection && selectedKey.value === key && !request.signal.aborted)
      typeDetail.value = info
  } catch (err) {
    if (!request.signal.aborted && context === selection) typeDetailError.value = toMessage(err)
  } finally {
    if (!request.signal.aborted && context === selection) typeDetailLoading.value = false
  }
})

// ── 资产层校验（A01–A08）──────────────────────────────────

/**
 * 装配完最需要知道的是「能不能发布」。后端 `POST /validation/ontologies/{id}`
 * 跑的就是资产层那 8 项检查，这里把四态结果直接摊在设计器里。
 */
async function runValidation() {
  const context = selection
  const id = ontologyId.value
  if (id === null || !context || !canValidate.value || validating.value || loading.value) return
  const editRevision = detail.value?.edit_revision
  const viewedRevision = frozenRevision.value
  const generation = ++validationGeneration
  const stillCurrent = () =>
    isCurrentSelection(context) &&
    generation === validationGeneration &&
    frozenRevision.value === viewedRevision &&
    (viewedRevision !== null || detail.value?.edit_revision === editRevision)
  validating.value = true
  validationError.value = ''
  validationReport.value = null
  validationResults.value = []
  showValidation.value = true
  try {
    const report = await validationApi.validateOntology(
      id,
      viewedRevision === null
        ? { target: 'WORKING' }
        : { target: 'PUBLISHED', revision: viewedRevision },
    )
    if (!stillCurrent()) return
    const results = await validationApi.getResults(report.report_id)
    if (!stillCurrent()) return
    validationReport.value = report
    validationResults.value = results
  } catch (err) {
    if (!stillCurrent()) return
    validationError.value = toMessage(err)
    validationReport.value = null
    validationResults.value = []
  } finally {
    if (stillCurrent()) validating.value = false
  }
}

const VALIDATION_STATE_VAR: Record<string, string> = {
  PASS: 'var(--status-pass)',
  VIOLATION: 'var(--status-violation)',
  NA: 'var(--status-na)',
  NOT_RUN: 'var(--status-not-run)',
}

function validationSummaryText(report: ValidationReport): string {
  const s = report.summary
  return t('designer.validationSummary', {
    pass: s.pass,
    violation: s.violation,
    na: s.na,
    notRun: s.not_run,
  })
}

/** 校验项名称走 i18n（A01–A08 文案在 report.checks 里）；未见过的码原样显示。 */
function checkLabel(code: string): string {
  const key = `report.checks.${code}`
  return te(key) ? t(key) : code
}

const unconfiguredLabels = computed(() =>
  unconfiguredRelationIds.value.map((rid) =>
    poolLabel(relationById.value[rid]?.label_i18n, String(rid)),
  ),
)
usePageIdentity(() => detail.value?.name)
const validationReadouts = computed(() =>
  (['PASS', 'VIOLATION', 'NA', 'NOT_RUN'] as const).map((state) => ({
    state,
    count:
      validationReport.value?.summary[
        state.toLowerCase() as 'pass' | 'violation' | 'na' | 'not_run'
      ],
  })),
)

async function closeCreate() {
  if (createLoading.value || !(await confirmDiscard())) return
  showCreate.value = false
  createName.value = ''
  createLabelZh.value = ''
}
async function closeRules() {
  if (working.value || !(await confirmDiscard())) return
  selectedRules.value = [...savedRules.value]
  showRules.value = false
}
function beforeUnload(event: BeforeUnloadEvent) {
  if (!layoutDirty.value && !createDirty.value && !rulesDirty.value) return
  event.preventDefault()
  event.returnValue = ''
}
onBeforeRouteLeave(async () => {
  if (saving.value || working.value || createLoading.value) return false
  return confirmDiscard()
})
onMounted(() => {
  if (typeof window !== 'undefined') {
    window.addEventListener('beforeunload', beforeUnload)
    window.addEventListener('resize', onViewportResize)
    onViewportResize()
  }

  // 支持从本体列表带 ?ontology=<id> 进来，直接定位到那一个本体
  const requested = Number(route.query.ontology)
  if (Number.isSafeInteger(requested) && requested > 0) ontologyId.value = requested
  void loadCatalog()
})

onBeforeUnmount(() => {
  alive = false
  if (typeof window !== 'undefined') {
    window.removeEventListener('beforeunload', beforeUnload)
    window.removeEventListener('resize', onViewportResize)
  }
  answerDiscard(false)
  catalogController?.abort()
  selection?.controller.abort()
  canvasObserver?.disconnect()
  onPointerCancel()
})
</script>

<template>
  <FocusScope
    :trapped="focusMode"
    :loop="focusMode"
    :present="focusMode"
    as-child
    @mount-auto-focus="$event.preventDefault()"
    @unmount-auto-focus="$event.preventDefault()"
  >
    <section class="designer" :class="{ 'focus-mode': focusMode }" @keydown.esc="onEditorEscape">
      <!-- Capture-Escape must return the dragged layout to its original state even
         if focus moved from the canvas to the toolbar while the pointer is held. -->
      <!-- 顶栏：本体选择 + 布局 + 发布 -->
      <header class="studio-identity">
        <UiButton
          variant="ghost"
          size="small"
          :aria-expanded="poolOpen && !focusMode"
          aria-controls="designer-resources"
          @click="toggleResources"
          >{{ t('designer.resourcePool') }}</UiButton
        >
        <div class="studio-object">
          <h1 :title="detail?.iri">{{ detail?.name || t('designerUi.title') }}</h1>
          <div v-if="detail" class="object-meta">
            <span>{{
              t('designerUi.versions', {
                published: detail.current_revision,
                edit: detail.edit_revision,
              })
            }}</span>
            <span v-if="!roleCanWrite">{{ t('designerUi.viewer') }}</span>
            <span v-else-if="frozenRevision !== null">{{ t('designerUi.frozenReadOnly') }}</span>
            <span v-else role="status">{{
              t(
                saving
                  ? 'designer.saving'
                  : layoutDirty
                    ? 'designerUi.unsavedLayout'
                    : 'designerUi.layoutSaved',
              )
            }}</span>
          </div>
        </div>
        <div class="studio-actions">
          <UiButton
            size="small"
            :disabled="!canValidate"
            :loading="validating"
            @click="runValidation"
          >
            {{ t('designer.runValidation') }}
          </UiButton>
          <UiButton size="small" :disabled="!canEdit" @click="showAi = true">
            {{ t('designer.aiAssist') }}
          </UiButton>
          <UiButton
            size="small"
            :disabled="!canEdit || createDirty || rulesDirty || detail?.status === 'ARCHIVED'"
            @click="showModeling = true"
            >{{ t('modeling.open') }}</UiButton
          >
          <UiButton size="small" type="primary" :disabled="!canEdit" @click="publish">
            {{ t('common.publish') }}
          </UiButton>
          <UiButton
            size="small"
            :aria-expanded="inspectorOpen && !!selected"
            :disabled="!selected"
            aria-controls="designer-inspector"
            @click="toggleInspector"
            >{{ t('designer.inspector') }}</UiButton
          >
          <UiButton size="small" :aria-pressed="focusMode" @click="focusMode = !focusMode">
            {{ t(focusMode ? 'graphStudio.exitFocus' : 'graphStudio.focus') }}
          </UiButton>
        </div>
      </header>

      <!-- 资产层校验结果：装配完在这里就能看出能不能发布 -->
      <section v-if="showValidation" class="validation">
        <header class="validation-head">
          <b>{{ t('designer.validationTitle') }}</b>
          <span v-if="validationReport" class="validation-summary mono">
            {{ validationSummaryText(validationReport) }}
          </span>
          <span class="spacer" />
          <UiButton
            variant="ghost"
            size="small"
            attr-type="button"
            class="validation-close"
            @click="showValidation = false"
          >
            {{ t('common.close') }}
          </UiButton>
        </header>
        <UiAlert v-if="validationError" type="error" role="alert">{{ validationError }}</UiAlert>
        <p v-else-if="validating && !validationResults.length" role="status">
          {{ t('common.loading') }}
        </p>
        <ul v-else-if="validationResults.length" class="validation-list">
          <li
            v-for="(item, index) in validationResults"
            :key="`${item.check_code}-${item.focus_node ?? 'root'}-${index}`"
          >
            <span class="check-tag" :style="{ '--dot': VALIDATION_STATE_VAR[item.state] }">
              <i class="status-dot" />
              {{ t(`report.states.${item.state}`) }}
            </span>
            <span class="check-name">{{ checkLabel(item.check_code) }}</span>
            <span v-if="item.message" class="check-msg">{{ item.message }}</span>
          </li>
        </ul>
      </section>

      <UiAlert v-if="catalogError" type="error" role="alert">
        {{ catalogError }}
        <UiButton :loading="catalogLoading" @click="() => loadCatalog()">{{
          t('graph.refresh')
        }}</UiButton>
      </UiAlert>
      <UiAlert v-if="loadError || actionError" type="error" role="alert">
        {{ loadError || actionError }}
        <UiButton :loading="loading" @click="ontologyId !== null && selectOntology(ontologyId)">
          {{ t('graph.refresh') }}
        </UiButton>
      </UiAlert>
      <UiAlert v-if="saveError" type="error" role="alert">
        {{ saveError }}
        <UiButton :disabled="!canEdit" @click="persist">{{ t('common.save') }}</UiButton>
      </UiAlert>
      <UiAlert v-if="historyError" type="error" role="alert">
        {{ t('designerUi.snapshotUnavailable') }} {{ historyError }}
        <UiButton @click="frozenRevision !== null && changeRevision(frozenRevision)">{{
          t('graph.refresh')
        }}</UiButton>
      </UiAlert>
      <p v-if="catalogLoading" role="status">{{ t('common.loading') }}</p>

      <div v-if="!catalogLoading && !catalogError && !ontologies.length" class="no-ontology">
        <!-- 空态要给出可执行动作，而不是只说「去创建一个」却没有入口 -->
        <UiEmpty :description="t('designer.noOntologyHint')">
          <template #extra>
            <UiButton
              type="primary"
              size="small"
              :disabled="!roleCanWrite"
              @click="router.push({ name: 'ontologies' })"
            >
              {{ t('ontology.create') }}
            </UiButton>
          </template>
        </UiEmpty>
      </div>

      <div v-else-if="ontologies.length" class="body">
        <!-- 左：资源面板 -->
        <aside
          v-if="poolOpen && !focusMode"
          id="designer-resources"
          class="panel pool"
          :aria-label="t('designer.resourcePool')"
        >
          <div class="panel-head">
            <span>{{ t('designer.resourcePool') }}</span>
            <UiButton size="tiny" :disabled="!canEdit" @click="openCreate">
              {{ t('designer.createOnCanvas') }}
            </UiButton>
            <UiButton
              variant="ghost"
              size="small"
              class="panel-close"
              attr-type="button"
              :aria-label="t('designerUi.closeResources')"
              @click="poolOpen = false"
            >
              {{ t('common.close') }}
            </UiButton>
          </div>
          <div class="identity-context">
            <UiSelect
              :value="ontologyId"
              :options="ontologies.map((o) => ({ label: o.name, value: o.id }))"
              :placeholder="t('designer.selectOntology')"
              :loading="catalogLoading"
              :disabled="catalogLoading || !!catalogError"
              class="onto-select"
              :aria-label="t('designer.selectOntology')"
              @update:value="selectOntology"
            />
            <span v-if="detail" class="status-tag" :style="{ '--dot': STATUS_VAR[detail.status] }">
              <i class="status-dot" />
              {{ t(`resourceStatus.${detail.status}`) }}
            </span>
            <UiSelect
              v-if="detail"
              :value="frozenRevision ?? 0"
              :options="revisionOptions"
              :aria-label="t('designerUi.versionView')"
              :disabled="saving || working"
              size="small"
              class="revision-select"
              @update:value="changeRevision"
            />
          </div>
          <UiInput
            v-model:value="poolSearch"
            class="pool-search"
            clearable
            :placeholder="t('designerUi.searchResources')"
            :aria-label="t('designerUi.searchResources')"
          />
          <div class="pool-body">
            <UiButton size="small" :disabled="!canEdit" @click="openRules">{{
              t('designer.configureRules')
            }}</UiButton>
            <div class="pool-group">
              <span>{{ t('designer.inCanvas') }}</span>
              <span class="mono pool-count">{{ canvasTotal }}</span>
            </div>
            <template v-for="cat in filteredCanvasCategories" :key="`c-${cat.kind}`">
              <div v-if="cat.items.length" class="pool-subgroup">
                <span>{{ cat.label }}</span>
                <span class="mono">{{ cat.items.length }}</span>
              </div>
              <UiButton
                v-for="item in cat.items"
                :key="`c-${cat.kind}-${item.id}`"
                variant="ghost"
                size="small"
                attr-type="button"
                class="pool-item on"
                :class="{ active: isPoolItemActive(cat.kind, item.id) }"
                @click="selectPoolItem(cat.kind, item.id)"
              >
                <i
                  class="dot"
                  :style="{
                    background:
                      cat.kind === 'type'
                        ? 'var(--graph-entity)'
                        : cat.kind === 'relation'
                          ? 'var(--graph-relation)'
                          : 'var(--foreground-secondary)',
                  }"
                />
                <span class="pool-name">{{ item.label }}</span>
                <!-- 端点没全部入画布的关系画不出连线，明确标出来而不是静默消失 -->
                <span v-if="item.unconfigured" class="pool-tag">
                  {{ t('designer.legendUnconfigured') }}
                </span>
              </UiButton>
            </template>
            <div v-if="!canvasTotal" class="pool-empty">{{ t('common.empty') }}</div>

            <div v-if="frozenRevision === null" class="pool-group">
              {{ t('designer.notInCanvas') }}
            </div>
            <template
              v-for="cat in frozenRevision === null ? filteredAvailableCategories : []"
              :key="`a-${cat.kind}`"
            >
              <div v-if="cat.items.length" class="pool-subgroup">
                <span>{{ cat.label }}</span>
                <span class="mono">{{ cat.items.length }}</span>
              </div>
              <UiButton
                v-for="item in cat.items"
                :key="`a-${cat.kind}-${item.id}`"
                variant="ghost"
                size="small"
                attr-type="button"
                class="pool-item addable"
                :disabled="
                  !canEdit || (cat.kind === 'domain' && !domainById[item.id]?.current_revision)
                "
                :title="cat.kind === 'domain' ? t('designer.addDomainMembersHint') : undefined"
                @click="addPoolItem(cat.kind, item.id)"
              >
                <i class="dot" :style="{ background: STATUS_VAR[item.status] }" />
                <span class="pool-name">{{ item.label }}</span>
                <span
                  class="plus"
                  :aria-label="
                    t(cat.kind === 'domain' ? 'designer.addDomainMembers' : 'designer.addToCanvas')
                  "
                />
              </UiButton>
            </template>
          </div>
          <div class="pool-foot">
            {{ t(frozenRevision === null ? 'designerUi.workingHint' : 'designerUi.frozenHint') }}
          </div>
        </aside>
        <!-- B-7 画布直接建模：新建实体类型弹窗 -->
        <UiModal
          :show="showCreate"
          preset="dialog"
          :title="t('designer.createOnCanvas')"
          :mask-closable="false"
          :close-on-esc="false"
          @update:show="(value: boolean) => !value && closeCreate()"
        >
          <FormContainer
            ref="createForm"
            :model="createModel"
            :rules="createRules"
            :submitting="createLoading"
            @submit="submitCreate"
          >
            <FormField path="namespace" :label="t('designer.createNamespace')">
              <UiSelect
                v-model:value="createNamespace"
                :options="namespaceOptions"
                :placeholder="t('designer.createNamespacePlaceholder')"
                :disabled="createLoading || createdResourceId !== null"
                filterable
              />
            </FormField>
            <FormField path="name" :label="t('common.name')">
              <UiInput
                v-model:value="createName"
                :placeholder="t('designer.createNamePlaceholder')"
                :disabled="createLoading || createdResourceId !== null"
              />
            </FormField>
            <FormField path="labelZh" :label="t('common.labelZh')">
              <UiInput
                v-model:value="createLabelZh"
                :placeholder="t('designer.createLabelPlaceholder')"
                :disabled="createLoading || createdResourceId !== null"
              />
            </FormField>
          </FormContainer>
          <UiAlert v-if="createError" type="error" class="feedback">{{ createError }}</UiAlert>
          <template #action>
            <UiButton :disabled="createLoading" @click="closeCreate">{{
              t('common.cancel')
            }}</UiButton>
            <UiButton
              type="primary"
              :loading="createLoading"
              :disabled="!canEdit || createValidating"
              @click="submitCreate"
              >{{ t('common.create') }}</UiButton
            >
          </template>
        </UiModal>

        <UiDrawer
          :show="showRules"
          :width="440"
          :mask-closable="false"
          :close-on-esc="false"
          @update:show="(value: boolean) => !value && closeRules()"
        >
          <UiDrawerContent :title="t('designer.configureRules')" closable>
            <p>{{ t('designer.rulesHint') }}</p>
            <UiAlert v-if="ruleError" type="error">{{ ruleError }}</UiAlert>
            <UiButton v-if="ruleError" @click="openRules">{{ t('graph.refresh') }}</UiButton>
            <FormContainer
              ref="rulesForm"
              :model="rulesModel"
              :rules="rulesValidation"
              :submitting="working"
              @submit="saveRules"
            >
              <FormField path="selectedRules" :label="t('designer.configureRules')">
                <UiSelect
                  v-model:value="selectedRules"
                  :options="ruleOptions"
                  multiple
                  filterable
                  :loading="ruleLoading"
                  :disabled="ruleLoading || !!ruleError || !canEdit"
                  :aria-label="t('designer.configureRules')"
                />
              </FormField>
            </FormContainer>
            <template #footer>
              <UiButton :disabled="working" @click="closeRules">{{ t('common.cancel') }}</UiButton>
              <UiButton
                type="primary"
                :loading="working"
                :disabled="ruleLoading || !!ruleError || !canEdit || rulesValidating"
                @click="saveRules"
                >{{ t('common.save') }}</UiButton
              >
            </template>
          </UiDrawerContent>
        </UiDrawer>

        <!-- 中：画布 -->
        <div
          ref="canvasEl"
          class="canvas"
          :class="{ panning: !!panning }"
          tabindex="0"
          :aria-label="t('designerUi.canvas')"
          @pointerdown="onBackgroundDown"
          @pointermove="onNodeMove"
          @pointerup="onNodeUp"
          @pointercancel="onPointerCancel"
          @lostpointercapture="onPointerCancel"
          @keydown="onCanvasKey"
          @wheel="onWheel"
        >
          <div
            v-if="detail"
            class="view-toolbar"
            role="toolbar"
            :aria-label="t('graphUi.canvasTools')"
            @pointerdown.stop
            @wheel.stop
          >
            <span class="canvas-mode">{{
              t(frozenRevision === null ? 'designerUi.workingContent' : 'designerUi.frozenContent')
            }}</span>
            <span class="spacer" />
            <UiButton size="small" :disabled="!canEdit || !nodes.length" @click="autoLayout">{{
              t('designer.autoLayout')
            }}</UiButton>
            <UiButton
              size="small"
              :disabled="!canEdit || !layoutDirty"
              :loading="saving"
              @click="persist"
              >{{ t('designerUi.saveLayout') }}</UiButton
            >
            <UiButton v-if="layoutDirty" size="small" :disabled="!canEdit" @click="cancelLayout">{{
              t('designerUi.cancelLayout')
            }}</UiButton>
          </div>
          <UiSpin :show="loading || historyLoading" class="canvas-spin">
            <div ref="worldEl" class="world" :style="worldStyle">
              <svg class="edges" :width="WORLD_W" :height="WORLD_H">
                <defs>
                  <marker
                    id="edge-arrow"
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
                      stroke="var(--graph-relation)"
                      stroke-width="1.5"
                      stroke-linecap="round"
                    />
                  </marker>
                </defs>

                <!-- 业务域分区：画在连线与节点之下，让「域」在画布上可见 -->
                <g v-for="band in domainBands" :key="`band-${band.id}`" class="band">
                  <rect
                    :x="band.x"
                    :y="band.y"
                    :width="band.w"
                    :height="band.h"
                    rx="14"
                    class="band-rect"
                    :class="{ 'band-rect--empty': band.count === 0 }"
                  />
                  <text :x="band.x + 14" :y="band.y + 17" class="band-label">
                    {{ band.label }} · {{ band.count }}
                  </text>
                </g>

                <g
                  v-for="edge in edges"
                  :key="edge.key"
                  class="edge"
                  :class="{ selected: selectedKey === edge.key }"
                >
                  <path
                    class="edge-hit"
                    :d="edge.d"
                    fill="none"
                    stroke="transparent"
                    stroke-width="18"
                    pointer-events="stroke"
                    tabindex="0"
                    role="button"
                    :data-selection="edge.key"
                    :aria-label="t('designer.selectRelation', { name: edge.label })"
                    @click.stop="selectRelation(edge.id)"
                    @keydown.enter.stop="selectRelation(edge.id)"
                    @keydown.space.prevent.stop="selectRelation(edge.id)"
                  />
                  <path
                    :d="edge.d"
                    fill="none"
                    :stroke="
                      selectedKey === edge.key
                        ? 'var(--action-primary)'
                        : edge.status === 'PUBLISHED'
                          ? 'var(--graph-relation)'
                          : 'var(--border-emphasis)'
                    "
                    :stroke-width="selectedKey === edge.key ? 2.6 : 1.6"
                    marker-end="url(#edge-arrow)"
                  />
                  <g
                    class="edge-label-button"
                    role="button"
                    :aria-label="t('designer.selectRelation', { name: edge.label })"
                    @click.stop="selectRelation(edge.id)"
                  >
                    <title>{{ edge.label }}</title>
                    <rect
                      :x="edge.lx - edge.labelWidth / 2"
                      :y="edge.ly - 13"
                      :width="edge.labelWidth"
                      height="26"
                      rx="5"
                    />
                    <text :x="edge.lx" :y="edge.ly + 4" text-anchor="middle" class="edge-label">
                      {{ edge.displayLabel }}
                    </text>
                  </g>
                </g>
              </svg>

              <div
                v-for="node in nodes"
                :key="node.key"
                class="node"
                role="button"
                tabindex="0"
                :aria-label="node.label"
                :aria-pressed="selectedKey === node.key"
                :data-selection="node.key"
                :title="node.label + '\n' + node.iri"
                :class="{ on: selectedKey === node.key, dragging: dragging?.key === node.key }"
                :style="{
                  left: `${node.x}px`,
                  top: `${node.y}px`,
                  width: `${NODE_W}px`,
                  height: `${NODE_H}px`,
                }"
                @pointerdown="onNodeDown(node.key, $event)"
                @keydown.enter.stop="selectNode(node.key)"
                @keydown.space.prevent.stop="selectNode(node.key)"
              >
                <span class="node-head">
                  <svg class="node-icon" viewBox="0 0 20 20" aria-hidden="true">
                    <path d="m10 2 7 4v8l-7 4-7-4V6Zm0 8 7-4M10 10 3 6m7 4v8" />
                  </svg>
                  <span class="node-label">{{ node.label }}</span>
                </span>
                <span class="node-meta">{{ node.name }}</span>
                <span class="node-status" :style="{ color: STATUS_VAR[node.status] }">{{
                  t(`resourceStatus.${node.status}`)
                }}</span>
              </div>

              <div
                v-if="!loading && !historyLoading && !historyError && !loadError && !nodes.length"
                class="world-empty"
              >
                <div class="world-empty-title">{{ t('designer.emptyCanvas') }}</div>
                <div class="world-empty-hint">{{ t('designer.emptyCanvasHint') }}</div>
              </div>
            </div>
          </UiSpin>

          <div v-if="unconfiguredLabels.length" class="canvas-warn">
            {{ t('designer.unconfiguredHint', { names: unconfiguredLabels.join('、') }) }}
          </div>

          <div class="canvas-tools" @pointerdown.stop @wheel.stop>
            <UiButton
              variant="ghost"
              size="small"
              attr-type="button"
              :aria-label="t('designer.zoomOut')"
              @click="stepZoom(-0.1)"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
                <path d="M3 8h10" fill="none" stroke="currentColor" stroke-width="1.5" />
              </svg>
            </UiButton>
            <span class="mono zoom-val">{{
              t('designer.zoomLevel', { percent: Math.round(zoom * 100) })
            }}</span>
            <UiButton
              variant="ghost"
              size="small"
              attr-type="button"
              :aria-label="t('designer.zoomIn')"
              @click="stepZoom(0.1)"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
                <path d="M3 8h10M8 3v10" fill="none" stroke="currentColor" stroke-width="1.5" />
              </svg>
            </UiButton>
            <span class="divider" />
            <UiButton variant="ghost" size="small" attr-type="button" @click="fitView">{{
              t('designer.fitView')
            }}</UiButton>
            <UiButton
              variant="ghost"
              size="small"
              attr-type="button"
              :disabled="!previousCamera"
              @click="restoreView"
            >
              {{ t('designerUi.restoreView') }}
            </UiButton>
            <UiButton
              :ref="setLegendButton"
              variant="ghost"
              size="small"
              attr-type="button"
              :aria-expanded="legendOpen"
              @click="legendOpen = !legendOpen"
            >
              {{ t('designerUi.legend') }}
            </UiButton>
          </div>

          <div v-if="legendOpen" class="legend">
            <div><span class="lg-line solid" />{{ t('designer.legendRelation') }}</div>
            <div>{{ t('designerUi.legendStatus') }}</div>
            <div><span class="lg-line warn" />{{ t('designer.legendUnconfigured') }}</div>
          </div>
        </div>

        <!-- 右：属性检查器 -->
        <aside
          v-if="inspectorOpen && selected && !focusMode"
          id="designer-inspector"
          class="panel inspector"
          :aria-label="t('designer.inspector')"
        >
          <div class="panel-head">
            <span>{{ t('designer.inspector') }}</span
            ><UiButton
              variant="ghost"
              size="small"
              class="panel-close"
              attr-type="button"
              @click="closeInspector"
            >
              {{ t('common.close') }}
            </UiButton>
          </div>
          <div v-if="selected" class="inspect-body">
            <div class="inspect-title">
              <i
                class="dot"
                :style="{
                  background:
                    selected.kind === 'entity'
                      ? 'var(--graph-entity)'
                      : selected.kind === 'relation'
                        ? 'var(--graph-relation)'
                        : 'var(--foreground-secondary)',
                  width: '8px',
                  height: '8px',
                }"
              />
              <b>{{ selected.label }}</b>
              <span class="status-tag" :style="{ '--dot': STATUS_VAR[selected.status] }">
                <i class="status-dot" />
                {{ t(`resourceStatus.${selected.status}`) }}
              </span>
            </div>
            <span class="iri inspect-iri">{{ selected.iri }}</span>
            <p class="resource-context">
              {{
                frozenRevision !== null
                  ? t('designerUi.frozenResource', { revision: inspectedRevision })
                  : pinnedRevision
                    ? t('designerUi.livePinnedResource', { revision: pinnedRevision })
                    : t('designerUi.liveResource')
              }}
            </p>

            <dl class="inspect-kv">
              <dt>{{ t('common.name') }}</dt>
              <dd class="mono">{{ selected.name }}</dd>
              <template v-if="selected.kind === 'entity'">
                <dt>{{ t('designer.nodePosition') }}</dt>
                <dd class="mono">
                  {{ t('designer.positionValue', { x: selected.x, y: selected.y }) }}
                </dd>
                <dt>{{ t('designer.domainMembership') }}</dt>
                <dd>
                  {{
                    selected.domainLabels.length
                      ? selected.domainLabels.join(' · ')
                      : t('common.noneValue')
                  }}
                </dd>
              </template>
              <template v-else-if="selected.kind === 'relation'">
                <dt>{{ t('designer.relationDomain') }}</dt>
                <dd>{{ selected.domainLabel || t('common.noneValue') }}</dd>
                <dt>{{ t('designer.relationRange') }}</dt>
                <dd>{{ selected.rangeLabel || t('common.noneValue') }}</dd>
              </template>
              <template v-else>
                <dt>{{ t('designer.domainMembers') }}</dt>
                <dd class="mono">{{ selected.memberCount }}</dd>
              </template>
            </dl>

            <!-- 数据属性清单：装配时最需要知道这个类型有哪些属性（映射阶段依赖它） -->
            <div v-if="selected.kind === 'entity'" class="inspect-props">
              <div class="inspect-props-head">
                <span>{{ t('entityType.dataProps') }}</span>
                <span v-if="!typeDetailLoading && !typeDetailError" class="mono">{{
                  inspectedProperties.length
                }}</span>
              </div>
              <p v-if="typeDetailLoading" class="inspect-empty">{{ t('common.loading') }}</p>
              <UiAlert v-else-if="typeDetailError" type="error">{{ typeDetailError }}</UiAlert>
              <template v-else-if="inspectedProperties.length">
                <ul class="prop-list">
                  <li v-for="prop in inspectedProperties" :key="prop.name">
                    <span class="mono prop-name">{{ prop.name }}</span>
                    <span class="prop-type">{{ t(`entityProps.datatypes.${prop.datatype}`) }}</span>
                  </li>
                </ul>
              </template>
              <p v-else class="inspect-empty">{{ t('common.empty') }}</p>
            </div>

            <p v-if="selected.kind === 'domain'" class="inspect-empty">
              {{ t('designer.domainMembersHint') }}
            </p>
            <UiButton
              v-else
              size="small"
              block
              :disabled="!canEdit"
              @click="removeFromCanvas(selected.id)"
            >
              {{ t('designer.removeFromCanvas') }}
            </UiButton>
          </div>
          <div v-else class="inspect-empty">{{ t('designer.selectNode') }}</div>
          <section class="inspection-validation">
            <header>{{ t('designer.validationTitle') }}</header>
            <div class="validation-readouts">
              <div
                v-for="entry in validationReadouts"
                :key="entry.state"
                :style="{ '--state': VALIDATION_STATE_VAR[entry.state] }"
              >
                <code>{{ entry.state }}</code
                ><strong>{{ entry.count ?? '—' }}</strong>
                <span>{{ t(`report.states.${entry.state}`) }}</span>
              </div>
            </div>
            <p v-if="!validationReport">{{ t('studio.validationPending') }}</p>
            <UiButton
              size="small"
              :aria-expanded="showValidation"
              @click="showValidation = !showValidation"
              >{{ t('report.results') }}</UiButton
            >
          </section>
        </aside>
      </div>
      <footer v-if="detail" class="canvas-status">
        <span>{{
          t('designerUi.scope', {
            nodes: nodes.length,
            edges: edges.length,
            missing: unconfiguredRelationIds.length,
          })
        }}</span>
        <span>{{ t('designerUi.gestures') }}</span>
      </footer>
      <UiModal
        :show="showDiscard"
        preset="dialog"
        :title="t('designerUi.unsavedTitle')"
        :content="t('designerUi.unsavedPrompt')"
        :positive-text="t('designerUi.discard')"
        :negative-text="t('designerUi.keepEditing')"
        :mask-closable="false"
        :close-on-esc="false"
        @positive-click="answerDiscard(true)"
        @negative-click="answerDiscard(false)"
        @close="answerDiscard(false)"
      />
      <UiDrawer v-model:show="showModeling" width="min(860px, 100vw)" placement="right">
        <UiDrawerContent :title="t('modeling.open')" closable>
          <AiModeling
            v-if="
              showModeling &&
              detail &&
              ontologyId !== null &&
              roleCanWrite &&
              frozenRevision === null &&
              detail.status !== 'ARCHIVED'
            "
            :ontology-id="ontologyId"
            :draft-id="detail.working_draft_id"
            :base-edit-revision="detail.edit_revision"
            @applied="modelingApplied"
          />
        </UiDrawerContent>
      </UiDrawer>
      <!-- AI 补全建议（V-DS-05）：逐条人工确认后才写入草稿资源 -->
      <UiDrawer v-model:show="showAi" :width="460" placement="right">
        <UiDrawerContent :title="t('designer.aiAssist')" closable>
          <AiSuggestions
            v-if="showAi && ontologyId !== null && roleCanWrite && frozenRevision === null"
            kind="ONTOLOGY_COMPLETION"
            :title="t('designer.aiAssist')"
            :target-id="ontologyId"
            @applied="() => void loadCatalog()"
          />
        </UiDrawerContent>
      </UiDrawer>
    </section>
  </FocusScope>
</template>

<style scoped>
.studio-identity {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  flex: none;
  margin: 0;
  padding: 12px 24px;
  background: var(--surface-panel);
  border-bottom: 1px solid var(--border-default);
}
.studio-object {
  flex: 1;
  min-width: 160px;
}
.studio-object h1 {
  margin: 0;
  font-size: 18px;
  overflow-wrap: anywhere;
}
.object-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  margin-top: 4px;
  color: var(--foreground-secondary);
  font-size: var(--font-caption);
}
.studio-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.identity-context {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  padding: 12px;
  border-bottom: 1px solid var(--border-muted);
}
.inspection-validation {
  margin-top: auto;
  padding: var(--space-4);
  border-top: 1px solid var(--border-default);
  display: grid;
  gap: var(--space-3);
  background: var(--surface-inset);
}
.inspection-validation header {
  color: var(--foreground-primary);
  font-size: var(--font-caption);
  font-weight: 600;
}
.inspection-validation p {
  margin: 0;
  color: var(--foreground-secondary);
  font-size: var(--font-caption);
}
.validation-readouts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-2);
}
.validation-readouts > div {
  padding: var(--space-2);
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 5px;
  border: 1px solid var(--border-default);
  background: var(--surface-panel);
}
.validation-readouts code,
.validation-readouts strong {
  color: var(--state);
  font-size: var(--font-caption);
}
.validation-readouts span {
  grid-column: 1 / -1;
  font-size: var(--font-caption);
  color: var(--foreground-secondary);
}
.designer {
  display: flex;
  flex-direction: column;
  flex: 1;
  height: 100%;
  min-height: 0;
  min-width: 0;
  background: var(--surface-panel);
  overflow: hidden;
}
.designer.focus-mode {
  position: fixed;
  inset: 0;
  z-index: calc(var(--z-navigation) + 1);
}

.toolbar {
  display: flex;
  flex: none;
  gap: var(--space-2);
  align-items: center;
  padding: 10px var(--space-4);
  background: var(--surface-panel);
  border-bottom: 1px solid var(--border-muted);
  flex-wrap: wrap;
}
.toolbar h1 {
  margin: 0 8px 0 0;
  font-size: var(--font-h2);
}
.object-bar,
.view-toolbar,
.canvas-status {
  display: flex;
  flex: none;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  padding: 8px 16px;
  color: var(--foreground-secondary);
  background: var(--surface-panel);
  border-bottom: 1px solid var(--border-default);
  font-size: var(--font-caption);
}
.object-mode {
  color: var(--foreground-primary);
  font-weight: 500;
}
.revision-select {
  width: 100%;
}
.readonly-note {
  color: var(--status-na);
}
.view-toolbar {
  position: absolute;
  z-index: 2;
  top: 16px;
  left: 16px;
  right: 16px;
  padding: 0;
  border: 0;
  background: transparent;
  pointer-events: none;
}
.view-toolbar > :deep(button),
.canvas-mode {
  pointer-events: auto;
  background: var(--surface-panel);
  border: 1px solid var(--border-muted);
  box-shadow: var(--shadow-low);
}
.canvas-mode {
  padding: 6px 10px;
  border-radius: var(--radius-control);
  color: var(--action-primary);
}
.canvas-status {
  justify-content: space-between;
  border-top: 1px solid var(--border-default);
  border-bottom: 0;
}

.onto-select {
  width: 100%;
}

.spacer {
  flex: 1;
}

.saving {
  color: var(--foreground-muted);
  font-size: var(--font-caption);
}

.no-ontology {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
}

.body {
  position: relative;
  display: flex;
  flex: 1;
  min-height: 0;
  min-width: 0;
  gap: 0;
  padding: 0;
  background: var(--surface-background);
}

/* ── 侧栏面板 ───────────────────────────────────────────── */
.panel {
  display: flex;
  flex-direction: column;
  flex: none;
  background: var(--surface-panel);
  border: 0;
  border-radius: 0;
  overflow: hidden;
}

.pool {
  width: 220px;
  border-right: 1px solid var(--border-muted);
}

.inspector {
  width: var(--inspector-width, 300px);
  border-left: 1px solid var(--border-muted);
  overflow: auto;
}

.panel-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 12px 14px;
  color: var(--foreground-secondary);
  font-size: var(--font-caption);
  border-bottom: 1px solid var(--border-muted);
}
.panel-head > span:first-child {
  flex: 1;
}
.pool .panel-head {
  flex-wrap: wrap;
}
.pool .panel-head :deep(button:not(.panel-close)) {
  order: 3;
  flex: 0 0 100%;
}
.panel-close {
  border: 0;
  background: transparent;
  color: var(--foreground-secondary);
  font: inherit;
  cursor: pointer;
  padding: var(--space-1);
}
.pool-search {
  margin: 10px;
  width: calc(100% - 20px);
}
.resource-context {
  margin: 0;
  padding: 10px;
  background: var(--surface-muted);
  border-radius: var(--radius-control);
  font-size: var(--font-caption);
}

.pool-body {
  flex: 1;
  padding: 10px;
  overflow: auto;
}

.pool-group {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 6px;
  color: var(--foreground-muted);
  font-size: var(--font-caption);
}

/* 类型 / 关系 / 域 三个子分组，各带计数 */
.pool-subgroup {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 6px 2px 10px;
  color: var(--foreground-secondary);
  font-size: var(--font-caption);
}

.pool-count {
  color: var(--foreground-muted);
  font-size: var(--font-caption);
}

.pool-item {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  width: 100%;
  padding: 7px 10px;
  margin-bottom: var(--space-1);
  font: inherit;
  font-size: var(--font-caption);
  color: var(--foreground-secondary);
  text-align: left;
  cursor: pointer;
  background: var(--surface-raised);
  border: 1px solid var(--border-muted);
  border-radius: var(--radius-control);
  transition: border-color var(--duration-fast) var(--ease-out);
}

.pool-item:hover {
  border-color: var(--action-primary);
}

/* on = 已在画布；active = 当前选中。两者语义不同，样式也分开 */
.pool-item.on {
  color: var(--foreground-primary);
  background: transparent;
  border-color: transparent;
}

.pool-item.active {
  background: var(--action-soft);
  border-color: var(--action-primary);
}

.pool-tag {
  flex: none;
  margin-left: auto;
  padding: 1px 6px;
  font-size: var(--font-caption);
  color: var(--status-not-run);
  border: 1px solid var(--status-not-run);
  border-radius: var(--radius-pill);
}

.pool-item.addable {
  background: transparent;
  border-color: transparent;
}
.pool-item:disabled {
  cursor: default;
  opacity: 0.65;
}

.pool-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plus {
  margin-left: auto;
  color: var(--foreground-disabled);
}
.plus::before {
  content: '+';
}

.pool-empty {
  padding: 8px 6px;
  color: var(--foreground-disabled);
  font-size: var(--font-caption);
}

.pool-foot {
  padding: 10px 14px;
  color: var(--foreground-muted);
  font-size: var(--font-caption);
  line-height: 1.7;
  border-top: 1px solid var(--border-muted);
}

/* ── 画布 ───────────────────────────────────────────────── */
.canvas {
  position: relative;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  cursor: grab;
  background-color: var(--canvas);
  background-image: radial-gradient(var(--border-default) 1px, transparent 1px);
  background-size: 24px 24px;
  overscroll-behavior: contain;
  touch-action: none;
}
.canvas.panning {
  cursor: grabbing;
}

.canvas-spin {
  height: 100%;
}

.world {
  position: absolute;
  top: 0;
  left: 0;
  transform-origin: 0 0;
}

.edges {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
  overflow: visible;
}

.edge-label {
  font-size: var(--font-small);
  fill: var(--foreground-secondary);
  pointer-events: none;
}
.edge-label-button {
  pointer-events: all;
  cursor: pointer;
}
.edge-label-button rect {
  fill: var(--surface-panel);
  stroke: var(--border-default);
}
.edge.selected .edge-label-button rect {
  fill: var(--action-soft);
  stroke: var(--action-primary);
}
.edge.selected .edge-label {
  fill: var(--action-primary);
}
.edge-hit {
  cursor: pointer;
}
.edge-hit:focus-visible {
  stroke: var(--action-primary);
  stroke-opacity: 0.35;
  stroke-width: 18;
  outline: none;
}

.node {
  position: absolute;
  display: flex;
  flex-direction: column;
  gap: 3px;
  justify-content: center;
  padding: 0 12px;
  cursor: grab;
  background: var(--surface-panel);
  border: 1px solid var(--border-emphasis);
  border-radius: var(--radius-control);
  transition: box-shadow var(--duration-fast) var(--ease-out);
}

.node:hover {
  box-shadow: var(--shadow-raised);
}

.node.on {
  border-color: var(--action-primary);
  box-shadow: var(--glow);
}

.node.dragging {
  cursor: grabbing;
  box-shadow: var(--glow);
}

.node-head {
  display: flex;
  gap: 7px;
  align-items: center;
}

.node-label {
  font-size: var(--font-small);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.node-icon {
  width: 18px;
  height: 18px;
  flex: none;
  fill: none;
  stroke: var(--graph-entity);
  stroke-width: 1.3;
}
.node-status {
  color: var(--foreground-muted);
  font-size: var(--font-caption);
  padding-left: 25px;
}

.node-iri {
  overflow: hidden;
  color: var(--action-primary);
  font-size: var(--font-caption);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-meta {
  color: var(--foreground-muted);
  font-size: var(--font-caption);
  padding-left: 25px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.world-empty {
  position: absolute;
  top: 46%;
  left: 50%;
  text-align: center;
  transform: translate(-50%, -50%);
}

.world-empty-title {
  font-size: var(--font-h3);
  font-weight: 500;
}

.world-empty-hint {
  margin-top: 6px;
  color: var(--foreground-muted);
  font-size: var(--font-caption);
}

/* 未配置关系提示：贴在画布左下角，工具条之上 */
.canvas-warn {
  position: absolute;
  bottom: 52px;
  left: 14px;
  max-width: min(520px, 60%);
  padding: 5px 10px;
  font-size: var(--font-caption);
  color: var(--status-not-run);
  background: var(--surface-raised);
  border: 1px solid var(--status-not-run);
  border-radius: var(--radius-control);
}

.canvas-tools {
  position: absolute;
  bottom: 14px;
  left: 14px;
  display: flex;
  gap: var(--space-1);
  align-items: center;
  padding: 5px 8px;
  background: var(--surface-raised);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-control);
  opacity: 0.94;
  max-width: calc(100% - 28px);
  flex-wrap: wrap;
}

.canvas-tools :deep(.ui-button) {
  min-width: 26px;
  height: var(--control-height-small);
  padding: 0 7px;
  font: inherit;
  font-size: var(--font-caption);
  color: var(--foreground-secondary);
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: var(--radius-small);
}
.canvas-tools :deep(.ui-button):disabled {
  opacity: 0.5;
  cursor: default;
}

.canvas-tools :deep(.ui-button):hover {
  color: var(--foreground-primary);
  background: var(--surface-hover);
}

.zoom-val {
  min-width: 38px;
  font-size: var(--font-caption);
  color: var(--foreground-secondary);
  text-align: center;
}

.divider {
  width: 1px;
  height: 16px;
  background: var(--border-default);
}

.legend {
  position: absolute;
  right: 14px;
  bottom: 66px;
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 9px 12px;
  font-size: var(--font-caption);
  color: var(--foreground-secondary);
  background: var(--surface-raised);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-control);
  opacity: 0.94;
}

.legend > div {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

.lg-line {
  width: 18px;
  height: 0;
  border-top-width: 1.6px;
}

.lg-line.solid {
  border-top-style: solid;
  border-color: var(--graph-relation);
}

.lg-line.dashed {
  border-top-style: dashed;
  border-color: var(--border-emphasis);
}

/* 未配置：端点没全在画布上，画不出连线 */
.lg-line.warn {
  border-top-style: dashed;
  border-color: var(--status-not-run);
}

/* ── 业务域分区 ─────────────────────────────────────────── */
.band-rect {
  fill: var(--action-soft);
  stroke: var(--border-default);
  stroke-width: 1;
}

/* 还没有成员上画布的域：虚线框，一眼看出「这个域还是空的」 */
.band-rect--empty {
  fill: transparent;
  stroke-dasharray: 6 5;
}

.band-label {
  font-size: var(--font-caption);
  font-weight: 500;
  fill: var(--foreground-secondary);
}

/* ── 资产层校验 ─────────────────────────────────────────── */
.validation {
  flex: none;
  /* 8 项检查 + 标题刚好放得下，再多才滚动 */
  max-height: 280px;
  padding: 10px var(--space-4) 12px;
  overflow: auto;
  background: var(--surface-panel);
  border-bottom: 1px solid var(--border-muted);
}

.validation-head {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  margin-bottom: var(--space-2);
  font-size: var(--font-small);
}

.validation-summary {
  color: var(--foreground-secondary);
  font-size: var(--font-caption);
}

.validation-close {
  padding: 2px 8px;
  font: inherit;
  font-size: var(--font-caption);
  color: var(--foreground-secondary);
  cursor: pointer;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-small);
}

.validation-list {
  display: grid;
  gap: 5px;
  padding: 0;
  margin: 0;
  list-style: none;
  font-size: var(--font-caption);
}

.validation-list li {
  display: flex;
  gap: 10px;
  align-items: center;
}

.check-tag {
  display: inline-flex;
  flex: none;
  gap: 6px;
  align-items: center;
  width: 78px;
  padding: 1px 8px;
  color: var(--foreground-secondary);
  border: 1px solid var(--border-muted);
  border-radius: var(--radius-pill);
}

.check-name {
  flex: none;
  min-width: 96px;
  color: var(--foreground-primary);
}

.check-msg {
  color: var(--foreground-muted);
}

/* ── 检查器 ─────────────────────────────────────────────── */
.inspect-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: 14px;
}

.inspect-title {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  flex-wrap: wrap;
}

.inspect-title b {
  font-weight: 500;
  overflow-wrap: anywhere;
}

.inspect-iri {
  max-width: 100%;
  white-space: normal;
  overflow-wrap: anywhere;
}

.inspect-kv {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 7px 10px;
  margin: 0;
  font-size: var(--font-caption);
}

.inspect-kv dt {
  color: var(--foreground-muted);
}

.inspect-kv dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.inspect-empty {
  padding: 18px 14px;
  color: var(--foreground-muted);
  font-size: var(--font-caption);
  line-height: 1.7;
}

/* ── 检查器 · 数据属性清单 ──────────────────────────────── */
.inspect-props {
  display: grid;
  gap: 6px;
  padding-top: 10px;
  border-top: 1px solid var(--border-muted);
}

.inspect-props-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--font-caption);
  color: var(--foreground-secondary);
}

.prop-list {
  display: grid;
  gap: var(--space-1);
  padding: 0;
  margin: 0;
  list-style: none;
}

.prop-list li {
  display: flex;
  gap: 10px;
  align-items: baseline;
  justify-content: space-between;
  font-size: var(--font-caption);
  padding: 10px 0;
  border-bottom: 1px solid var(--border-muted);
}

.prop-name {
  overflow: hidden;
  color: var(--foreground-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.prop-type {
  flex: none;
  color: var(--foreground-muted);
}

.prop-more {
  margin: 0;
  font-size: var(--font-caption);
  color: var(--foreground-muted);
}

/* ── 共享 ───────────────────────────────────────────────── */
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
}

.status-tag {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  padding: 2px 9px;
  font-size: var(--font-caption);
  color: var(--foreground-secondary);
  white-space: nowrap;
  border: 1px solid var(--border-muted);
  border-radius: var(--radius-pill);
}

.status-dot {
  width: 6px;
  height: 6px;
  background: var(--dot);
  border-radius: 50%;
}
@media (max-width: 1023px) {
  .inspector {
    position: absolute;
    inset: 0 0 0 auto;
    z-index: 4;
    box-shadow: var(--shadow-raised);
    max-width: min(360px, 90%);
  }
}
@media (max-width: 767px) {
  .studio-identity {
    padding: 8px 12px;
  }
  .studio-identity :deep(.header-actions) {
    gap: 6px;
  }
  .object-bar {
    gap: 6px;
    padding-inline: 12px;
  }
  .object-bar > span:nth-child(2) {
    display: none;
  }
  .body {
    padding: 6px;
  }
  .view-toolbar {
    padding-inline: 12px;
  }
  .canvas-status {
    gap: var(--space-1);
  }
}
@media (max-width: 1023px) {
  .pool {
    position: absolute;
    inset: 0 auto 0 0;
    z-index: 4;
    box-shadow: var(--shadow-raised);
    max-width: 90%;
  }
  .onto-select {
    width: 180px;
  }
  .toolbar h1 {
    font-size: var(--font-h3);
  }
  .object-bar {
    gap: 6px;
  }
  .canvas-status {
    font-size: var(--font-caption);
  }
}
@media (max-height: 720px) {
  .validation {
    max-height: 160px;
  }
  .object-bar,
  .toolbar {
    padding-block: 6px;
  }
}
</style>
