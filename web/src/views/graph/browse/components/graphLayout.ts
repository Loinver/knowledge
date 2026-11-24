import type { GraphView } from '@/api/graph'

import type { EdgePathOverride, PositionedNode } from './layouts/index.ts'

export type { LayoutPlugin, LayoutResult, PositionedNode } from './layouts/index.ts'
export { LAYOUT_IDS, LAYOUTS, resolveLayout } from './layouts/index.ts'

type GraphEdge = GraphView['edges'][number]
type Point = { x: number; y: number }
type Quadratic = { start: Point; control: Point; end: Point }
type CircleOptions = {
  radius: number | ((node: PositionedNode) => number)
  originalNodes: PositionedNode[]
  /** Opt in for hierarchy renderers; the camera scale keeps hit clearance in screen pixels. */
  avoidNodes?: boolean
  scale?: number
}

export type RenderedEdge = GraphEdge & {
  path: string
  key: string
  label?: Point
  /** Conservative geometry bounds for the host's fit/minimap; never persisted. */
  bounds?: { x: number; y: number; width: number; height: number }
}

function circleBoundary(node: PositionedNode, control: Point, radius: number): Point {
  const length = Math.hypot(control.x - node.x, control.y - node.y) || 1
  return {
    x: node.x + ((control.x - node.x) / length) * radius,
    y: node.y + ((control.y - node.y) / length) * radius,
  }
}

function segmentDistance(point: Point, start: Point, end: Point): number {
  const dx = end.x - start.x
  const dy = end.y - start.y
  const lengthSquared = dx * dx + dy * dy
  const t = lengthSquared
    ? Math.max(
        0,
        Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / lengthSquared),
      )
    : 0
  return Math.hypot(point.x - start.x - t * dx, point.y - start.y - t * dy)
}

/** Subdivision uses a conservative curve/chord error bound, rather than sparse samples. */
function intersectsCircle(curve: Quadratic, center: Point, radius: number, depth = 0): boolean {
  const { start, control, end } = curve
  if (
    center.x + radius < Math.min(start.x, control.x, end.x) ||
    center.x - radius > Math.max(start.x, control.x, end.x) ||
    center.y + radius < Math.min(start.y, control.y, end.y) ||
    center.y - radius > Math.max(start.y, control.y, end.y)
  )
    return false
  const error = segmentDistance(control, start, end) / 2
  if (error <= 0.25 || depth === 10) return segmentDistance(center, start, end) <= radius + error
  const left = { x: (start.x + control.x) / 2, y: (start.y + control.y) / 2 }
  const right = { x: (control.x + end.x) / 2, y: (control.y + end.y) / 2 }
  const middle = { x: (left.x + right.x) / 2, y: (left.y + right.y) / 2 }
  return (
    intersectsCircle({ start, control: left, end: middle }, center, radius, depth + 1) ||
    intersectsCircle({ start: middle, control: right, end }, center, radius, depth + 1)
  )
}

function quadraticBounds({ start, control, end }: Quadratic) {
  // The control hull encloses the entire curve, including after asymmetric endpoint dragging.
  const x = Math.min(start.x, control.x, end.x)
  const y = Math.min(start.y, control.y, end.y)
  return {
    x,
    y,
    width: Math.max(start.x, control.x, end.x) - x,
    height: Math.max(start.y, control.y, end.y) - y,
  }
}

function avoidingCurves(
  nodes: PositionedNode[],
  source: PositionedNode,
  target: PositionedNode,
  count: number,
  circles: CircleOptions,
): Quadratic[] {
  const radiusOf = (node: PositionedNode) =>
    typeof circles.radius === 'number' ? circles.radius : circles.radius(node)
  const [first, last] = source.iri < target.iri ? [source, target] : [target, source]
  const dx = last.x - first.x
  const dy = last.y - first.y
  const length = Math.hypot(dx, dy) || 1
  const middle = { x: (first.x + last.x) / 2, y: (first.y + last.y) / 2 }
  const separation = Math.max(1, radiusOf(source) / 42, radiusOf(target) / 42)
  const scale =
    circles.scale && Number.isFinite(circles.scale) && circles.scale > 0 ? circles.scale : 1
  // 7px is half of the non-scaling hit stroke; allow the existing node selection ring too.
  const clearance = 9 / scale
  const obstacles = nodes.filter((node) => node.iri !== source.iri && node.iri !== target.iri)
  const curvesAt = (shift: number, spacing: number) =>
    Array.from({ length: count }, (_, index) => {
      const offset = shift + (index - (count - 1) / 2) * spacing
      const control = { x: middle.x - (dy / length) * offset, y: middle.y + (dx / length) * offset }
      return {
        start: circleBoundary(source, control, radiusOf(source)),
        control,
        end: circleBoundary(target, control, radiusOf(target)),
      }
    })
  const collisions = (curves: Quadratic[]) =>
    curves.reduce(
      (total, curve) =>
        total +
        obstacles.reduce((score, node) => {
          const visibleRadius = radiusOf(node) * (47 / 42)
          // At extreme zoom the hit margin can surround an endpoint too. Prefer a route
          // outside every visible disk even when its entire hit strip cannot fit.
          return (
            score +
            Number(intersectsCircle(curve, node, visibleRadius)) * (count * obstacles.length + 1) +
            Number(intersectsCircle(curve, node, visibleRadius + clearance))
          )
        }, 0),
      0,
    )
  let best = curvesAt(0, 42 * separation)
  let bestScore = collisions(best)
  if (!bestScore || !Math.hypot(dx, dy)) return best
  // Shift the whole pair together: independently detouring each fact can merge parallel paths.
  const spacing = Math.max(42 * separation, 36 / scale)
  const base = Math.max(84, clearance * 2) + (count * spacing) / 2
  for (let attempt = 0; attempt < 12; attempt++) {
    for (const side of [1, -1]) {
      const curves = curvesAt(side * base * 1.5 ** attempt, spacing)
      const score = collisions(curves)
      if (!score) return curves
      if (score < bestScore) {
        best = curves
        bestScore = score
      }
    }
  }
  // Overlapping endpoint/obstacle disks can make clearance impossible. Keep finite geometry.
  return best
}

/**
 * 边路径计算：平行边沿法向偏移、自环三次贝塞尔、端点裁剪到节点边界。
 * 布局提供 edgePaths 覆写（树形折线）时优先使用。
 */
export function graphPaths(
  nodes: PositionedNode[],
  edges: GraphEdge[],
  overrides?: Record<number, EdgePathOverride>,
  circles?: CircleOptions,
): RenderedEdge[] {
  const byIri = new Map(nodes.map((node) => [node.iri, node]))
  const originalByIri = new Map(circles?.originalNodes.map((node) => [node.iri, node]))
  const pairs = new Map<string, GraphEdge[]>()
  for (const edge of edges) {
    const key = JSON.stringify([edge.subject, edge.object_].sort())
    const group = pairs.get(key) ?? []
    group.push(edge)
    pairs.set(key, group)
  }
  return [...pairs.values()].flatMap((group) => {
    const source = byIri.get(group[0]!.subject)
    const target = byIri.get(group[0]!.object_)
    const curves =
      circles?.avoidNodes &&
      source &&
      target &&
      source.iri !== target.iri &&
      !group.some((edge) => overrides?.[edge.id])
        ? avoidingCurves(nodes, source, target, group.length, circles)
        : undefined
    return [...group]
      .sort((a, b) => (a.kind === b.kind ? a.id - b.id : a.kind === 'DIRECT' ? -1 : 1))
      .map((edge, index) => {
        const override = overrides?.[edge.id]
        if (override && !circles) {
          return {
            ...edge,
            path: override.path,
            key: `${edge.kind}-${edge.id}`,
            label: override.label,
          }
        }
        const source = byIri.get(edge.subject)
        const target = byIri.get(edge.object_)
        if (!source || !target) {
          // 边端点不在画布（被隐藏/截断）：不绘制路径
          return { ...edge, path: '', key: `${edge.kind}-${edge.id}` }
        }
        let path: string
        let label: { x: number; y: number } | undefined
        const radius =
          typeof circles?.radius === 'number' ? circles.radius : circles?.radius(source)
        const targetRadius =
          typeof circles?.radius === 'number' ? circles.radius : circles?.radius(target)
        // Enlarged selected nodes keep readable labels at distant zoom; their parallel
        // curves and self-loop labels need the same spacing in screen coordinates.
        const separation = Math.max(1, (radius ?? 42) / 42, (targetRadius ?? 42) / 42)
        const circlePoint = (node: PositionedNode, x: number, y: number) => {
          const length = Math.hypot(x - node.x, y - node.y) || 1
          return {
            x:
              node.x +
              ((x - node.x) / length) *
                (typeof circles?.radius === 'function' ? circles.radius(node) : (radius ?? 42)),
            y:
              node.y +
              ((y - node.y) / length) *
                (typeof circles?.radius === 'function' ? circles.radius(node) : (radius ?? 42)),
          }
        }
        // Existing tree overrides are cubics. Translate their controls with dragged endpoints,
        // and orient them by fact direction (some layout plugins supply the reverse curve).
        if (circles && override && group.length === 1 && source.iri !== target.iri) {
          const values = override.path.match(/-?\d*\.?\d+(?:e[+-]?\d+)?/gi)?.map(Number)
          const oldSource = originalByIri.get(source.iri)
          const oldTarget = originalByIri.get(target.iri)
          if (values?.length === 8 && override.path.includes(' C ') && oldSource && oldTarget) {
            let [sx, sy, cx1, cy1, cx2, cy2, tx, ty] = values as [
              number,
              number,
              number,
              number,
              number,
              number,
              number,
              number,
            ]
            if (
              Math.hypot(tx - oldSource.x, ty - oldSource.y) <
              Math.hypot(sx - oldSource.x, sy - oldSource.y)
            ) {
              ;[sx, sy, cx1, cy1, cx2, cy2, tx, ty] = [tx, ty, cx2, cy2, cx1, cy1, sx, sy]
            }
            // Numeric override IDs can be shared by DIRECT and DERIVED facts.
            if (
              Math.hypot(sx - oldSource.x, sy - oldSource.y) < 1 &&
              Math.hypot(tx - oldTarget.x, ty - oldTarget.y) < 1
            ) {
              cx1 += source.x - sx
              cy1 += source.y - sy
              cx2 += target.x - tx
              cy2 += target.y - ty
              const start = circlePoint(source, cx1, cy1)
              const end = circlePoint(target, cx2, cy2)
              return {
                ...edge,
                key: `${edge.kind}-${edge.id}`,
                path: `M ${start.x} ${start.y} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${end.x} ${end.y}`,
                label: {
                  x: (start.x + 3 * cx1 + 3 * cx2 + end.x) / 8,
                  y: (start.y + 3 * cy1 + 3 * cy2 + end.y) / 8,
                },
              }
            }
          }
        }
        if (curves) {
          const curve = curves[index]!
          const start = source.iri === group[0]!.subject ? curve.start : curve.end
          const end = source.iri === group[0]!.subject ? curve.end : curve.start
          const { control } = curve
          return {
            ...edge,
            key: `${edge.kind}-${edge.id}`,
            path: `M ${start.x} ${start.y} Q ${control.x} ${control.y} ${end.x} ${end.y}`,
            label: {
              x: (start.x + 2 * control.x + end.x) / 4,
              y: (start.y + 2 * control.y + end.y) / 4,
            },
            bounds: quadraticBounds(curve),
          }
        }
        if (source.iri === target.iri) {
          const bend = Math.max(90, (radius ?? 42) * 2) + index * 35 * separation
          const insetX = radius ? radius * Math.SQRT1_2 : 40
          const insetY = radius ? radius * Math.SQRT1_2 : 26
          path = `M ${source.x - insetX} ${source.y - insetY} C ${source.x - bend} ${source.y - bend}, ${source.x + bend} ${source.y - bend}, ${source.x + insetX} ${source.y - insetY}`
          label = { x: source.x, y: source.y - insetY * 0.25 - bend * 0.75 }
        } else {
          const [first, last] = source.iri < target.iri ? [source, target] : [target, source]
          const dx = last.x - first.x
          const dy = last.y - first.y
          const length = Math.hypot(dx, dy) || 1
          const offset = (index - (group.length - 1) / 2) * 42 * separation
          const cx = (first.x + last.x) / 2 - (dy / length) * offset
          const cy = (first.y + last.y) / 2 + (dx / length) * offset
          const boundary = (node: typeof source) => {
            if (radius) {
              const point = circlePoint(node, cx, cy)
              return `${point.x} ${point.y}`
            }
            const vx = cx - node.x
            const vy = cy - node.y
            const scale = vx || vy ? Math.min(80 / Math.abs(vx), 26 / Math.abs(vy)) : 0
            return `${node.x + vx * scale} ${node.y + vy * scale}`
          }
          path = `M ${boundary(source)} Q ${cx} ${cy} ${boundary(target)}`
          // 二次贝塞尔中点：0.25 起 + 0.5 控制点 + 0.25 终
          label = {
            x: 0.25 * source.x + 0.5 * cx + 0.25 * target.x,
            y: 0.25 * source.y + 0.5 * cy + 0.25 * target.y,
          }
        }
        return { ...edge, path, key: `${edge.kind}-${edge.id}`, label }
      })
  })
}
