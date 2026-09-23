<script setup lang="ts">
import { NButton, NEmpty, NSelect, NSpin, useMessage } from 'naive-ui'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { DomainBrief, DomainMember } from '@/api/domains'
import { domainsApi } from '@/api/domains'
import type { EntityTypeBrief, ResourceStatus } from '@/api/entity-types'
import { entityTypesApi } from '@/api/entity-types'
import type { CanvasPositions, Ontology, OntologyDetail, OntologyRef } from '@/api/ontology'
import { ontologyApi } from '@/api/ontology'
import type { RelationTypeBrief, RelationTypeDetail } from '@/api/relations'
import { relationsApi } from '@/api/relations'

const { t, locale } = useI18n()
const message = useMessage()

/** 画布世界尺寸固定，视口通过 transform 平移缩放 —— 拖动因此可以用纯 CSS 像素计算。 */
const WORLD_W = 2200
const WORLD_H = 1500
const NODE_W = 148
const NODE_H = 68

const loading = ref(false)
const saving = ref(false)
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

const canvasEl = ref<HTMLElement | null>(null)
const worldEl = ref<HTMLElement | null>(null)
const dragging = ref<{ key: string; offsetX: number; offsetY: number } | null>(null)

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
  const [types, rels, domainList] = await Promise.all([
    entityTypesApi.list().catch(() => [] as EntityTypeBrief[]),
    relationsApi.list().catch(() => [] as RelationTypeBrief[]),
    domainsApi.list().catch(() => [] as DomainBrief[]),
  ])
  entityTypes.value = types
  relations.value = rels
  domains.value = domainList
  const members = await Promise.all(
    domainList.map((domain) => domainsApi.members(domain.id).catch(() => [] as DomainMember[])),
  )
  domainMembers.value = Object.fromEntries(
    domainList.map((domain, index) => [domain.id, members[index]]),
  )
}

async function loadOntologies() {
  ontologies.value = await ontologyApi.list().catch(() => [] as Ontology[])
  if (!ontologyId.value && ontologies.value.length) {
    await selectOntology(ontologies.value[0].id)
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

async function selectOntology(id: number) {
  ontologyId.value = id
  selectedKey.value = null
  loading.value = true
  try {
    const [onto, refList, canvas] = await Promise.all([
      ontologyApi.get(id),
      ontologyApi.refs(id).catch(() => [] as OntologyRef[]),
      ontologyApi.getCanvas(id).catch(() => null),
    ])
    detail.value = onto
    refs.value = refList
    positions.value = { ...((canvas?.positions ?? {}) as CanvasPositions) }

    // 连线需要定义域/值域，而列表接口只返回 brief，按需补详情
    const relIds = refList
      .map((r) => r.resource_id)
      .filter((rid) => relations.value.some((r) => r.id === rid))
    await loadRelationDetails(relIds)

    ensurePositions()
    await nextTick()
    fitView()
  } finally {
    loading.value = false
  }
}

async function loadRelationDetails(ids: number[]) {
  const missing = ids.filter((id) => relationDetails.value[id] === undefined)
  if (!missing.length) return
  const results = await Promise.all(missing.map((id) => relationsApi.get(id).catch(() => null)))
  const next = { ...relationDetails.value }
  for (const item of results) if (item) next[item.id] = item
  relationDetails.value = next
}

// ── 布局持久化 ─────────────────────────────────────────────

async function persist() {
  if (!ontologyId.value) return
  saving.value = true
  try {
    await ontologyApi.saveCanvas(ontologyId.value, positions.value)
  } catch {
    message.error(t('designer.saveFailed'))
  } finally {
    saving.value = false
  }
}

function autoLayout() {
  const list = nodes.value
  if (!list.length) return
  const next = { ...positions.value }
  const radius = Math.min(430, 170 + list.length * 24)
  list.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / list.length - Math.PI / 2
    next[node.key] = {
      x: Math.round(WORLD_W / 2 + radius * Math.cos(angle) - NODE_W / 2),
      y: Math.round(WORLD_H / 2 + radius * Math.sin(angle) - NODE_H / 2),
    }
  })
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
  if (!drag || !world) return
  const rect = world.getBoundingClientRect()
  positions.value = {
    ...positions.value,
    [drag.key]: {
      x: Math.round((event.clientX - rect.left) / zoom.value - drag.offsetX),
      y: Math.round((event.clientY - rect.top) / zoom.value - drag.offsetY),
    },
  }
}

function onNodeUp() {
  window.removeEventListener('mousemove', onNodeMove)
  window.removeEventListener('mouseup', onNodeUp)
  if (!dragging.value) return
  dragging.value = null
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

async function addToCanvas(resourceId: number) {
  if (!ontologyId.value) return
  try {
    await ontologyApi.addRef(ontologyId.value, resourceId)
    refs.value = await ontologyApi.refs(ontologyId.value)
    if (relations.value.some((item) => item.id === resourceId)) {
      await loadRelationDetails([resourceId])
    }
    ensurePositions()
    fitView()
    void persist()
  } catch (err) {
    message.error((err as { code?: string }).code || t('designer.addFailed'))
  }
}

async function removeFromCanvas(resourceId: number) {
  if (!ontologyId.value) return
  const ref = refs.value.find((r) => r.resource_id === resourceId)
  if (!ref) return
  try {
    await ontologyApi.removeRef(ontologyId.value, ref.id)
    refs.value = await ontologyApi.refs(ontologyId.value)
    if (
      selectedKey.value === String(resourceId) ||
      selectedKey.value === `rel-${resourceId}` ||
      selectedKey.value === `domain-${resourceId}`
    ) {
      selectedKey.value = null
    }
    fitView()
  } catch (err) {
    message.error((err as { code?: string }).code || t('designer.removeFailed'))
  }
}

async function publish() {
  if (!ontologyId.value) return
  try {
    await ontologyApi.publish(ontologyId.value)
    await selectOntology(ontologyId.value)
    message.success(t('common.publish'))
  } catch (err) {
    message.error((err as { code?: string }).code || t('common.publish'))
  }
}

onMounted(async () => {
  await loadCatalog()
  await loadOntologies()
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onNodeMove)
  window.removeEventListener('mouseup', onNodeUp)
})
</script>

<template>
  <section class="designer">
    <!-- 顶栏：本体选择 + 布局 + 发布 -->
    <header class="toolbar">
      <NSelect
        v-model:value="ontologyId"
        :options="ontologies.map((o) => ({ label: o.name, value: o.id }))"
        :placeholder="t('designer.selectOntology')"
        class="onto-select"
        @update:value="(v: number) => selectOntology(v)"
      />
      <span v-if="detail" class="status-tag" :style="{ '--dot': STATUS_VAR[detail.status] }">
        <i class="status-dot" />
        {{ t(`resourceStatus.${detail.status}`) }}
      </span>
      <span v-if="saving" class="saving">{{ t('designer.saving') }}</span>
      <span class="spacer" />
      <NButton size="small" :disabled="!nodes.length" @click="autoLayout">
        {{ t('designer.autoLayout') }}
      </NButton>
      <NButton size="small" type="primary" :disabled="!ontologyId" @click="publish">
        {{ t('common.publish') }}
      </NButton>
    </header>

    <div v-if="!ontologies.length" class="no-ontology">
      <NEmpty :description="t('designer.noOntologyHint')" />
    </div>

    <div v-else class="body">
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

            <div v-if="!nodes.length" class="world-empty">
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

          <NButton size="small" block @click="removeFromCanvas(selected.id)">
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
  /* 设计器要占满内容区，用负边距抵消 AdminLayout 的统一留白 */
  height: calc(100vh - var(--header-height) - var(--space-5) * 2);
  margin: calc(var(--space-5) * -1);
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
