<script setup lang="ts">
import { NAlert, NButton, NEmpty, NSelect, NSpin, useMessage } from 'naive-ui'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import type { DomainBrief, DomainMember } from '@/api/domains'
import { domainsApi } from '@/api/domains'
import type { EntityType, EntityTypeBrief, ResourceStatus } from '@/api/entity-types'
import { entityTypesApi } from '@/api/entity-types'
import type { CanvasPositions, Ontology, OntologyDetail, OntologyRef } from '@/api/ontology'
import { ontologyApi } from '@/api/ontology'
import type { RelationTypeBrief, RelationTypeDetail } from '@/api/relations'
import { relationsApi } from '@/api/relations'
import type { ValidationReport, ValidationResultItem } from '@/api/validation'
import { validationApi } from '@/api/validation'
import { useApiError } from '@/composables/useApiError'

const { t, te, locale } = useI18n()
const message = useMessage()
const { toMessage } = useApiError()
const route = useRoute()
const router = useRouter()

/** 画布世界尺寸固定，视口通过 transform 平移缩放 —— 拖动因此可以用纯 CSS 像素计算。 */
const WORLD_W = 2200
const WORLD_H = 1500
const NODE_W = 148
const NODE_H = 68

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
const validationError = ref('')
const showValidation = ref(false)

const canvasEl = ref<HTMLElement | null>(null)
const worldEl = ref<HTMLElement | null>(null)
const dragging = ref<{ key: string; offsetX: number; offsetY: number } | null>(null)

type OntologySelection = { id: number; controller: AbortController }
let selection: OntologySelection | undefined
let catalogController: AbortController | undefined
let alive = true
const pendingWrites = new Map<number, Promise<unknown>>()
const canEdit = computed(
  () =>
    detail.value?.id === ontologyId.value &&
    !!detail.value &&
    !catalogLoading.value &&
    !catalogError.value &&
    !loading.value &&
    !loadError.value &&
    !saving.value &&
    !working.value &&
    !needsRefresh.value,
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
  PUBLISHED: 'var(--s-pass)',
  DRAFT: 'var(--s-notrun)',
  ARCHIVED: 'var(--s-na)',
}

function pickLabel(labels: Record<string, string> | null | undefined, fallback: string): string {
  return labels?.[locale.value] ?? labels?.['zh-CN'] ?? fallback
}

const typeById = computed(() => {
  const map: Record<number, EntityTypeBrief> = {}
  for (const tp of entityTypes.value) map[tp.id] = tp
  return map
})

const relationById = computed(() => {
  const map: Record<number, RelationTypeBrief> = {}
  for (const r of relations.value) map[r.id] = r
  return map
})

const domainById = computed(() => {
  const map: Record<number, DomainBrief> = {}
  for (const domain of domains.value) map[domain.id] = domain
  return map
})

/** 引用里哪些是实体类型（画布节点）、哪些是对象属性（画布连线）。 */
const canvasTypeIds = computed(() =>
  refs.value.map((r) => r.resource_id).filter((id) => typeById.value[id] !== undefined),
)
const canvasRelationIds = computed(() =>
  refs.value.map((r) => r.resource_id).filter((id) => relationById.value[id] !== undefined),
)
const canvasDomainIds = computed(() =>
  refs.value.map((r) => r.resource_id).filter((id) => domainById.value[id] !== undefined),
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

/** 连线只画两端都在画布上的关系 —— 一端缺失时画不出来，也不该硬画。 */
const edges = computed(() => {
  const out: {
    key: string
    id: number
    d: string
    lx: number
    ly: number
    label: string
    status: ResourceStatus
  }[] = []
  for (const rid of canvasRelationIds.value) {
    const rel = relationById.value[rid]
    const relDetail = relationDetails.value[rid]
    if (!rel || !relDetail) continue
    const from = positions.value[String(relDetail.domain_spec.type_id)]
    const to = positions.value[String(relDetail.range_spec.type_id)]
    if (!from || !to) continue
    const x1 = from.x + NODE_W / 2
    const y1 = from.y + NODE_H / 2
    const x2 = to.x + NODE_W / 2
    const y2 = to.y + NODE_H / 2
    const dx = x2 - x1
    const dy = y2 - y1
    const len = Math.hypot(dx, dy) || 1
    // 控制点沿垂直方向偏移，同向的两条线因此不会完全重叠
    const off = Math.min(34, len / 4)
    const cx = (x1 + x2) / 2 - (dy / len) * off
    const cy = (y1 + y2) / 2 + (dx / len) * off
    out.push({
      key: `rel-${rid}`,
      id: rid,
      d: `M${x1} ${y1} Q${cx} ${cy} ${x2} ${y2}`,
      // 二次贝塞尔 t=0.5 处即标签落点
      lx: 0.25 * x1 + 0.5 * cx + 0.25 * x2,
      ly: 0.25 * y1 + 0.5 * cy + 0.25 * y2,
      label: pickLabel(rel.label_i18n, rel.name),
      status: rel.status,
    })
  }
  return out
})

const availableTypes = computed(() =>
  entityTypes.value.filter((tp) => !canvasTypeIds.value.includes(tp.id)),
)
const availableRelations = computed(() =>
  relations.value.filter((r) => !canvasRelationIds.value.includes(r.id)),
)
const availableDomains = computed(() =>
  domains.value.filter((domain) => !canvasDomainIds.value.includes(domain.id)),
)

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
    const detail = relationDetails.value[id]
    if (!relation) return null
    return {
      kind: 'relation',
      key,
      id,
      label: pickLabel(relation.label_i18n, relation.name),
      name: relation.name,
      iri: relation.iri,
      status: relation.status,
      domainLabel: detail
        ? pickLabel(
            typeById.value[detail.domain_spec.type_id]?.label_i18n,
            typeById.value[detail.domain_spec.type_id]?.name ?? '',
          )
        : '',
      rangeLabel: detail
        ? pickLabel(
            typeById.value[detail.range_spec.type_id]?.label_i18n,
            typeById.value[detail.range_spec.type_id]?.name ?? '',
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
  const domainLabels = domains.value
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

async function loadCatalog() {
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
  selection?.controller.abort()
  selection = id === null ? undefined : { id, controller: new AbortController() }
  stopDragging()
  ontologyId.value = id
  selectedKey.value = null
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

async function loadOntology(context: OntologySelection) {
  if (!isCurrentSelection(context)) return false
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
    positions.value = { ...((canvas.positions ?? {}) as CanvasPositions) }
    relationDetails.value = Object.fromEntries(relationItems.map((item) => [item.id, item]))
    ensurePositions()
    await nextTick()
    if (!isCurrentSelection(context)) return false
    fitView()
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

// ── 布局持久化 ─────────────────────────────────────────────

async function persist() {
  const context = selection
  if (!context || !isCurrentSelection(context) || !canEdit.value) return
  await persistLayout(context)
}

async function persistLayout(context: OntologySelection) {
  const snapshot: CanvasPositions = Object.fromEntries(
    Object.entries(positions.value).map(([key, position]) => [key, { ...position }]),
  )
  saving.value = true
  saveError.value = ''
  try {
    await trackWrite(context.id, ontologyApi.saveCanvas(context.id, snapshot))
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
  fitView()
  void persist()
}

function fitView() {
  const viewportWidth = canvasEl.value?.clientWidth || 800
  const viewportHeight = canvasEl.value?.clientHeight || 520
  const list = nodes.value
  if (!list.length) {
    zoom.value = 0.55
    pan.value = {
      x: viewportWidth / 2 - (WORLD_W / 2) * zoom.value,
      y: viewportHeight / 2 - (WORLD_H / 2) * zoom.value,
    }
    return
  }

  const minX = Math.min(...list.map((node) => node.x))
  const minY = Math.min(...list.map((node) => node.y))
  const maxX = Math.max(...list.map((node) => node.x + NODE_W))
  const maxY = Math.max(...list.map((node) => node.y + NODE_H))
  const boundsWidth = Math.max(1, maxX - minX)
  const boundsHeight = Math.max(1, maxY - minY)
  const scale = Math.min(
    1.5,
    (viewportWidth - 64) / boundsWidth,
    (viewportHeight - 64) / boundsHeight,
  )
  zoom.value = Math.max(0.2, scale)
  pan.value = {
    x: (viewportWidth - boundsWidth * zoom.value) / 2 - minX * zoom.value,
    y: (viewportHeight - boundsHeight * zoom.value) / 2 - minY * zoom.value,
  }
}

function stepZoom(delta: number) {
  zoom.value = Math.min(2, Math.max(0.2, Math.round((zoom.value + delta) * 100) / 100))
}

// ── 拖拽 ───────────────────────────────────────────────────

function onNodeDown(key: string, event: MouseEvent) {
  if (!canEdit.value) return
  event.preventDefault()
  selectedKey.value = key
  const world = worldEl.value
  if (!world) return
  // 世界容器已被 transform，先换算回未缩放坐标，再减去抓取偏移
  const rect = world.getBoundingClientRect()
  const worldX = (event.clientX - rect.left) / zoom.value
  const worldY = (event.clientY - rect.top) / zoom.value
  const pos = positions.value[key] ?? { x: 0, y: 0 }
  dragging.value = { key, offsetX: worldX - pos.x, offsetY: worldY - pos.y }
  window.addEventListener('mousemove', onNodeMove)
  window.addEventListener('mouseup', onNodeUp)
}

function onNodeMove(event: MouseEvent) {
  const drag = dragging.value
  const world = worldEl.value
  if (!drag || !world || !canEdit.value) return
  const rect = world.getBoundingClientRect()
  positions.value = {
    ...positions.value,
    [drag.key]: {
      x: Math.round((event.clientX - rect.left) / zoom.value - drag.offsetX),
      y: Math.round((event.clientY - rect.top) / zoom.value - drag.offsetY),
    },
  }
}

function stopDragging() {
  if (typeof window !== 'undefined') {
    window.removeEventListener('mousemove', onNodeMove)
    window.removeEventListener('mouseup', onNodeUp)
  }
  dragging.value = null
}

function onNodeUp() {
  const moved = !!dragging.value
  stopDragging()
  if (!moved) return
  // 拖拽只改布局，不产生语义版本，所以请求里没有 If-Match
  void persist()
}

function onWheel(event: WheelEvent) {
  event.preventDefault()
  stepZoom(event.deltaY > 0 ? -0.1 : 0.1)
}

function selectRelation(id: number) {
  selectedKey.value = `rel-${id}`
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
    const loaded = await loadOntology(context)
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
  await updateOntology(
    (id, revision) => ontologyApi.addRef(id, resourceId, undefined, revision),
    true,
  )
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
watch(selectedKey, async (key) => {
  typeDetail.value = null
  const context = selection
  if (!key || key.startsWith('rel-') || key.startsWith('domain-')) return
  const id = Number(key)
  if (!Number.isSafeInteger(id) || id <= 0) return
  typeDetailLoading.value = true
  try {
    const info = await entityTypesApi.get(id)
    if (alive && context === selection && selectedKey.value === key) typeDetail.value = info
  } catch {
    // 详情取不到不影响装配，检查器退化为不含属性清单
  } finally {
    typeDetailLoading.value = false
  }
})

// ── 资产层校验（A01–A08）──────────────────────────────────

/**
 * 装配完最需要知道的是「能不能发布」。后端 `POST /validation/ontologies/{id}`
 * 跑的就是资产层那 8 项检查，这里把四态结果直接摊在设计器里。
 */
async function runValidation() {
  const id = ontologyId.value
  if (id === null || validating.value) return
  validating.value = true
  validationError.value = ''
  showValidation.value = true
  try {
    const report = await validationApi.validateOntology(id)
    const results = await validationApi.getResults(report.report_id)
    if (!alive) return
    validationReport.value = report
    validationResults.value = results
  } catch (err) {
    if (!alive) return
    validationError.value = toMessage(err)
    validationReport.value = null
    validationResults.value = []
  } finally {
    if (alive) validating.value = false
  }
}

const VALIDATION_STATE_VAR: Record<string, string> = {
  PASS: 'var(--s-pass)',
  VIOLATION: 'var(--s-violation)',
  NA: 'var(--s-na)',
  NOT_RUN: 'var(--s-notrun)',
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

onMounted(() => {
  // 支持从本体列表带 ?ontology=<id> 进来，直接定位到那一个本体
  const requested = Number(route.query.ontology)
  if (Number.isSafeInteger(requested) && requested > 0) ontologyId.value = requested
  void loadCatalog()
})

onBeforeUnmount(() => {
  alive = false
  catalogController?.abort()
  selection?.controller.abort()
  stopDragging()
})
</script>

<template>
  <section class="designer">
    <!-- 顶栏：本体选择 + 布局 + 发布 -->
    <header class="toolbar">
      <NSelect
        :value="ontologyId"
        :options="ontologies.map((o) => ({ label: o.name, value: o.id }))"
        :placeholder="t('designer.selectOntology')"
        :loading="catalogLoading"
        :disabled="catalogLoading || !!catalogError"
        class="onto-select"
        @update:value="(v: number) => selectOntology(v)"
      />
      <span v-if="detail" class="status-tag" :style="{ '--dot': STATUS_VAR[detail.status] }">
        <i class="status-dot" />
        {{ t(`resourceStatus.${detail.status}`) }}
      </span>
      <span v-if="saving" class="saving">{{ t('designer.saving') }}</span>
      <span class="spacer" />
      <NButton size="small" :disabled="!canEdit || !nodes.length" @click="autoLayout">
        {{ t('designer.autoLayout') }}
      </NButton>
      <NButton
        size="small"
        :disabled="ontologyId === null"
        :loading="validating"
        @click="runValidation"
      >
        {{ t('designer.runValidation') }}
      </NButton>
      <NButton size="small" type="primary" :disabled="!canEdit" @click="publish">
        {{ t('common.publish') }}
      </NButton>
    </header>

    <!-- 资产层校验结果：装配完在这里就能看出能不能发布 -->
    <section v-if="showValidation" class="validation">
      <header class="validation-head">
        <b>{{ t('designer.validationTitle') }}</b>
        <span v-if="validationReport" class="validation-summary mono">
          {{ validationSummaryText(validationReport) }}
        </span>
        <span class="spacer" />
        <button type="button" class="validation-close" @click="showValidation = false">
          {{ t('common.close') }}
        </button>
      </header>
      <NAlert v-if="validationError" type="error" role="alert">{{ validationError }}</NAlert>
      <p v-else-if="validating && !validationResults.length" role="status">
        {{ t('common.loading') }}
      </p>
      <ul v-else-if="validationResults.length" class="validation-list">
        <li v-for="item in validationResults" :key="item.check_code">
          <span class="check-tag" :style="{ '--dot': VALIDATION_STATE_VAR[item.state] }">
            <i class="status-dot" />
            {{ t(`report.states.${item.state}`) }}
          </span>
          <span class="check-name">{{ checkLabel(item.check_code) }}</span>
          <span v-if="item.message" class="check-msg">{{ item.message }}</span>
        </li>
      </ul>
    </section>

    <NAlert v-if="catalogError" type="error" role="alert">
      {{ catalogError }}
      <NButton :loading="catalogLoading" @click="loadCatalog">{{ t('graph.refresh') }}</NButton>
    </NAlert>
    <NAlert v-if="loadError || actionError" type="error" role="alert">
      {{ loadError || actionError }}
      <NButton :loading="loading" @click="ontologyId !== null && selectOntology(ontologyId)">
        {{ t('graph.refresh') }}
      </NButton>
    </NAlert>
    <NAlert v-if="saveError" type="error" role="alert">
      {{ saveError }}
      <NButton :disabled="!canEdit" @click="persist">{{ t('common.save') }}</NButton>
    </NAlert>
    <p v-if="catalogLoading" role="status">{{ t('common.loading') }}</p>

    <div v-if="!catalogLoading && !catalogError && !ontologies.length" class="no-ontology">
      <!-- 空态要给出可执行动作，而不是只说「去创建一个」却没有入口 -->
      <NEmpty :description="t('designer.noOntologyHint')">
        <template #extra>
          <NButton type="primary" size="small" @click="router.push({ name: 'ontologies' })">
            {{ t('ontology.create') }}
          </NButton>
        </template>
      </NEmpty>
    </div>

    <div v-else-if="ontologies.length" class="body">
      <!-- 左：资源面板 -->
      <aside class="panel pool">
        <div class="panel-head">{{ t('designer.resourcePool') }}</div>
        <div class="pool-body">
          <div class="pool-group">{{ t('designer.inCanvas') }}</div>
          <button
            v-for="id in canvasTypeIds"
            :key="`c-${id}`"
            type="button"
            class="pool-item on"
            @click="selectedKey = String(id)"
          >
            <i class="dot" style="background: var(--g-entity)" />
            <span class="pool-name">{{ pickLabel(typeById[id]?.label_i18n, String(id)) }}</span>
          </button>
          <button
            v-for="id in canvasRelationIds"
            :key="`cr-${id}`"
            type="button"
            class="pool-item"
            :class="{ on: selectedKey === `rel-${id}` }"
            @click="selectRelation(id)"
          >
            <i class="dot" style="background: var(--g-relation)" />
            <span class="pool-name">{{ pickLabel(relationById[id]?.label_i18n, String(id)) }}</span>
          </button>
          <button
            v-for="id in canvasDomainIds"
            :key="`cd-${id}`"
            type="button"
            class="pool-item"
            :class="{ on: selectedKey === `domain-${id}` }"
            @click="selectedKey = `domain-${id}`"
          >
            <i class="dot" style="background: var(--text-secondary)" />
            <span class="pool-name">{{ pickLabel(domainById[id]?.label_i18n, String(id)) }}</span>
          </button>
          <div
            v-if="!canvasTypeIds.length && !canvasRelationIds.length && !canvasDomainIds.length"
            class="pool-empty"
          >
            {{ t('common.empty') }}
          </div>

          <div class="pool-group">{{ t('designer.notInCanvas') }}</div>
          <button
            v-for="tp in availableTypes"
            :key="`a-${tp.id}`"
            type="button"
            class="pool-item addable"
            :disabled="!canEdit"
            @click="addToCanvas(tp.id)"
          >
            <i class="dot" :style="{ background: STATUS_VAR[tp.status] }" />
            <span class="pool-name">{{ pickLabel(tp.label_i18n, tp.name) }}</span>
            <span class="plus" :aria-label="t('designer.addToCanvas')" />
          </button>
          <button
            v-for="r in availableRelations"
            :key="`ar-${r.id}`"
            type="button"
            class="pool-item addable"
            :disabled="!canEdit"
            @click="addToCanvas(r.id)"
          >
            <i class="dot" :style="{ background: STATUS_VAR[r.status] }" />
            <span class="pool-name">{{ pickLabel(r.label_i18n, r.name) }}</span>
            <span class="plus" :aria-label="t('designer.addToCanvas')" />
          </button>
          <button
            v-for="domain in availableDomains"
            :key="`ad-${domain.id}`"
            type="button"
            class="pool-item addable"
            :disabled="!canEdit"
            @click="addToCanvas(domain.id)"
          >
            <i class="dot" :style="{ background: STATUS_VAR[domain.status] }" />
            <span class="pool-name">{{ pickLabel(domain.label_i18n, domain.name) }}</span>
            <span class="plus" :aria-label="t('designer.addToCanvas')" />
          </button>
        </div>
        <div class="pool-foot">{{ t('designer.layoutHint') }}</div>
      </aside>

      <!-- 中：画布 -->
      <div ref="canvasEl" class="canvas" @wheel="onWheel">
        <NSpin :show="loading" class="canvas-spin">
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
                    stroke="var(--g-relation)"
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

              <g v-for="edge in edges" :key="edge.key">
                <path
                  class="edge-hit"
                  :d="edge.d"
                  fill="none"
                  stroke="transparent"
                  stroke-width="18"
                  pointer-events="stroke"
                  tabindex="0"
                  role="button"
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
                      ? 'var(--accent)'
                      : edge.status === 'PUBLISHED'
                        ? 'var(--g-relation)'
                        : 'var(--border-strong)'
                  "
                  :stroke-width="selectedKey === edge.key ? 2.6 : 1.6"
                  :stroke-dasharray="edge.status === 'PUBLISHED' ? undefined : '5 5'"
                  marker-end="url(#edge-arrow)"
                />
                <text :x="edge.lx" :y="edge.ly - 6" text-anchor="middle" class="edge-label">
                  {{ edge.label }}
                </text>
              </g>
            </svg>

            <div
              v-for="node in nodes"
              :key="node.key"
              class="node"
              :class="{ on: selectedKey === node.key, dragging: dragging?.key === node.key }"
              :style="{
                left: `${node.x}px`,
                top: `${node.y}px`,
                width: `${NODE_W}px`,
                height: `${NODE_H}px`,
              }"
              @mousedown="onNodeDown(node.key, $event)"
            >
              <span class="node-head">
                <i class="dot" :style="{ background: STATUS_VAR[node.status] }" />
                <span class="node-label">{{ node.label }}</span>
              </span>
              <span class="node-iri mono">{{ node.iri }}</span>
              <span class="node-meta">{{ node.name }}</span>
            </div>

            <div v-if="!loading && !loadError && !nodes.length" class="world-empty">
              <div class="world-empty-title">{{ t('designer.emptyCanvas') }}</div>
              <div class="world-empty-hint">{{ t('designer.emptyCanvasHint') }}</div>
            </div>
          </div>
        </NSpin>

        <div class="canvas-tools">
          <button type="button" :aria-label="t('designer.zoomOut')" @click="stepZoom(-0.1)" />
          <span class="mono zoom-val">{{
            t('designer.zoomLevel', { percent: Math.round(zoom * 100) })
          }}</span>
          <button type="button" :aria-label="t('designer.zoomIn')" @click="stepZoom(0.1)" />
          <span class="divider" />
          <button type="button" @click="fitView">{{ t('designer.fitView') }}</button>
        </div>

        <div class="legend">
          <div><span class="lg-line solid" />{{ t('designer.legendRelation') }}</div>
          <div><span class="lg-line dashed" />{{ t('designer.legendDraft') }}</div>
        </div>
      </div>

      <!-- 右：属性检查器 -->
      <aside class="panel inspector">
        <div class="panel-head">{{ t('designer.inspector') }}</div>
        <div v-if="selected" class="inspect-body">
          <div class="inspect-title">
            <i
              class="dot"
              :style="{
                background:
                  selected.kind === 'entity'
                    ? 'var(--g-entity)'
                    : selected.kind === 'relation'
                      ? 'var(--g-relation)'
                      : 'var(--text-secondary)',
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
              <span class="mono">{{ typeDetail?.data_props?.length ?? 0 }}</span>
            </div>
            <p v-if="typeDetailLoading" class="inspect-empty">{{ t('common.loading') }}</p>
            <template v-else-if="typeDetail?.data_props?.length">
              <ul class="prop-list">
                <li v-for="prop in typeDetail.data_props.slice(0, 4)" :key="prop.name">
                  <span class="mono prop-name">{{ prop.name }}</span>
                  <span class="prop-type">{{ t(`entityProps.datatypes.${prop.datatype}`) }}</span>
                </li>
              </ul>
              <p v-if="typeDetail.data_props.length > 4" class="prop-more">
                {{ t('designer.moreProps', { count: typeDetail.data_props.length - 4 }) }}
              </p>
            </template>
            <p v-else class="inspect-empty">{{ t('common.empty') }}</p>
          </div>

          <NButton size="small" block :disabled="!canEdit" @click="removeFromCanvas(selected.id)">
            {{ t('designer.removeFromCanvas') }}
          </NButton>
        </div>
        <div v-else class="inspect-empty">{{ t('designer.selectNode') }}</div>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.designer {
  display: flex;
  flex-direction: column;
  /*
   * 全屏画布：铺满顶栏以下的整个内容区（路由 meta.fullBleed 已把内容区留白去掉）。
   *
   * 这里既不能加负边距、也不能用 height:100%：
   * - 负边距会把内容顶出 naive 在 NLayoutContent 内部那层 overflow:hidden 的滚动
   *   容器，顶部被裁掉一条（工具条曾被裁掉 24px）；
   * - 设计器真正的父元素是那层滚动容器里的包装层，高度是 auto，
   *   百分比解析不出来，画布会塌成一条。
   * 内容区高度就是「视口 - 顶栏」，直接按它算。
   */
  height: calc(100vh - var(--header-height));
  overflow: hidden;
}

.toolbar {
  display: flex;
  flex: none;
  gap: var(--space-2);
  align-items: center;
  padding: 10px var(--space-4);
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-subtle);
}

.onto-select {
  width: 240px;
}

.spacer {
  flex: 1;
}

.saving {
  color: var(--text-tertiary);
  font-size: var(--font-caption);
}

.no-ontology {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
}

.body {
  display: flex;
  flex: 1;
  min-height: 0;
}

/* ── 侧栏面板 ───────────────────────────────────────────── */
.panel {
  display: flex;
  flex-direction: column;
  flex: none;
  background: var(--bg-surface);
}

.pool {
  width: 216px;
  border-right: 1px solid var(--border-subtle);
}

.inspector {
  width: 246px;
  border-left: 1px solid var(--border-subtle);
}

.panel-head {
  padding: 12px 14px;
  color: var(--text-secondary);
  font-size: var(--font-caption);
  border-bottom: 1px solid var(--border-subtle);
}

.pool-body {
  flex: 1;
  padding: 10px;
  overflow: auto;
}

.pool-group {
  padding: 4px 6px;
  color: var(--text-tertiary);
  font-size: 10.5px;
}

.pool-item {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 100%;
  padding: 7px 10px;
  margin-bottom: 4px;
  font: inherit;
  font-size: var(--font-caption);
  color: var(--text-secondary);
  text-align: left;
  cursor: pointer;
  background: var(--bg-raised);
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-md);
  transition: border-color var(--dur-fast) var(--ease-out);
}

.pool-item:hover {
  border-color: var(--accent);
}

.pool-item.on {
  color: var(--text);
  background: var(--accent-soft);
  border-color: transparent;
}

.pool-item.addable {
  background: transparent;
  border-style: dashed;
}

.pool-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plus {
  margin-left: auto;
  color: var(--text-disabled);
}
.plus::before {
  content: '+';
}

.pool-empty {
  padding: 8px 6px;
  color: var(--text-disabled);
  font-size: 11px;
}

.pool-foot {
  padding: 10px 14px;
  color: var(--text-disabled);
  font-size: 10.5px;
  line-height: 1.7;
  border-top: 1px solid var(--border-subtle);
}

/* ── 画布 ───────────────────────────────────────────────── */
.canvas {
  position: relative;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  cursor: grab;
  background-color: var(--bg-base);
  background-image:
    linear-gradient(var(--border-subtle) 1px, transparent 1px),
    linear-gradient(90deg, var(--border-subtle) 1px, transparent 1px);
  background-size: 24px 24px;
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
}

.edge-label {
  font-size: 10.5px;
  fill: var(--g-relation);
  pointer-events: none;
}
.edge-hit {
  cursor: pointer;
}
.edge-hit:focus-visible {
  stroke: var(--accent);
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
  background: var(--bg-raised);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-lg);
  transition: box-shadow var(--dur-fast) var(--ease-out);
}

.node:hover {
  box-shadow: var(--elev-2);
}

.node.on {
  border-color: var(--accent);
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
  font-size: var(--font-caption);
  font-weight: 500;
}

.node-iri {
  overflow: hidden;
  color: var(--cyan);
  font-size: 9.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-meta {
  color: var(--text-disabled);
  font-size: 9.5px;
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
  color: var(--text-tertiary);
  font-size: var(--font-caption);
}

.canvas-tools {
  position: absolute;
  bottom: 14px;
  left: 14px;
  display: flex;
  gap: 4px;
  align-items: center;
  padding: 5px 8px;
  background: var(--bg-raised);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  opacity: 0.94;
}

.canvas-tools button {
  min-width: 26px;
  height: 24px;
  padding: 0 7px;
  font: inherit;
  font-size: 11px;
  color: var(--text-secondary);
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: var(--r-sm);
}

.canvas-tools button:hover {
  color: var(--text);
  background: var(--bg-hover);
}
.canvas-tools button:first-child::before {
  content: '−';
}
.canvas-tools button:nth-child(3)::before {
  content: '+';
}

.zoom-val {
  min-width: 38px;
  font-size: 11px;
  color: var(--text-secondary);
  text-align: center;
}

.divider {
  width: 1px;
  height: 16px;
  background: var(--border);
}

.legend {
  position: absolute;
  right: 14px;
  bottom: 14px;
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 9px 12px;
  font-size: 10.5px;
  color: var(--text-secondary);
  background: var(--bg-raised);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  opacity: 0.94;
}

.legend > div {
  display: flex;
  gap: 8px;
  align-items: center;
}

.lg-line {
  width: 18px;
  height: 0;
  border-top-width: 1.6px;
}

.lg-line.solid {
  border-top-style: solid;
  border-color: var(--g-relation);
}

.lg-line.dashed {
  border-top-style: dashed;
  border-color: var(--border-strong);
}

/* ── 业务域分区 ─────────────────────────────────────────── */
.band-rect {
  fill: var(--accent-soft);
  stroke: var(--border);
  stroke-width: 1;
}

/* 还没有成员上画布的域：虚线框，一眼看出「这个域还是空的」 */
.band-rect--empty {
  fill: transparent;
  stroke-dasharray: 6 5;
}

.band-label {
  font-size: 11px;
  font-weight: 500;
  fill: var(--text-secondary);
}

/* ── 资产层校验 ─────────────────────────────────────────── */
.validation {
  flex: none;
  /* 8 项检查 + 标题刚好放得下，再多才滚动 */
  max-height: 280px;
  padding: 10px var(--space-4) 12px;
  overflow: auto;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-subtle);
}

.validation-head {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  margin-bottom: 8px;
  font-size: var(--font-small);
}

.validation-summary {
  color: var(--text-secondary);
  font-size: var(--font-caption);
}

.validation-close {
  padding: 2px 8px;
  font: inherit;
  font-size: var(--font-caption);
  color: var(--text-secondary);
  cursor: pointer;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
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
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-pill);
}

.check-name {
  flex: none;
  min-width: 96px;
  color: var(--text);
}

.check-msg {
  color: var(--text-tertiary);
}

/* ── 检查器 ─────────────────────────────────────────────── */
.inspect-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
}

.inspect-title {
  display: flex;
  gap: 8px;
  align-items: center;
}

.inspect-title b {
  font-weight: 500;
}

.inspect-iri {
  max-width: 100%;
}

.inspect-kv {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: 7px 10px;
  margin: 0;
  font-size: 11px;
}

.inspect-kv dt {
  color: var(--text-tertiary);
}

.inspect-kv dd {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.inspect-empty {
  padding: 18px 14px;
  color: var(--text-tertiary);
  font-size: var(--font-caption);
  line-height: 1.7;
}

/* ── 检查器 · 数据属性清单 ──────────────────────────────── */
.inspect-props {
  display: grid;
  gap: 6px;
  padding-top: 10px;
  border-top: 1px solid var(--border-subtle);
}

.inspect-props-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--font-caption);
  color: var(--text-secondary);
}

.prop-list {
  display: grid;
  gap: 4px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.prop-list li {
  display: flex;
  gap: 10px;
  align-items: baseline;
  justify-content: space-between;
  font-size: 11px;
}

.prop-name {
  overflow: hidden;
  color: var(--text);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.prop-type {
  flex: none;
  color: var(--text-tertiary);
}

.prop-more {
  margin: 0;
  font-size: 11px;
  color: var(--text-tertiary);
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
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-pill);
}

.status-dot {
  width: 6px;
  height: 6px;
  background: var(--dot);
  border-radius: 50%;
}
</style>
