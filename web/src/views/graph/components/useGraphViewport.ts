import type { Ref } from 'vue'
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'

import type { GraphView } from '@/api/graph'

import type { Camera, Positions } from './graphViewport.ts'
import {
  centerCamera,
  fitCamera,
  MAX_SCALE,
  mergePositions,
  MIN_SCALE,
  NODE_RADIUS,
  pointBounds,
  resizeCamera,
  viewportBounds,
} from './graphViewport.ts'
import type { LayoutResult } from './layouts/index.ts'

export type GraphCanvasContext = {
  graphRevisionId: number
  layoutKey: string
  camera: Camera
  positions: Positions
  markPositions: Positions
  previousCamera: Camera | null
}

const copyPositions = (positions: Positions): Positions =>
  Object.fromEntries(Object.entries(positions).map(([iri, point]) => [iri, { ...point }]))

export function useGraphViewport(
  host: Ref<HTMLElement | null>,
  graph: () => GraphView,
  layout: Ref<LayoutResult>,
  layoutKey: () => string,
) {
  const camera = ref<Camera>({ x: 0, y: 0, scale: 1 })
  const previousCamera = ref<Camera | null>(null)
  const size = ref({ width: 900, height: 600 })
  const positions = shallowRef<Positions>({})
  const markPositions = shallowRef<Positions>({})
  let owner: number | undefined
  let key: string | undefined
  let needsFit = true
  let measured = false

  const nodes = computed(() =>
    layout.value.nodes.map((node) => ({ ...node, ...positions.value[node.iri] })),
  )
  const marks = computed(() =>
    layout.value.marks?.map((mark) => {
      const point = markPositions.value[mark.id] ?? mark
      return { ...mark, offsetX: point.x - mark.x, offsetY: point.y - mark.y }
    }),
  )
  const bounds = computed(() => {
    if (marks.value) {
      // Sector paths can extend beyond their label anchor; retain the layout extent.
      const points = [
        { x: 0, y: 0 },
        { x: layout.value.width, y: layout.value.height },
      ]
      for (const mark of marks.value) {
        const x = mark.x + mark.offsetX
        const y = mark.y + mark.offsetY
        const w = (mark.w ?? 0) / 2 || mark.r || 0
        const h = (mark.h ?? 0) / 2 || mark.r || 0
        points.push({ x: x - w, y: y - h }, { x: x + w, y: y + h })
      }
      return pointBounds(points, 16)
    }
    const points = nodes.value.map((node) => ({ x: node.x, y: node.y }))
    // Account for multiple self loops so fit never clips their arrow or predicate.
    const loops = new Map<string, number>()
    for (const edge of layout.value.edges ?? graph().edges) {
      if (edge.subject === edge.object_) loops.set(edge.subject, (loops.get(edge.subject) ?? 0) + 1)
    }
    for (const node of nodes.value) {
      const count = loops.get(node.iri)
      if (count) points.push({ x: node.x, y: node.y - 90 - (count - 1) * 35 })
    }
    points.push(...(layout.value.titles ?? []))
    return pointBounds(points, NODE_RADIUS + 12)
  })
  const viewport = computed(() => viewportBounds(camera.value, size.value))

  function autoFit() {
    if (needsFit && measured && (nodes.value.length || marks.value?.length)) {
      camera.value = fitCamera(bounds.value, size.value)
      needsFit = false
    }
  }

  watch(
    [() => graph().graph_revision_id, layoutKey, layout],
    ([revision, nextKey]) => {
      if (owner !== revision || key !== nextKey) {
        previousCamera.value = owner === revision ? { ...camera.value } : null
        positions.value = {}
        markPositions.value = {}
        needsFit = true
        owner = revision
        key = nextKey
      }
      positions.value = mergePositions(
        positions.value,
        layout.value.nodes,
        layout.value.edges ?? graph().edges,
      )
      const next = { ...markPositions.value }
      for (const mark of layout.value.marks ?? []) next[mark.id] ??= { x: mark.x, y: mark.y }
      markPositions.value = next
      autoFit()
    },
    { immediate: true, flush: 'sync' },
  )

  function fitView() {
    previousCamera.value = { ...camera.value }
    camera.value = fitCamera(bounds.value, size.value)
    needsFit = false
  }

  function focus(iri: string): boolean {
    const node = nodes.value.find((item) => item.iri === iri)
    const mark = marks.value?.find((item) => item.iri === iri)
    const point = mark ? { x: mark.x + mark.offsetX, y: mark.y + mark.offsetY } : node
    if (!point) return false
    previousCamera.value = { ...camera.value }
    camera.value = centerCamera(
      { ...camera.value, scale: Math.max(0.8, camera.value.scale) },
      point,
      size.value,
    )
    needsFit = false
    return true
  }

  function restoreView() {
    if (!previousCamera.value) return
    camera.value = { ...previousCamera.value }
    previousCamera.value = null
    needsFit = false
  }

  function getContext(): GraphCanvasContext {
    return {
      graphRevisionId: graph().graph_revision_id,
      layoutKey: layoutKey(),
      camera: { ...camera.value },
      positions: copyPositions(positions.value),
      markPositions: copyPositions(markPositions.value),
      previousCamera: previousCamera.value ? { ...previousCamera.value } : null,
    }
  }

  function restoreContext(context: GraphCanvasContext): boolean {
    if (context.graphRevisionId !== graph().graph_revision_id || context.layoutKey !== layoutKey())
      return false
    if (
      !Object.values(context.camera).every(Number.isFinite) ||
      context.camera.scale < MIN_SCALE ||
      context.camera.scale > MAX_SCALE
    )
      return false
    if (
      ![...Object.values(context.positions), ...Object.values(context.markPositions)].every(
        (point) => Number.isFinite(point.x) && Number.isFinite(point.y),
      )
    )
      return false
    positions.value = mergePositions(
      copyPositions(context.positions),
      layout.value.nodes,
      layout.value.edges ?? graph().edges,
    )
    markPositions.value = { ...markPositions.value, ...copyPositions(context.markPositions) }
    camera.value = { ...context.camera }
    previousCamera.value = context.previousCamera ? { ...context.previousCamera } : null
    needsFit = false
    return true
  }

  let observer: ResizeObserver | undefined
  onMounted(() => {
    if (!host.value) return
    const measure = () => {
      if (!host.value?.clientWidth || !host.value.clientHeight) return
      const next = { width: host.value.clientWidth, height: host.value.clientHeight }
      if (measured && !needsFit) {
        camera.value = resizeCamera(camera.value, size.value, next)
        if (previousCamera.value)
          previousCamera.value = resizeCamera(previousCamera.value, size.value, next)
      }
      size.value = next
      measured = true
      autoFit()
    }
    measure()
    observer = new ResizeObserver(measure)
    observer.observe(host.value)
  })
  onBeforeUnmount(() => observer?.disconnect())

  return {
    camera,
    previousCamera,
    size,
    positions,
    nodes,
    marks,
    bounds,
    viewport,
    fitView,
    focus,
    restoreView,
    getContext,
    restoreContext,
  }
}
