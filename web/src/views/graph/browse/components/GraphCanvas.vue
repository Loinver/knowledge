<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { GraphView } from '@/api/graph'
import { UiAlert } from '@/components/ui'

import type { Bounds, Camera, Point } from '../../../../components/graph/viewport'
import {
  centerCamera,
  dragPosition,
  isDrag,
  MAX_SCALE,
  MIN_SCALE,
  NODE_RADIUS,
  wheelCamera,
  zoomAt,
} from '../../../../components/graph/viewport'
import { nodeAppearance } from '../../components/graphPresentation'
import { entityName } from '../../components/graphWorkspace'
import { graphPaths } from './graphLayout'
import { nodeDisplayScales, nodeNameLines, showGraphLabel } from './graphViewportPolicy'
import { resolveLayout, typeColor } from './layouts/index.ts'
import type { SemanticContext } from './layouts/semanticView'
import { useGraphViewport } from './useGraphViewport'

type GraphEdge = GraphView['edges'][number]
type GraphNode = GraphView['nodes'][number]
const props = defineProps<{
  graph: GraphView
  neighborhood: boolean
  layoutId?: string | null
  semanticContext?: SemanticContext
  flaggedIris?: Set<string>
  highlightIris?: Set<string>
  selectedIri?: string | null
  selectedEdgeKey?: string | null
  relationLabels?: Record<string, string>
}>()
const emit = defineEmits<{
  select: [iri: string]
  selectEdge: [edge: GraphEdge, aggregate: boolean]
  selectedEdgeUpdated: [edge: GraphEdge | null, aggregate: boolean]
}>()
const { t } = useI18n()
const id = useId()
const shortName = (iri: string) => iri.split(/[/#]/).filter(Boolean).at(-1) || iri
const layout = computed(() =>
  resolveLayout(props.layoutId, props.neighborhood).compute(
    props.graph,
    props.semanticContext ?? { config: {}, fields: [] },
  ),
)
const layoutKey = () =>
  JSON.stringify([
    resolveLayout(props.layoutId, props.neighborhood).id,
    Object.entries(props.semanticContext?.config ?? {}).sort(([a], [b]) => a.localeCompare(b)),
    props.semanticContext?.legacy ?? false,
  ])
const scrollEl = ref<HTMLElement | null>(null)
const edgeBounds = shallowRef<Bounds[]>([])
const {
  camera,
  previousCamera,
  size,
  positions,
  markPositions,
  nodes,
  marks,
  bounds,
  viewport,
  focus,
  fitView,
  restoreView,
  getContext,
  restoreContext,
} = useGraphViewport(scrollEl, () => props.graph, layout, layoutKey, edgeBounds)
function focusSelection() {
  const selected = scrollEl.value?.querySelector<SVGElement>('[aria-pressed="true"]')
  const target = selected ?? scrollEl.value
  void nextTick(() => target?.focus({ preventScroll: true }))
}
const displayCounts = computed(() => ({
  nodes: marks.value ? marks.value.filter((mark) => mark.iri).length : nodes.value.length,
  edges: marks.value ? 0 : paths.value.filter((path) => path.path).length,
}))
defineExpose({ focus, focusSelection, fitView, getContext, restoreContext, displayCounts })

const legendTypes = computed(() => [
  ...new Set([
    ...layout.value.groups.map((group) => group.type),
    ...props.graph.nodes.map((node) => node.type_iri),
  ]),
])
const typePaint = (type: string) =>
  marks.value ? typeColor(type, legendTypes.value) : nodeAppearance(type).color
const nodeFlagged = (iri: string) => props.flaggedIris?.has(iri) ?? false
const nodeHighlighted = (iri: string) => props.highlightIris?.has(iri) ?? false
const selectedFact = computed(() =>
  (layout.value.edges ?? props.graph.edges).find(
    (edge) => `${edge.kind}:${edge.id}` === props.selectedEdgeKey,
  ),
)
const importantNode = (iri: string) =>
  props.selectedIri === iri ||
  nodeHighlighted(iri) ||
  selectedFact.value?.subject === iri ||
  selectedFact.value?.object_ === iri
const displayScales = computed(() =>
  nodeDisplayScales(
    nodes.value,
    new Set(nodes.value.filter((node) => importantNode(node.iri)).map((node) => node.iri)),
    camera.value.scale,
  ),
)
const nodeDisplayScale = (iri: string) => displayScales.value.get(iri) ?? 1
// Paint the active context last so distant nodes cannot obscure its enlarged label.
const paintOrder = (iri: string) => (props.selectedIri === iri ? 2 : Number(importantNode(iri)))
const paintedNodes = computed(() =>
  [...nodes.value].sort((a, b) => paintOrder(a.iri) - paintOrder(b.iri)),
)
watch(paintedNodes, () => {
  const active = typeof document === 'undefined' ? null : document.activeElement
  if (active && scrollEl.value?.contains(active)) {
    void nextTick(() => {
      if (active.isConnected) (active as SVGElement | HTMLElement).focus({ preventScroll: true })
    })
  }
})
const paths = computed(() =>
  graphPaths(nodes.value, layout.value.edges ?? props.graph.edges, layout.value.edgePaths, {
    radius: (node) => NODE_RADIUS * nodeDisplayScale(node.iri),
    originalNodes: layout.value.nodes,
    avoidNodes: [
      'org_tree',
      'indent_tree',
      'equity_tree',
      'control_chain',
      'clan_tree',
      'impact',
    ].includes(resolveLayout(props.layoutId, props.neighborhood).id),
    scale: camera.value.scale,
  }).filter((edge) => edge.path),
)
watch(
  paths,
  (edges) => {
    edgeBounds.value = edges.flatMap((edge) => (edge.bounds ? [edge.bounds] : []))
  },
  { immediate: true, flush: 'sync' },
)
const aggregate = computed(() =>
  ['schema', 'sankey', 'chord'].includes(resolveLayout(props.layoutId, props.neighborhood).id),
)
function selectEdge(edge: GraphEdge) {
  emit('selectEdge', edge, aggregate.value)
}
watch([paths, () => props.selectedEdgeKey, aggregate], () => {
  if (props.selectedEdgeKey)
    emit(
      'selectedEdgeUpdated',
      paths.value.find((edge) => `${edge.kind}:${edge.id}` === props.selectedEdgeKey) ?? null,
      aggregate.value,
    )
})
// A compact overview must retain identity after fitting beside the fixed inspector.
// Dense or distant views keep the existing selection-driven label reduction.
const overviewLabels = computed(
  () => nodes.value.length <= 30 && paths.value.length <= 40 && camera.value.scale >= 0.5,
)
const nodeLabelVisible = (node: GraphNode) =>
  showGraphLabel(camera.value.scale, importantNode(node.iri) || overviewLabels.value, 'node')
const edgeKey = (edge: GraphEdge) => `${edge.kind}:${edge.id}`
const edgeSelected = (edge: GraphEdge) => edgeKey(edge) === props.selectedEdgeKey
const edgeHighlighted = (edge: GraphEdge) =>
  nodeHighlighted(edge.subject) && nodeHighlighted(edge.object_)
const importantEdge = (edge: GraphEdge) =>
  edgeSelected(edge) ||
  edgeHighlighted(edge) ||
  edge.subject === props.selectedIri ||
  edge.object_ === props.selectedIri
const edgeName = (edge: GraphEdge) =>
  `${props.relationLabels?.[edge.predicate] ?? shortName(edge.predicate)}${edge.kind === 'DERIVED' ? ` · ${t('graph.derived')}` : ''}`
const edgeDescription = (edge: GraphEdge) =>
  t('graph.factDescription', {
    subject: edge.subject,
    predicate: `${edgeName(edge)} · ${edge.predicate}`,
    object: edge.object_,
  })
const edgeLabelScale = (edge: GraphEdge) =>
  importantEdge(edge)
    ? Math.max(1, 1 / camera.value.scale)
    : overviewLabels.value
      ? Math.max(1, 0.75 / camera.value.scale)
      : 1
const nodeName = (node: GraphNode) => entityName(node) || shortName(node.iri)
const nodeTitle = (node: GraphNode) =>
  `${nodeName(node)} · ${node.iri}${nodeFlagged(node.iri) ? ` · ${t('graph.qualityFlagged')}` : ''}`
const nodeBadgeText = (node: GraphNode) =>
  typeof node.attrs.__typeCount__ === 'number'
    ? t('graph.entityCount', { count: node.attrs.__typeCount__ })
    : ''

const typeIcon = (iri: string) => nodeAppearance(iri).icon
const showLegend = ref(false)
const showMinimap = ref(false)
const legendButton = ref<HTMLButtonElement | null>(null)
const minimapButton = ref<HTMLButtonElement | null>(null)
function closeLegend() {
  showLegend.value = false
  void nextTick(() => legendButton.value?.focus())
}
function closeMinimap() {
  showMinimap.value = false
  void nextTick(() => minimapButton.value?.focus())
}
const minimapBox = computed(
  () => `${bounds.value.x} ${bounds.value.y} ${bounds.value.width} ${bounds.value.height}`,
)
const minimapDots = computed(() =>
  marks.value
    ? marks.value.map((mark) => ({
        id: mark.id,
        x: mark.x + mark.offsetX,
        y: mark.y + mark.offsetY,
        fill: mark.fill,
      }))
    : nodes.value.map((node) => ({
        id: node.iri,
        x: node.x,
        y: node.y,
        fill: typePaint(node.type_iri),
      })),
)
function onMinimapClick(event: MouseEvent) {
  const el = event.currentTarget as SVGSVGElement
  const matrix = el.getScreenCTM()
  if (!matrix) return
  const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
  camera.value = centerCamera(camera.value, point, size.value)
}
function zoom(factor: number) {
  camera.value = zoomAt(
    camera.value,
    { x: size.value.width / 2, y: size.value.height / 2 },
    camera.value.scale * factor,
  )
}
function onWheel(event: WheelEvent) {
  const rect = scrollEl.value!.getBoundingClientRect()
  camera.value = wheelCamera(
    camera.value,
    event,
    { x: event.clientX - rect.left, y: event.clientY - rect.top },
    size.value,
  )
}

type Drag = {
  pointerId: number
  start: Point
  camera: Camera
  iri?: string
  markId?: string
  origin?: Point
  moved: boolean
  revision: number
  layoutKey: string
  target: HTMLElement | SVGElement
}
const drag = ref<Drag | null>(null)
const spacePressed = ref(false)
let suppressClick = false
function startDrag(event: PointerEvent, iri?: string, markId?: string) {
  if (event.button !== 0 || !event.isPrimary || !scrollEl.value || drag.value) return
  if (![event.clientX, event.clientY].every(Number.isFinite)) return
  if (showLegend.value) showLegend.value = false
  const nodeIri = spacePressed.value ? undefined : iri
  const activeMark = nodeIri ? markId : undefined
  const origin = activeMark
    ? markPositions.value[activeMark]
    : nodeIri
      ? positions.value[nodeIri]
      : undefined
  if (nodeIri && (!origin || ![origin.x, origin.y].every(Number.isFinite))) return
  try {
    scrollEl.value.setPointerCapture(event.pointerId)
  } catch {
    return
  }
  suppressClick = false
  drag.value = {
    pointerId: event.pointerId,
    start: { x: event.clientX, y: event.clientY },
    camera: { ...camera.value },
    iri: nodeIri,
    markId: activeMark,
    origin: origin ? { ...origin } : undefined,
    moved: false,
    revision: props.graph.graph_revision_id,
    layoutKey: layoutKey(),
    target: event.currentTarget as HTMLElement | SVGElement,
  }
  ;(event.currentTarget as HTMLElement | SVGElement).focus({ preventScroll: true })
}
function moveDrag(event: PointerEvent) {
  const current = drag.value
  if (!current || event.pointerId !== current.pointerId) return
  const point = { x: event.clientX, y: event.clientY }
  if (![point.x, point.y].every(Number.isFinite)) return
  current.moved ||= isDrag(current.start, point)
  if (!current.moved) return
  if (current.iri && current.origin) {
    const next = dragPosition(current.origin, current.start, point, current.camera.scale)
    if (![next.x, next.y].every(Number.isFinite)) return
    if (current.markId) markPositions.value = { ...markPositions.value, [current.markId]: next }
    else positions.value = { ...positions.value, [current.iri]: next }
  } else {
    const next = dragPosition(current.camera, current.start, point, 1)
    if ([next.x, next.y].every(Number.isFinite)) camera.value = { ...current.camera, ...next }
  }
}
function finishDrag(event?: PointerEvent, cancel = false) {
  const current = drag.value
  if (!current || (event && event.pointerId !== current.pointerId)) return
  const owned =
    current.revision === props.graph.graph_revision_id && current.layoutKey === layoutKey()
  if (cancel && owned) {
    if (current.markId && current.origin)
      markPositions.value = { ...markPositions.value, [current.markId]: current.origin }
    else if (current.iri && current.origin)
      positions.value = { ...positions.value, [current.iri]: current.origin }
    else camera.value = current.camera
  }
  suppressClick = current.moved || cancel
  drag.value = null
  if (scrollEl.value?.hasPointerCapture(current.pointerId))
    scrollEl.value.releasePointerCapture(current.pointerId)
  // Pointer capture retargets click to the viewport, so dispatch node selection here.
  if (owned && !cancel && !current.moved && current.iri) {
    current.target.focus({ preventScroll: true })
    selectNode(current.iri)
  }
}
watch([() => props.graph.graph_revision_id, layoutKey], () => finishDrag(undefined, true))
onBeforeUnmount(() => finishDrag(undefined, true))
function selectNode(iri: string) {
  // At overview zoom, bring the selection into readable view instead of inflating it over neighbours.
  if (camera.value.scale < 0.8) focus(iri)
  emit('select', iri)
}
function onNodeClick(event: MouseEvent, iri: string) {
  if (event.detail === 0 && !suppressClick) selectNode(iri)
}
let tabNavigation: KeyboardEvent | null = null
function recordTabNavigation(event: KeyboardEvent) {
  tabNavigation = event.key === 'Tab' ? event : null
  if (event.key !== 'Tab') return
  // Native focus follows keydown within this task. Do not redirect later
  // programmatic focus, such as returning from the inspector to its selection.
  setTimeout(() => {
    if (tabNavigation === event) tabNavigation = null
  }, 0)
}
onMounted(() => document.addEventListener('keydown', recordTabNavigation, true))
onBeforeUnmount(() => document.removeEventListener('keydown', recordTabNavigation, true))
function onNodeFocus(event: FocusEvent) {
  const navigation = tabNavigation
  // Consume the Tab on its focus transition. A later paint-order restoration
  // must not reuse it while the timer queue is still waiting to run.
  tabNavigation = null
  const previous = event.relatedTarget as Element | null
  if (!navigation || (previous?.classList.contains('node') && scrollEl.value?.contains(previous)))
    return
  const boundary = navigation.shiftKey ? nodes.value.at(-1) : nodes.value[0]
  const elements = [...(scrollEl.value?.querySelectorAll<SVGElement>('.node') ?? [])]
  elements.find((element) => element.dataset.iri === boundary?.iri)?.focus({ preventScroll: true })
}
function onNodeTab(event: KeyboardEvent, iri: string) {
  const index = nodes.value.findIndex((node) => node.iri === iri)
  const next = nodes.value[index + (event.shiftKey ? -1 : 1)]
  const elements = [...(scrollEl.value?.querySelectorAll<SVGElement>('.node') ?? [])]
  if (next) {
    event.preventDefault()
    elements.find((element) => element.dataset.iri === next.iri)?.focus({ preventScroll: true })
  } else {
    // Let native Tab leave the node collection from its physical boundary, even
    // when selection has raised a different node to the last paint position.
    const boundary = event.shiftKey ? elements[0] : elements.at(-1)
    boundary?.focus({ preventScroll: true })
  }
}
function onCanvasKey(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    // Dismiss only the active canvas interaction; keep the object's inspector open.
    if (drag.value || showLegend.value || showMinimap.value) {
      event.preventDefault()
      event.stopPropagation()
    }
    spacePressed.value = false
    if (drag.value) {
      const target = drag.value.target
      finishDrag(undefined, true)
      target.focus({ preventScroll: true })
    } else if (showLegend.value) closeLegend()
    else if (showMinimap.value) closeMinimap()
    return
  }
  if (event.target !== scrollEl.value && !(event.target as Element).classList.contains('minimap'))
    return
  if (event.key === ' ') {
    event.preventDefault()
    spacePressed.value = true
    return
  }
  const shifts: Record<string, Point> = {
    ArrowLeft: { x: 48, y: 0 },
    ArrowRight: { x: -48, y: 0 },
    ArrowUp: { x: 0, y: 48 },
    ArrowDown: { x: 0, y: -48 },
  }
  if (shifts[event.key]) {
    event.preventDefault()
    camera.value = {
      ...camera.value,
      x: camera.value.x + shifts[event.key]!.x,
      y: camera.value.y + shifts[event.key]!.y,
    }
  } else if (['+', '=', '-', 'Home'].includes(event.key)) {
    event.preventDefault()
    if (event.key === 'Home') fitView()
    else zoom(event.key === '-' ? 1 / 1.2 : 1.2)
  }
}
</script>

<template>
  <div
    class="canvas-panel"
    @keydown="onCanvasKey"
    @keyup.space="spacePressed = false"
    @focusout="spacePressed = false"
  >
    <UiAlert v-for="notice in layout.notices ?? []" :key="notice.key" type="warning">
      {{ t(`semanticView.${notice.key}`, { count: notice.count ?? 0 }) }}
    </UiAlert>
    <div class="canvas-frame">
      <div class="canvas-toolbar" role="toolbar" :aria-label="t('graphUi.canvasTools')">
        <button
          type="button"
          :disabled="camera.scale <= MIN_SCALE"
          :aria-label="t('graph.zoomOut')"
          :title="t('graph.zoomOut')"
          @click="zoom(1 / 1.2)"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            <path d="M3 8H13" />
          </svg>
        </button>
        <output class="zoom-value" :aria-label="t('graphUi.zoomLevel')"
          >{{ Math.round(camera.scale * 100) }}{{ t('graphUi.percent') }}</output
        >
        <button
          type="button"
          :disabled="camera.scale >= MAX_SCALE"
          :aria-label="t('graph.zoomIn')"
          :title="t('graph.zoomIn')"
          @click="zoom(1.2)"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            <path d="M3 8H13 M8 3V13" />
          </svg>
        </button>
        <span class="tool-divider" aria-hidden="true" />
        <button type="button" @click="fitView">{{ t('graphUi.fitView') }}</button>
        <button type="button" :disabled="!previousCamera" @click="restoreView">
          {{ t('graphUi.restoreView') }}
        </button>
        <button
          ref="legendButton"
          type="button"
          :aria-expanded="showLegend"
          :aria-controls="`${id}-legend`"
          @click="showLegend = !showLegend"
        >
          {{ t('graphUi.legend') }}
        </button>
        <button
          ref="minimapButton"
          type="button"
          :aria-expanded="showMinimap"
          :aria-controls="`${id}-minimap`"
          @click="showMinimap = !showMinimap"
        >
          {{ t('graphUi.minimap') }}
        </button>
      </div>
      <div
        ref="scrollEl"
        class="canvas-scroll"
        :class="{ dragging: drag?.moved }"
        tabindex="0"
        role="region"
        :aria-label="t('page.graphBrowse')"
        :aria-describedby="`${id}-help`"
        @wheel.prevent="onWheel"
        @pointerdown.prevent="startDrag($event)"
        @pointermove="moveDrag"
        @pointerup="finishDrag($event)"
        @pointercancel="finishDrag($event, true)"
        @lostpointercapture="finishDrag($event, true)"
      >
        <svg
          :width="size.width"
          :height="size.height"
          :viewBox="`0 0 ${size.width} ${size.height}`"
          role="group"
          :aria-label="t('page.graphBrowse')"
        >
          <defs>
            <marker
              v-for="kind in ['direct', 'derived', 'selected']"
              :id="`${id}-${kind}-arrow`"
              :key="kind"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="5"
              markerHeight="5"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" :class="`arrow-${kind}`" />
            </marker>
          </defs>
          <g
            :transform="`translate(${camera.x},${camera.y}) scale(${camera.scale})`"
            class="graph-scene"
          >
            <text
              v-for="title in layout.titles ?? []"
              :key="title.id"
              :x="title.x"
              :y="title.y"
              :text-anchor="title.anchor ?? 'middle'"
              class="layout-title"
            >
              {{ title.text }}
            </text>
            <template v-if="marks">
              <text
                v-for="group in layout.groups"
                :key="group.type"
                x="35"
                :y="group.y"
                class="group-label"
              >
                {{ shortName(group.type) }}
              </text>
              <g
                v-for="mark in marks"
                :key="mark.id"
                class="mark-group"
                :class="{
                  selected: selectedIri === mark.iri,
                  highlighted: mark.iri && nodeHighlighted(mark.iri),
                }"
                :transform="`translate(${mark.offsetX},${mark.offsetY})`"
                :role="mark.iri ? 'button' : undefined"
                :tabindex="mark.iri ? 0 : undefined"
                :aria-label="mark.label ?? mark.iri"
                :aria-pressed="mark.iri ? selectedIri === mark.iri : undefined"
                :data-mark-id="mark.id"
                :data-iri="mark.iri"
                @pointerdown.stop.prevent="startDrag($event, mark.iri, mark.id)"
                @click.stop="mark.iri && onNodeClick($event, mark.iri)"
                @keydown.enter.prevent.stop="mark.iri && selectNode(mark.iri)"
                @keydown.space.prevent.stop="mark.iri && selectNode(mark.iri)"
              >
                <title>{{ mark.label }}{{ mark.sublabel ? ` · ${mark.sublabel}` : '' }}</title>
                <path v-if="mark.kind === 'sector'" :d="mark.path" class="mark" :fill="mark.fill" />
                <rect
                  v-else-if="mark.kind === 'rect'"
                  :x="mark.x - (mark.w ?? 0) / 2"
                  :y="mark.y - (mark.h ?? 0) / 2"
                  :width="mark.w"
                  :height="mark.h"
                  class="mark"
                  :fill="mark.fill"
                />
                <circle
                  v-else
                  :cx="mark.x"
                  :cy="mark.y"
                  :r="mark.r"
                  class="mark"
                  :fill="mark.fill"
                />
                <text
                  v-if="
                    mark.label && showGraphLabel(camera.scale, selectedIri === mark.iri, 'node')
                  "
                  :x="mark.x"
                  :y="mark.labelY ?? mark.y"
                  text-anchor="middle"
                  class="mark-label"
                >
                  {{ mark.label }}
                </text>
                <text
                  v-if="mark.sublabel && camera.scale >= 0.65"
                  :x="mark.x"
                  :y="(mark.labelY ?? mark.y) + 14"
                  text-anchor="middle"
                  class="mark-sublabel"
                >
                  {{ mark.sublabel }}
                </text>
                <g
                  v-if="mark.iri && nodeFlagged(mark.iri)"
                  :transform="`translate(${mark.x + 12},${mark.y - 12})`"
                  class="quality-flag"
                  role="img"
                  :aria-label="t('graph.qualityFlagged')"
                >
                  <circle r="8" />
                  <path d="M0-4V1 M0 3V4" />
                </g>
              </g>
            </template>
            <template v-else>
              <g
                v-for="edge in paths"
                :key="edge.key"
                class="edge-group"
                :class="{
                  derived: edge.kind === 'DERIVED',
                  selected: edgeSelected(edge),
                  highlighted: edgeHighlighted(edge),
                }"
                role="button"
                tabindex="0"
                :aria-label="edgeDescription(edge)"
                :aria-pressed="edgeSelected(edge)"
                :data-edge-key="edgeKey(edge)"
                @pointerdown.stop
                @click.stop="selectEdge(edge)"
                @keydown.enter.prevent.stop="selectEdge(edge)"
                @keydown.space.prevent.stop="selectEdge(edge)"
              >
                <title>{{ edgeDescription(edge) }}</title>
                <path :d="edge.path" class="edge-hit" vector-effect="non-scaling-stroke" />
                <path
                  :d="edge.path"
                  class="edge"
                  :marker-end="`url(#${id}-${edgeSelected(edge) ? 'selected' : edge.kind.toLowerCase()}-arrow)`"
                />
                <g
                  v-if="
                    edge.label &&
                    showGraphLabel(camera.scale, importantEdge(edge) || overviewLabels, 'edge')
                  "
                  :transform="`translate(${edge.label.x},${edge.label.y}) scale(${edgeLabelScale(edge)})`"
                  class="edge-label"
                >
                  <text text-anchor="middle" dy="-4">{{ edgeName(edge) }}</text>
                </g>
              </g>
              <g
                v-for="node in paintedNodes"
                :key="node.iri"
                :transform="`translate(${node.x},${node.y})`"
                class="node"
                :class="{
                  center: neighborhood && node.distance === 0,
                  highlighted: nodeHighlighted(node.iri),
                  selected: selectedIri === node.iri,
                }"
                tabindex="0"
                role="button"
                :aria-label="t('graph.exploreEntity', { iri: nodeName(node) })"
                :aria-pressed="selectedIri === node.iri"
                :data-iri="node.iri"
                :style="{ '--node-color': typePaint(node.type_iri) }"
                @pointerdown.stop.prevent="startDrag($event, node.iri)"
                @click.stop="onNodeClick($event, node.iri)"
                @focus="onNodeFocus"
                @keydown.tab="onNodeTab($event, node.iri)"
                @keydown.enter.prevent.stop="selectNode(node.iri)"
                @keydown.space.prevent.stop="selectNode(node.iri)"
              >
                <title>
                  {{ nodeTitle(node) }}{{ nodeBadgeText(node) ? ` · ${nodeBadgeText(node)}` : '' }}
                </title>
                <g :transform="`scale(${nodeDisplayScale(node.iri)})`">
                  <circle class="selection-ring" :r="NODE_RADIUS + 5" />
                  <circle class="node-body" :r="NODE_RADIUS" />
                  <g
                    :transform="`translate(0,${nodeLabelVisible(node) ? -17 : 0})`"
                    class="node-icon"
                    aria-hidden="true"
                  >
                    <circle r="13" class="icon-disc" />
                    <path :d="typeIcon(node.type_iri)" class="type-icon" />
                  </g>
                  <text v-if="nodeLabelVisible(node)" text-anchor="middle" class="node-name">
                    <tspan
                      v-for="(line, index) in nodeNameLines(nodeName(node))"
                      :key="index"
                      x="0"
                      :y="index * 15 + (nodeNameLines(nodeName(node)).length > 1 ? 9 : 13)"
                    >
                      {{ line }}
                    </tspan>
                  </text>
                  <g
                    v-if="nodeFlagged(node.iri)"
                    transform="translate(32,-30)"
                    class="quality-flag"
                    role="img"
                    :aria-label="t('graph.qualityFlagged')"
                  >
                    <circle r="9" />
                    <path d="M0-5V1 M0 3V5" />
                  </g>
                </g>
              </g>
            </template>
          </g>
        </svg>
      </div>
      <section
        v-if="showLegend"
        :id="`${id}-legend`"
        class="legend-panel"
        :aria-label="t('graphUi.legend')"
        @keydown.esc.stop.prevent="closeLegend"
      >
        <div class="panel-heading">
          <strong>{{ t('graphUi.legend') }}</strong
          ><button type="button" @click="closeLegend">{{ t('graphUi.closePanel') }}</button>
        </div>
        <span class="legend direct">{{ t('graph.directRelation') }}</span>
        <span class="legend derived">{{ t('graph.derived') }}</span>
        <span class="legend selected">{{ t('graphUi.selected') }}</span>
        <span class="legend flagged">{{ t('graph.qualityFlagged') }}</span>
        <span v-for="type in legendTypes" :key="type" class="legend-type"
          ><svg width="20" height="20" viewBox="-10 -10 20 20" aria-hidden="true">
            <path :d="typeIcon(type)" class="type-icon" :style="{ color: typePaint(type) }" /></svg
          >{{ shortName(type) }}</span
        >
      </section>
      <section
        v-if="showMinimap"
        :id="`${id}-minimap`"
        class="minimap-panel"
        :aria-label="t('graph.minimap')"
        @keydown.esc.stop.prevent="closeMinimap"
      >
        <div class="panel-heading">
          <span>{{ t('graphUi.loadedMap') }}</span
          ><button type="button" @click="closeMinimap">{{ t('graphUi.closePanel') }}</button>
        </div>
        <svg
          class="minimap"
          width="180"
          height="110"
          :viewBox="minimapBox"
          tabindex="0"
          role="group"
          :aria-label="t('graphUi.minimapHelp')"
          @click="onMinimapClick"
        >
          <rect
            :x="bounds.x"
            :y="bounds.y"
            :width="bounds.width"
            :height="bounds.height"
            class="minimap-bg"
          />
          <circle
            v-for="dot in minimapDots"
            :key="dot.id"
            :cx="dot.x"
            :cy="dot.y"
            :r="Math.max(4, bounds.width / 140)"
            :fill="dot.fill"
          />
          <rect
            class="minimap-viewport"
            :x="viewport.x"
            :y="viewport.y"
            :width="viewport.width"
            :height="viewport.height"
            vector-effect="non-scaling-stroke"
          />
        </svg>
      </section>
      <p :id="`${id}-help`" class="canvas-help">{{ t('graphUi.canvasHelp') }}</p>
    </div>
  </div>
</template>

<style scoped>
.canvas-panel {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  min-height: 0;
  width: 100%;
  height: 100%;
}
.canvas-frame {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: var(--canvas, var(--surface-muted));
  border: 0;
  border-radius: 0;
}
.canvas-scroll {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  touch-action: none;
  cursor: grab;
  user-select: none;
}
.canvas-scroll > svg {
  display: block;
}
.canvas-scroll.dragging,
.canvas-scroll.dragging .node {
  cursor: grabbing;
}
.canvas-toolbar {
  position: absolute;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px;
  bottom: 16px;
  left: 16px;
  width: fit-content;
  max-width: calc(100% - 20px);
  padding: 4px;
  background: var(--surface-panel);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-control);
  box-shadow: var(--shadow-sm);
}
button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 30px;
  padding: 3px 8px;
  color: var(--foreground-secondary);
  font: inherit;
  font-size: var(--font-caption);
  background: transparent;
  border: 0;
  border-radius: var(--r-sm);
  cursor: pointer;
}
button:hover,
button[aria-expanded='true'] {
  color: var(--action-primary);
  background: var(--action-soft);
}
button:disabled {
  color: var(--foreground-disabled);
  cursor: default;
}
button svg {
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
}
.tool-divider {
  height: 18px;
  width: 1px;
  background: var(--border-default);
  margin: 0 4px;
}
.zoom-value {
  min-width: 40px;
  text-align: center;
  font-size: var(--font-caption);
  color: var(--foreground-secondary);
  font-variant-numeric: tabular-nums;
}
.canvas-help {
  position: absolute;
  pointer-events: none;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.legend-panel,
.minimap-panel {
  position: absolute;
  z-index: 3;
  padding: 10px;
  background: var(--surface-panel);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-control);
  box-shadow: var(--shadow-md);
}
.legend-panel {
  top: 60px;
  left: 10px;
  max-width: calc(100% - 20px);
  max-height: calc(100% - 110px);
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: var(--font-caption);
}
.panel-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  font-size: var(--font-caption);
  color: var(--foreground-secondary);
}
.panel-heading strong {
  font-weight: 500;
  color: var(--foreground-primary);
}
.panel-heading button {
  min-height: 24px;
  padding: 2px 5px;
}
.legend,
.legend-type {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.legend::before {
  content: '';
  width: 24px;
  border-top: 2px solid var(--foreground-secondary);
}
.legend.derived::before {
  border-top: 2px dashed var(--graph-derived);
}
.legend.selected::before {
  width: 15px;
  height: 15px;
  border: 3px double var(--action-primary);
  border-radius: 50%;
}
.legend.flagged::before {
  width: 12px;
  height: 12px;
  border: 2px solid var(--danger);
  border-radius: 50%;
}
.minimap-panel {
  right: 10px;
  bottom: 32px;
}
.minimap {
  display: block;
  cursor: crosshair;
}
.minimap-bg {
  fill: var(--surface-muted);
}
.minimap-viewport {
  fill: var(--action-soft);
  stroke: var(--action-primary);
  stroke-width: 1.5;
}
.edge-group {
  cursor: pointer;
}
.edge {
  fill: none;
  stroke: color-mix(in srgb, var(--foreground-muted) 62%, var(--canvas));
  stroke-width: 1.25;
  pointer-events: none;
}
.edge-hit {
  fill: none;
  stroke: transparent;
  stroke-width: 14;
  pointer-events: stroke;
}
.edge-group.derived .edge {
  stroke: var(--graph-derived);
  stroke-dasharray: 7 5;
}
.edge-group.selected .edge,
.edge-group.highlighted .edge {
  stroke: var(--action-primary);
  stroke-width: 3;
}
.edge-label text {
  fill: var(--foreground-secondary);
  stroke: var(--canvas, var(--surface-muted));
  stroke-width: 5;
  stroke-linejoin: round;
  paint-order: stroke;
  font-size: var(--font-caption);
  font-weight: 500;
}
.edge-group.derived .edge-label text {
  fill: var(--graph-derived);
}
.edge-group.selected .edge-label text {
  fill: var(--action-primary);
  stroke: var(--surface-selected);
  stroke-width: 9;
  font-weight: 600;
}
.edge-group:focus-visible .edge {
  stroke-width: 3;
  filter: drop-shadow(0 0 2px var(--action-primary));
}
.arrow-direct {
  fill: color-mix(in srgb, var(--foreground-muted) 72%, var(--canvas));
}
.arrow-derived {
  fill: var(--graph-derived);
}
.arrow-selected {
  fill: var(--action-primary);
}
.node {
  cursor: pointer;
  outline: none;
}
.node-body {
  fill: color-mix(in srgb, var(--node-color) 6%, var(--surface-panel));
  stroke: color-mix(in srgb, var(--node-color) 40%, var(--surface-panel));
  stroke-width: 1.25;
}
.node-icon {
  color: var(--node-color);
  pointer-events: none;
}
.icon-disc {
  fill: color-mix(in srgb, var(--node-color) 13%, var(--surface-panel));
}
.selection-ring {
  fill: none;
  stroke: transparent;
  stroke-width: 2;
}
.node.selected .node-body,
.node.highlighted .node-body,
.node.center .node-body,
.node:hover .node-body {
  stroke: var(--node-color);
  stroke-width: 2;
  fill: color-mix(in srgb, var(--node-color) 11%, var(--surface-panel));
}
.node.selected .selection-ring {
  stroke: var(--action-primary);
  stroke-width: 2;
}
.node.highlighted .selection-ring {
  stroke: var(--action-primary);
  stroke-dasharray: 3 3;
}
.node:focus-visible .selection-ring {
  stroke: var(--foreground-primary);
  stroke-dasharray: 2 3;
}
.node-name {
  fill: var(--foreground-primary);
  font-size: var(--font-caption);
  font-weight: 500;
  pointer-events: none;
}
.type-icon {
  fill: none;
  stroke: currentColor;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
  pointer-events: none;
}
.quality-flag circle {
  fill: var(--danger);
  stroke: var(--surface-panel);
  stroke-width: 2;
}
.quality-flag path {
  stroke: var(--action-foreground);
  stroke-width: 2;
  fill: none;
}
.group-label,
.layout-title {
  fill: var(--foreground-secondary);
  font-size: var(--font-caption);
  pointer-events: none;
}
.mark {
  fill-opacity: 0.8;
  stroke: var(--surface-panel);
  stroke-width: 1;
}
.mark-group[role='button'] {
  cursor: pointer;
}
.mark-group.selected .mark,
.mark-group.highlighted .mark,
.mark-group:focus-visible .mark {
  fill-opacity: 1;
  stroke: var(--action-primary);
  stroke-width: 3;
}
.mark-group.selected .mark {
  stroke-dasharray: 5 2;
}
.mark-label,
.mark-sublabel {
  fill: var(--foreground-primary);
  font-size: var(--font-caption);
  stroke: var(--surface-panel);
  stroke-width: 2;
  paint-order: stroke;
  pointer-events: none;
}
.mark-sublabel {
  font-size: 10px;
}
@media (max-width: 48rem) {
  .minimap-panel {
    right: 6px;
    bottom: 48px;
  }
  .canvas-toolbar {
    gap: 0;
  }
  button {
    padding: 3px 6px;
  }
}
</style>
