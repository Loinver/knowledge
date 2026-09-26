/**
 * 图谱形态注册表（第二批）：每个形态一个纯函数布局插件。
 *
 * 布局只做位置计算（与渲染分离），可被 node --test 直接断言；
 * GraphCanvas 消费 {width,height,groups,nodes,edgePaths?} 渲染。
 * 形态 id 与后端形态推荐（graph/layout-recommendations）一一对应：
 * 组织树 org_tree / 股权穿透 equity_tree / 实际控制人链 control_chain /
 * 力导向 force / 时间轴 timeline / 供应链 supply_chain / 本体模式 schema，
 * 以及通用网格 type_grid 与自我中心环 ring（G-11）。
 * path（G-12）与 diff（G-24）是查询/对比模式，由 GraphBrowse 单独实现。
 */
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation } from 'd3-force'
import { hierarchy, tree as d3tree } from 'd3-hierarchy'

import type { GraphView } from '@/api/graph'

export type GraphViewNode = GraphView['nodes'][number]
export type GraphViewEdge = GraphView['edges'][number]
export type PositionedNode = GraphViewNode & { x: number; y: number }
export type EdgePathOverride = { path: string; label?: { x: number; y: number } }

export type LayoutResult = {
  width: number
  height: number
  groups: { type: string; y: number; nodes: PositionedNode[] }[]
  nodes: PositionedNode[]
  /** 布局可覆写边路径（树形折线等）；缺省时用 graphPaths 的曲线。 */
  edgePaths?: Record<number, EdgePathOverride>
}

export type LayoutCompute = (graph: Pick<GraphView, 'nodes' | 'edges'>) => LayoutResult
export type LayoutPlugin = { id: string; compute: LayoutCompute }

export const NODE_W = 160
export const NODE_H = 52

function gridLayout(nodes: GraphViewNode[]): LayoutResult {
  let row = 0
  const groups = [...new Set(nodes.map((node) => node.type_iri))].map((type) => {
    const members = nodes.filter((node) => node.type_iri === type)
    const y = row * 110 + 35
    const placed = members.map((node, index) => ({
      ...node,
      x: 115 + (index % 4) * 215,
      y: y + 55 + Math.floor(index / 4) * 110,
    }))
    row += Math.ceil(members.length / 4) + 1
    return { type, y, nodes: placed }
  })
  return {
    width: 900,
    height: Math.max(480, row * 110),
    groups,
    nodes: groups.flatMap((group) => group.nodes),
  }
}

/** 通用网格（全图总览，按类型分行）。 */
const typeGrid: LayoutPlugin = { id: 'type_grid', compute: (graph) => gridLayout(graph.nodes) }

function ringLayout(nodes: GraphViewNode[]): LayoutResult {
  const rings = [0, 1, 2].map((distance) => nodes.filter((node) => node.distance === distance))
  const radii = [0, Math.max(210, (rings[1]!.length * 180) / (2 * Math.PI)), 0]
  radii[2] = rings[2]!.length
    ? Math.max(radii[1]! + 210, (rings[2]!.length * 180) / (2 * Math.PI))
    : 0
  const size = Math.max(700, Math.max(...radii) * 2 + 220)
  return {
    width: size,
    height: size,
    groups: [],
    nodes: rings.flatMap((ring, distance) =>
      ring.map((node, index) => {
        const angle = (2 * Math.PI * index) / ring.length - Math.PI / 2
        return {
          ...node,
          x: size / 2 + Math.cos(angle) * radii[distance]!,
          y: size / 2 + Math.sin(angle) * radii[distance]!,
        }
      }),
    ),
  }
}

/** G-11 自我中心距离环（1/2 度，中心高亮）。 */
const ring: LayoutPlugin = { id: 'ring', compute: (graph) => ringLayout(graph.nodes) }

/** G-10 力导向关系网络：确定性模拟（固定迭代 + 固定初值），可测可复现。 */
const force: LayoutPlugin = {
  id: 'force',
  compute: (graph) => {
    const nodes = graph.nodes.map((node, index) => ({
      ...node,
      x: ((index * 97) % 860) + 40,
      y: ((index * 53) % 560) + 40,
    }))
    const byIri = new Map(nodes.map((node) => [node.iri, node]))
    const links = graph.edges
      .filter((edge) => byIri.has(edge.subject) && byIri.has(edge.object_))
      .map((edge) => ({ source: byIri.get(edge.subject)!, target: byIri.get(edge.object_)! }))
    forceSimulation(nodes as never)
      .force(
        'link',
        forceLink(links as never)
          .distance(170)
          .strength(0.5),
      )
      .force('charge', forceManyBody().strength(-360))
      .force('center', forceCenter(450, 330))
      .force('collide', forceCollide(95))
      .stop()
      .tick(220)
    const placed = nodes.map((node) => ({
      ...node,
      x: Math.max(90, Math.min(830, node.x ?? 450)),
      y: Math.max(50, Math.min(620, node.y ?? 330)),
    }))
    return { width: 900, height: 660, groups: [], nodes: placed }
  },
}

/**
 * 从边集合取一父映射：edge (child -> parent) 语义（自引用/汇报线）。
 * 每个节点只保留第一条父边，因此产物必是森林，环结构会产生空根集。
 */
function parentLinks(
  nodes: GraphViewNode[],
  edges: GraphViewEdge[],
): Map<string, { parent: string; edgeId: number }> {
  const iris = new Set(nodes.map((node) => node.iri))
  const parents = new Map<string, { parent: string; edgeId: number }>()
  for (const edge of edges) {
    if (!iris.has(edge.subject) || !iris.has(edge.object_)) continue
    if (edge.subject === edge.object_) continue
    if (!parents.has(edge.subject)) {
      parents.set(edge.subject, { parent: edge.object_, edgeId: edge.id })
    }
  }
  return parents
}

function elbow(
  source: { x: number; y: number },
  target: { x: number; y: number },
): EdgePathOverride {
  const midY = (source.y + target.y) / 2
  return {
    path: `M ${source.x} ${source.y} C ${source.x} ${midY}, ${target.x} ${midY}, ${target.x} ${target.y}`,
    label: { x: (source.x + target.x) / 2, y: midY },
  }
}

function edgeOverrides(
  placed: PositionedNode[],
  parents: Map<string, { parent: string; edgeId: number }>,
): Record<number, EdgePathOverride> {
  const byIri = new Map(placed.map((node) => [node.iri, node]))
  const overrides: Record<number, EdgePathOverride> = {}
  for (const [child, link] of parents) {
    const source = byIri.get(child)
    const target = byIri.get(link.parent)
    if (source && target) overrides[link.edgeId] = elbow(source, target)
  }
  return overrides
}

function treeLayoutFactory(id: string, horizontal: boolean): LayoutPlugin {
  return {
    id,
    compute: (graph) => {
      const parents = parentLinks(graph.nodes, graph.edges)
      const rootIris = graph.nodes.filter((node) => !parents.has(node.iri)).map((node) => node.iri)
      const hasAnyLink = parents.size > 0
      if (!hasAnyLink || !rootIris.length) {
        // 无父子结构或全为环：退化为网格（环检测见后端规则阶段）
        return gridLayout(graph.nodes)
      }
      const byIri = new Map(graph.nodes.map((node) => [node.iri, node]))
      const childrenOf = (iri: string) =>
        graph.nodes.filter((node) => parents.get(node.iri)?.parent === iri).map((node) => node.iri)
      const data = hierarchy('__root__', (iri: string) =>
        iri === '__root__' ? rootIris : childrenOf(iri),
      )
      d3tree<string>().nodeSize(horizontal ? [NODE_H + 46, 230] : [NODE_W + 85, 165])(data)
      const placed: PositionedNode[] = []
      data.each((item) => {
        const node = byIri.get(item.data)
        if (!node) return // 虚根不渲染
        const px = (horizontal ? item.y : item.x) ?? 0
        const py = (horizontal ? item.x : item.y) ?? 0
        const x = horizontal ? px + 90 : px + 140
        const y = horizontal ? py + 70 : py + 60
        placed.push({ ...node, x, y })
      })
      const maxBreadth = Math.max(...placed.map((node) => (horizontal ? node.y : node.x)), 0)
      const maxDepth = Math.max(...placed.map((node) => (horizontal ? node.x : node.y)), 0)
      void 0
      const width = horizontal ? Math.max(900, maxDepth + NODE_W + 130) : maxBreadth + NODE_W + 200
      const height = horizontal ? maxBreadth + NODE_H + 140 : maxDepth + NODE_H + 130
      return {
        width,
        height: Math.max(480, height),
        groups: [],
        nodes: placed,
        edgePaths: edgeOverrides(placed, parents),
      }
    },
  }
}

/** G-01 组织架构树：自引用边（child -> parent）折线树，支持子树筛选与汇报线切换。 */
const orgTree = treeLayoutFactory('org_tree', false)

/** G-02 缩进目录树：横向树（左根右叶），适合懒加载与键盘导航。 */
const indentTree = treeLayoutFactory('indent_tree', true)

/**
 * 分层：把节点按边的上下方向（up -> down）做最长路径分层，
 * 环上节点落到最后一层；层内按 IRI 稳定排序。无可用边返回 null。
 */
function assignLevels(
  graph: Pick<GraphView, 'nodes' | 'edges'>,
): { level: Map<string, number>; order: Map<string, number> } | null {
  const iris = new Set(graph.nodes.map((node) => node.iri))
  const incoming = new Map<string, string[]>()
  const outgoing = new Map<string, string[]>()
  let usable = 0
  for (const edge of graph.edges) {
    if (!iris.has(edge.subject) || !iris.has(edge.object_) || edge.subject === edge.object_)
      continue
    usable += 1
    outgoing.set(edge.subject, [...(outgoing.get(edge.subject) ?? []), edge.object_])
    incoming.set(edge.object_, [...(incoming.get(edge.object_) ?? []), edge.subject])
  }
  if (!usable) return null
  const level = new Map<string, number>()
  const queue: string[] = []
  for (const iri of iris) {
    if (!incoming.get(iri)?.length) {
      level.set(iri, 0)
      queue.push(iri)
    }
  }
  // 环安全：真实场景会有刻意保留的持股环（如 1002<->1007），
  // 层级上限 = 节点数，环上的节点停止增长，绝不允许无限松弛。
  const levelCap = iris.size
  while (queue.length) {
    const current = queue.shift()!
    const currentLevel = level.get(current) ?? 0
    if (currentLevel >= levelCap) continue
    for (const next of outgoing.get(current) ?? []) {
      if ((level.get(next) ?? -Infinity) < currentLevel + 1 && currentLevel + 1 <= levelCap) {
        level.set(next, currentLevel + 1)
        queue.push(next)
      }
    }
  }
  const maxAssigned = Math.max(-1, ...level.values())
  for (const iri of iris) {
    if (!level.has(iri)) level.set(iri, maxAssigned + 1)
  }
  const perLevel = new Map<number, string[]>()
  for (const node of graph.nodes) {
    const lv = level.get(node.iri) ?? 0
    perLevel.set(lv, [...(perLevel.get(lv) ?? []), node.iri])
  }
  const order = new Map<string, number>()
  for (const [, list] of [...perLevel.entries()].sort((a, b) => a[0] - b[0])) {
    list.sort((a, b) => a.localeCompare(b)).forEach((iri, index) => order.set(iri, index))
  }
  return { level, order }
}

function layeredResult(
  levels: { level: Map<string, number>; order: Map<string, number> },
  graph: Pick<GraphView, 'nodes' | 'edges'>,
): LayoutResult {
  const { level, order } = levels
  const perLevel = new Map<number, PositionedNode[]>()
  for (const node of graph.nodes) {
    const lv = level.get(node.iri) ?? 0
    const index = order.get(node.iri) ?? 0
    const placed: PositionedNode = {
      ...node,
      x: 140 + index * (NODE_W + 90),
      y: 80 + lv * 170,
    }
    perLevel.set(lv, [...(perLevel.get(lv) ?? []), placed])
  }
  const maxLevel = Math.max(0, ...perLevel.keys())
  const maxRow = Math.max(1, ...[...perLevel.values()].map((nodes) => nodes.length))
  return {
    width: Math.max(900, 240 + maxRow * (NODE_W + 90)),
    height: Math.max(480, 160 + maxLevel * 170),
    groups: [],
    nodes: [...perLevel.values()].flat(),
    edgePaths: {},
  }
}

/** G-06 股权穿透图：股东在上、被投企业在下分层；比例在边上显示（props）。 */
const equityTree: LayoutPlugin = {
  id: 'equity_tree',
  compute: (graph) => {
    const levels = assignLevels(graph)
    return levels ? layeredResult(levels, graph) : gridLayout(graph.nodes)
  },
}

/** G-07 实际控制人链：优先用派生乘积边（间接持股）分层成链。 */
const controlChain: LayoutPlugin = {
  id: 'control_chain',
  compute: (graph) => {
    const derived = graph.edges.filter((edge) => edge.kind === 'DERIVED' && edge.props)
    const levels = assignLevels(derived.length ? { nodes: graph.nodes, edges: derived } : graph)
    return levels ? layeredResult(levels, graph) : gridLayout(graph.nodes)
  },
}

/** G-17 客商供应链图：买卖两端分列，双角色节点居中，金额在边上（props）。 */
const supplyChain: LayoutPlugin = {
  id: 'supply_chain',
  compute: (graph) => {
    const iris = new Set(graph.nodes.map((node) => node.iri))
    const left = new Set<string>()
    const right = new Set<string>()
    for (const edge of graph.edges) {
      if (!iris.has(edge.subject) || !iris.has(edge.object_) || edge.subject === edge.object_)
        continue
      left.add(edge.subject)
      right.add(edge.object_)
    }
    for (const iri of left) right.delete(iri)
    const middle = graph.nodes.filter((node) => !left.has(node.iri) && !right.has(node.iri))
    const columns: Set<string>[] = [left, right]
    const placed: PositionedNode[] = []
    columns.forEach((column, columnIndex) => {
      graph.nodes
        .filter((node) => column.has(node.iri))
        .forEach((node, index) => {
          placed.push({ ...node, x: columnIndex === 0 ? 170 : 790, y: 70 + index * 120 })
        })
    })
    middle.forEach((node, index) => {
      placed.push({ ...node, x: 480, y: 70 + index * 120 })
    })
    const rows = Math.max(left.size, right.size, middle.length, 3)
    return {
      width: 990,
      height: Math.max(480, 140 + rows * 120),
      groups: [],
      nodes: placed,
      edgePaths: {},
    }
  },
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}/

function firstDateAttr(attrs: Record<string, unknown>): string | null {
  for (const value of Object.values(attrs)) {
    if (typeof value === 'string' && ISO_DATE.test(value)) return value.slice(0, 10)
  }
  return null
}

/** G-21 时间轴：按类型分泳道，横轴按首个日期属性（无日期的排尾部并标记）。 */
const timeline: LayoutPlugin = {
  id: 'timeline',
  compute: (graph) => {
    const dated = graph.nodes.map((node) => ({ node, date: firstDateAttr(node.attrs) }))
    const times = dated
      .filter((item) => item.date !== null)
      .map((item) => new Date(item.date!).getTime())
    const min = times.length ? Math.min(...times) : 0
    const max = times.length ? Math.max(...times) : 1
    const span = Math.max(1, max - min)
    const types = [...new Set(graph.nodes.map((node) => node.type_iri))]
    const laneOf = new Map(types.map((type, index) => [type, index] as const))
    const laneHeight = 130
    const placed = dated.map(({ node, date }) => {
      const lane = laneOf.get(node.type_iri) ?? 0
      const ratio = date ? (new Date(date).getTime() - min) / span : 1.04
      return { ...node, x: 90 + ratio * 1060, y: 60 + lane * laneHeight + 36 }
    })
    return {
      width: 1240,
      height: Math.max(480, 120 + types.length * laneHeight + 70),
      groups: [],
      nodes: placed,
      edgePaths: {},
    }
  },
}

/**
 * G-16 本体模式图：类型级视图——实体类型聚合为节点（标签带计数）、
 * 关系聚合为类型边（props.count 为实例边数），点击下钻由外层处理。
 */
const schema: LayoutPlugin = {
  id: 'schema',
  compute: (graph) => {
    const byType = new Map<string, GraphViewNode[]>()
    for (const node of graph.nodes) {
      byType.set(node.type_iri, [...(byType.get(node.type_iri) ?? []), node])
    }
    const typeOf = new Map(graph.nodes.map((node) => [node.iri, node.type_iri] as const))
    const seenTypePairs = new Set<string>()
    const typeEdges: GraphViewEdge[] = []
    for (const edge of graph.edges) {
      const subjectType = typeOf.get(edge.subject)
      const objectType = typeOf.get(edge.object_)
      if (!subjectType || !objectType) continue
      const key = `${subjectType}|${edge.predicate}|${objectType}`
      if (seenTypePairs.has(key)) continue
      seenTypePairs.add(key)
      typeEdges.push({ ...edge, subject: subjectType, object_: objectType })
    }
    const shortName = (iri: string) => iri.split(/[/#]/).filter(Boolean).at(-1) || iri
    const typeNodes: GraphViewNode[] = [...byType.entries()].map(([type, members]) => ({
      ...members[0]!,
      iri: type,
      type_iri: type,
      row_key: String(members.length),
      attrs: { name: shortName(type), __typeCount__: members.length },
      distance: 0,
    }))
    // 类型对计数进 props.count，供边标签显示
    for (const edge of typeEdges) {
      edge.props = {
        count: graph.edges.filter(
          (item) =>
            item.predicate === edge.predicate &&
            typeOf.get(item.subject) === edge.subject &&
            typeOf.get(item.object_) === edge.object_,
        ).length,
      }
    }
    return force.compute({ nodes: typeNodes, edges: typeEdges })
  },
}

export const LAYOUTS: LayoutPlugin[] = [
  typeGrid,
  ring,
  force,
  orgTree,
  indentTree,
  equityTree,
  controlChain,
  supplyChain,
  timeline,
  schema,
]

export const LAYOUT_IDS = LAYOUTS.map((layout) => layout.id)

export function resolveLayout(id: string | null | undefined, hasCenter: boolean): LayoutPlugin {
  const found = id ? LAYOUTS.find((layout) => layout.id === id) : undefined
  if (found) return found
  // 缺省：有中心实体用距离环（G-11），全图总览用类型网格
  return hasCenter ? ring : typeGrid
}
