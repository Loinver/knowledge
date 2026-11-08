import type { GraphView } from '@/api/graph'

import type { EdgePathOverride, PositionedNode } from './layouts/index.ts'

export type { LayoutPlugin, LayoutResult, PositionedNode } from './layouts/index.ts'
export { LAYOUT_IDS, LAYOUTS, resolveLayout } from './layouts/index.ts'

type GraphEdge = GraphView['edges'][number]

export type RenderedEdge = GraphEdge & {
  path: string
  key: string
  label?: { x: number; y: number }
}

/**
 * 边路径计算：平行边沿法向偏移、自环三次贝塞尔、端点裁剪到节点边界。
 * 布局提供 edgePaths 覆写（树形折线）时优先使用。
 */
export function graphPaths(
  nodes: PositionedNode[],
  edges: GraphEdge[],
  overrides?: Record<number, EdgePathOverride>,
  circles?: {
    radius: number | ((node: PositionedNode) => number)
    originalNodes: PositionedNode[]
  },
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
  return [...pairs.values()].flatMap((group) =>
    [...group]
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
      }),
  )
}
