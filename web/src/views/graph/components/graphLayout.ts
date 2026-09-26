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
): RenderedEdge[] {
  const byIri = new Map(nodes.map((node) => [node.iri, node]))
  const pairs = new Map<string, GraphEdge[]>()
  for (const edge of edges) {
    const key = JSON.stringify([edge.subject, edge.object_].sort())
    const group = pairs.get(key) ?? []
    group.push(edge)
    pairs.set(key, group)
  }
  return [...pairs.values()].flatMap((group) =>
    group.map((edge, index) => {
      const override = overrides?.[edge.id]
      if (override) {
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
      if (source.iri === target.iri) {
        const bend = 90 + index * 35
        path = `M ${source.x - 40} ${source.y - 26} C ${source.x - bend} ${source.y - bend}, ${source.x + bend} ${source.y - bend}, ${source.x + 40} ${source.y - 26}`
        label = { x: source.x, y: source.y - bend - 4 }
      } else {
        const [first, last] = source.iri < target.iri ? [source, target] : [target, source]
        const dx = last.x - first.x
        const dy = last.y - first.y
        const length = Math.hypot(dx, dy)
        const offset = (index - (group.length - 1) / 2) * 42
        const cx = (first.x + last.x) / 2 - (dy / length) * offset
        const cy = (first.y + last.y) / 2 + (dx / length) * offset
        const boundary = (node: typeof source) => {
          const vx = cx - node.x
          const vy = cy - node.y
          const scale = Math.min(80 / Math.abs(vx), 26 / Math.abs(vy))
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
