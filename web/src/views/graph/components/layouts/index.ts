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
import {
  hierarchy,
  pack as d3pack,
  partition as d3partition,
  tree as d3tree,
  treemap as d3treemap,
  treemapSquarify,
} from 'd3-hierarchy'

import type { GraphView } from '@/api/graph'

export type GraphViewNode = GraphView['nodes'][number]
export type GraphViewEdge = GraphView['edges'][number]
export type PositionedNode = GraphViewNode & { x: number; y: number }
export type EdgePathOverride = { path: string; label?: { x: number; y: number } }

export type LayoutMark = {
  id: string
  /** 实例 IRI：携带则点击可下钻；类型区块不可点。 */
  iri?: string
  kind: 'rect' | 'circle' | 'sector'
  /** 标签锚点（也是 rect/circle 的几何中心）。 */
  x: number
  y: number
  /** rect 尺寸（中心对称）。 */
  w?: number
  h?: number
  /** circle 半径。 */
  r?: number
  /** sector 的完整 SVG path（环形扇区）。 */
  path?: string
  /** 类型色。 */
  fill: string
  label?: string
  sublabel?: string
  labelY?: number
}

export type LayoutTitle = {
  id: string
  x: number
  y: number
  text: string
  anchor?: 'start' | 'middle' | 'end'
}

export type LayoutResult = {
  width: number
  height: number
  groups: { type: string; y: number; nodes: PositionedNode[] }[]
  nodes: PositionedNode[]
  /** 布局可覆写边路径（树形折线等）；缺省时用 graphPaths 的曲线。 */
  edgePaths?: Record<number, EdgePathOverride>
  /** 划分图标记（旭日/矩形树/打包）：存在时画布只渲染标记，不渲染节点-边。 */
  marks?: LayoutMark[]
  /** 纯文字标注（甘特时间轴刻度、小多图图块标题）：不参与交互，只做刻度与分组说明。 */
  titles?: LayoutTitle[]
  /** 布局可收窄参与绘制的边（小多图各图块只画块内边）；缺省时画布用原始边。 */
  edges?: GraphViewEdge[]
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

// ===== 第三批增强形态（P1/P2） =====

function layeredHorizontal(
  levels: { level: Map<string, number>; order: Map<string, number> },
  graph: Pick<GraphView, 'nodes' | 'edges'>,
): LayoutResult {
  const { level, order } = levels
  const perLevel = new Map<number, PositionedNode[]>()
  for (const node of graph.nodes) {
    const lv = level.get(node.iri) ?? 0
    const index = order.get(node.iri) ?? 0
    perLevel.set(lv, [
      ...(perLevel.get(lv) ?? []),
      { ...node, x: 120 + lv * 190, y: 80 + index * 120 },
    ])
  }
  const maxLevel = Math.max(0, ...perLevel.keys())
  const maxRow = Math.max(1, ...[...perLevel.values()].map((nodes) => nodes.length))
  return {
    width: Math.max(900, 260 + maxLevel * 190),
    height: Math.max(480, 160 + maxRow * 120),
    groups: [],
    nodes: [...perLevel.values()].flat(),
    edgePaths: {},
  }
}

/** G-08 集团族谱：横向控股树（层沿横轴、成员沿纵轴）。 */
const clanTree: LayoutPlugin = {
  id: 'clan_tree',
  compute: (graph) => {
    const levels = assignLevels(graph)
    return levels ? layeredHorizontal(levels, graph) : gridLayout(graph.nodes)
  },
}

/** G-13 二部图：按边的方向把节点分到左右两列（通用二部布局）。 */
const bipartite: LayoutPlugin = {
  id: 'bipartite',
  compute: (graph) => supplyChain.compute(graph),
}

/** 环检测（G-09）：DFS 找出环上实体，置于中心环，其余实体网格排布。 */
function findCycleNodes(nodes: GraphViewNode[], edges: GraphViewEdge[]): Set<string> {
  const iris = new Set(nodes.map((node) => node.iri))
  const adj = new Map<string, string[]>()
  for (const edge of edges) {
    if (!iris.has(edge.subject) || !iris.has(edge.object_)) continue
    adj.set(edge.subject, [...(adj.get(edge.subject) ?? []), edge.object_])
  }
  const color = new Map<string, number>()
  const onStack = new Set<string>()
  const inCycle = new Set<string>()
  const visit = (node: string) => {
    color.set(node, 1)
    onStack.add(node)
    for (const next of adj.get(node) ?? []) {
      if (onStack.has(next)) {
        inCycle.add(next)
        inCycle.add(node)
      } else if (!color.get(next)) {
        visit(next)
      }
    }
    onStack.delete(node)
    color.set(node, 2)
  }
  for (const node of iris) if (!color.get(node)) visit(node)
  return inCycle
}

/** G-09 环路检测视图：环上实体内环居中，环外实体外圈网格。 */
const cycleView: LayoutPlugin = {
  id: 'cycle_view',
  compute: (graph) => {
    const cycleNodes = findCycleNodes(graph.nodes, graph.edges)
    const onCycle = graph.nodes.filter((node) => cycleNodes.has(node.iri))
    const offCycle = graph.nodes.filter((node) => !cycleNodes.has(node.iri))
    const radius = 150
    const center = 480
    const ringNodes = onCycle.map((node, index) => {
      const angle = (2 * Math.PI * index) / onCycle.length - Math.PI / 2
      return { ...node, x: center + Math.cos(angle) * radius, y: 330 + Math.sin(angle) * radius }
    })
    const rest = gridLayout(offCycle)
    const shifted = rest.nodes.map((node) => ({ ...node, x: node.x + 900 }))
    return {
      width: Math.max(1400, 900 + rest.width),
      height: Math.max(660, rest.height),
      groups: rest.groups.map((group) => ({ ...group, nodes: [] })),
      nodes: [...ringNodes, ...shifted],
      edgePaths: {},
    }
  },
}

/** 连通分量（无向）：社区划分基础。 */
function components(nodes: GraphViewNode[], edges: GraphViewEdge[]): GraphViewNode[][] {
  const adj = new Map<string, string[]>()
  for (const edge of edges) {
    adj.set(edge.subject, [...(adj.get(edge.subject) ?? []), edge.object_])
    adj.set(edge.object_, [...(adj.get(edge.object_) ?? []), edge.subject])
  }
  const seen = new Set<string>()
  const out: GraphViewNode[][] = []
  for (const node of nodes) {
    if (seen.has(node.iri)) continue
    const members: GraphViewNode[] = []
    const queue = [node.iri]
    seen.add(node.iri)
    while (queue.length) {
      const current = queue.shift()!
      const self = nodes.find((item) => item.iri === current)
      if (self) members.push(self)
      for (const next of adj.get(current) ?? []) {
        if (!seen.has(next)) {
          seen.add(next)
          queue.push(next)
        }
      }
    }
    out.push(members)
  }
  return out.sort((a, b) => b.length - a.length)
}

/** G-14 社区聚类：连通分量分块排布，块间留白，最大块在前。 */
const community: LayoutPlugin = {
  id: 'community',
  compute: (graph) => {
    const groups = components(graph.nodes, graph.edges)
    const placed: PositionedNode[] = []
    let blockX = 60
    let blockY = 60
    let rowHeight = 0
    let index = 0
    for (const members of groups) {
      const cols = Math.min(4, members.length)
      const blockWidth = cols * 215
      if (blockX + blockWidth > 1560 && blockX > 60) {
        blockX = 60
        blockY += rowHeight + 150
        rowHeight = 0
      }
      members.forEach((node, i) => {
        placed.push({
          ...node,
          x: blockX + 115 + (i % cols) * 215,
          y: blockY + 55 + Math.floor(i / cols) * 110,
        })
      })
      rowHeight = Math.max(rowHeight, Math.ceil(members.length / cols) * 110)
      blockX += blockWidth + 120
      index += 1
    }
    void index
    return {
      width: 1620,
      height: Math.max(480, blockY + rowHeight + 140),
      groups: [],
      nodes: placed,
      edgePaths: {},
    }
  },
}

/** G-15 多方关系：高度数枢纽居中内环，邻居按枢纽分布外环。 */
const nary: LayoutPlugin = {
  id: 'nary',
  compute: (graph) => {
    const degree = new Map<string, number>()
    for (const edge of graph.edges) {
      degree.set(edge.subject, (degree.get(edge.subject) ?? 0) + 1)
      degree.set(edge.object_, (degree.get(edge.object_) ?? 0) + 1)
    }
    const sorted = [...graph.nodes].sort(
      (a, b) => (degree.get(b.iri) ?? 0) - (degree.get(a.iri) ?? 0),
    )
    const hubs = sorted.slice(0, Math.max(1, Math.ceil(graph.nodes.length / 6)))
    const hubSet = new Set(hubs.map((node) => node.iri))
    const spokes = sorted.filter((node) => !hubSet.has(node.iri))
    const hubPlaced = hubs.map((node, index) => {
      const angle = (2 * Math.PI * index) / hubs.length - Math.PI / 2
      return { ...node, x: 480 + Math.cos(angle) * 110, y: 330 + Math.sin(angle) * 110 }
    })
    const byHub = new Map<string, GraphViewNode[]>()
    for (const node of spokes) {
      const hub =
        graph.edges.find(
          (edge) =>
            (edge.subject === node.iri && hubSet.has(edge.object_)) ||
            (edge.object_ === node.iri && hubSet.has(edge.subject)),
        ) ?? null
      const key = hub ? (hubSet.has(hub.subject) ? hub.subject : hub.object_) : '_free'
      byHub.set(key, [...(byHub.get(key) ?? []), node])
    }
    const outer: PositionedNode[] = []
    for (const [hubIri, members] of byHub) {
      const hub = hubPlaced.find((node) => node.iri === hubIri)
      const anchorX = hub ? hub.x : 880
      const anchorY = hub ? hub.y : 120
      members.forEach((node, index) => {
        const angle = (2 * Math.PI * index) / members.length + Math.abs(anchorX) * 0.001
        outer.push({
          ...node,
          x: Math.max(90, Math.min(1500, anchorX + Math.cos(angle) * 300)),
          y: Math.max(50, Math.min(640, anchorY + Math.sin(angle) * 260)),
        })
      })
    }
    return { width: 1560, height: 680, groups: [], nodes: [...hubPlaced, ...outer], edgePaths: {} }
  },
}

/** 类型级聚合图（G-18/G-19 公共基础）。 */
function typeGraph(graph: Pick<GraphView, 'nodes' | 'edges'>): {
  nodes: GraphViewNode[]
  edges: GraphViewEdge[]
} {
  const byType = new Map<string, GraphViewNode[]>()
  for (const node of graph.nodes) {
    byType.set(node.type_iri, [...(byType.get(node.type_iri) ?? []), node])
  }
  const typeOf = new Map(graph.nodes.map((node) => [node.iri, node.type_iri] as const))
  const seen = new Set<string>()
  const edges: GraphViewEdge[] = []
  for (const edge of graph.edges) {
    const st = typeOf.get(edge.subject)
    const ot = typeOf.get(edge.object_)
    if (!st || !ot) continue
    const key = `${st}|${edge.predicate}|${ot}`
    if (seen.has(key)) continue
    seen.add(key)
    edges.push({ ...edge, subject: st, object_: ot })
  }
  for (const edge of edges) {
    edge.props = {
      count: graph.edges.filter(
        (item) =>
          item.predicate === edge.predicate &&
          typeOf.get(item.subject) === edge.subject &&
          typeOf.get(item.object_) === edge.object_,
      ).length,
    }
  }
  const nodes: GraphViewNode[] = [...byType.entries()].map(([type, members]) => ({
    ...members[0]!,
    iri: type,
    type_iri: type,
    row_key: String(members.length),
    attrs: {
      name: type.split(/[/#]/).filter(Boolean).at(-1) || type,
      __typeCount__: members.length,
    },
    distance: 0,
  }))
  return { nodes, edges }
}

/** G-18 桑基（类型级流向）：类型分层排布，边宽以 count 标注。 */
const sankey: LayoutPlugin = {
  id: 'sankey',
  compute: (graph) => {
    const aggregated = typeGraph(graph)
    const levels = assignLevels(aggregated)
    return levels ? layeredResult(levels, aggregated) : gridLayout(aggregated.nodes)
  },
}

/** G-19 弦图（类型级圆周）：类型节点圆周分布，边带实例计数。 */
const chord: LayoutPlugin = {
  id: 'chord',
  compute: (graph) => {
    const aggregated = typeGraph(graph)
    const size = 760
    return {
      width: size,
      height: size,
      groups: [],
      nodes: aggregated.nodes.map((node, index) => {
        const angle = (2 * Math.PI * index) / aggregated.nodes.length - Math.PI / 2
        return {
          ...node,
          x: size / 2 + Math.cos(angle) * (size / 2 - 130),
          y: size / 2 + Math.sin(angle) * (size / 2 - 130),
        }
      }),
      edgePaths: {},
    }
  },
}

const REGION_KEYS = ['region', 'province', 'city', 'address', 'location', '地区', '城市', '地址']

function regionOf(attrs: Record<string, unknown>): string | null {
  for (const key of REGION_KEYS) {
    const value = attrs[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return null
}

/** G-25 地理分布：按区域属性聚块（无地图瓦片，区域名标注在块首节点）；无区域属性退化网格。 */
const geo: LayoutPlugin = {
  id: 'geo',
  compute: (graph) => {
    const buckets = new Map<string, GraphViewNode[]>()
    let hasRegion = false
    for (const node of graph.nodes) {
      const region = regionOf(node.attrs)
      if (region === null) continue
      hasRegion = true
      buckets.set(region, [...(buckets.get(region) ?? []), node])
    }
    if (!hasRegion) return gridLayout(graph.nodes)
    const regionless = graph.nodes.filter((node) => regionOf(node.attrs) === null)
    const placed: PositionedNode[] = []
    let blockX = 60
    let blockY = 60
    let rowHeight = 0
    for (const [region, members] of [...buckets.entries()].sort(
      (a, b) => b[1].length - a[1].length,
    )) {
      const cols = Math.min(4, members.length)
      const blockWidth = cols * 215
      if (blockX + blockWidth > 1560 && blockX > 60) {
        blockX = 60
        blockY += rowHeight + 190
        rowHeight = 0
      }
      members.forEach((node, i) => {
        placed.push({
          ...node,
          x: blockX + 115 + (i % cols) * 215,
          y: blockY + 95 + Math.floor(i / cols) * 110,
        })
      })
      if (placed.length) {
        const first = placed[placed.length - members.length]!
        placed[placed.length - members.length] = {
          ...first,
          attrs: { ...first.attrs, __region__: region },
        }
      }
      rowHeight = Math.max(rowHeight, Math.ceil(members.length / cols) * 110 + 80)
      blockX += blockWidth + 120
    }
    // 无区域属性的节点排在收尾块，绝不静默丢弃
    if (regionless.length) {
      const cols = Math.min(4, regionless.length)
      regionless.forEach((node, i) => {
        placed.push({
          ...node,
          x: blockX + 115 + (i % cols) * 215,
          y: blockY + 95 + Math.floor(i / cols) * 110,
        })
      })
    }
    return {
      width: 1620,
      height: Math.max(480, blockY + rowHeight + 140),
      groups: [],
      nodes: placed,
      edgePaths: {},
    }
  },
}

/**
 * G-27 影响面：被依赖者在上的依赖树。
 * 与组织树相反，这里 subject 是"依赖方上方的被依赖方"——
 * 即边 (a -> b) 表示 a 依赖 b，b 应在 a 之上，受影响面自上而下展开。
 */
function impactParentLinks(
  nodes: GraphViewNode[],
  edges: GraphViewEdge[],
): Map<string, { parent: string; edgeId: number }> {
  const iris = new Set(nodes.map((node) => node.iri))
  const parents = new Map<string, { parent: string; edgeId: number }>()
  for (const edge of edges) {
    if (!iris.has(edge.subject) || !iris.has(edge.object_)) continue
    if (edge.subject === edge.object_) continue
    // 反向：object 是被依赖方（父），subject 是依赖方（子）
    if (!parents.has(edge.subject)) {
      parents.set(edge.subject, { parent: edge.object_, edgeId: edge.id })
    }
  }
  return parents
}

const impact: LayoutPlugin = {
  id: 'impact',
  compute: (graph) => {
    const parents = impactParentLinks(graph.nodes, graph.edges)
    const rootIris = graph.nodes.filter((node) => !parents.has(node.iri)).map((node) => node.iri)
    if (!parents.size || !rootIris.length) return gridLayout(graph.nodes)
    const byIri = new Map(graph.nodes.map((node) => [node.iri, node]))
    const childrenOf = (iri: string) =>
      graph.nodes.filter((node) => parents.get(node.iri)?.parent === iri).map((node) => node.iri)
    const data = hierarchy('__root__', (iri: string) =>
      iri === '__root__' ? rootIris : childrenOf(iri),
    )
    d3tree<string>().nodeSize([NODE_W + 85, 165])(data)
    const placed: PositionedNode[] = []
    data.each((item) => {
      const node = byIri.get(item.data)
      if (!node) return
      const px = item.x ?? 0
      const py = item.y ?? 0
      placed.push({ ...node, x: px + 140, y: py + 60 })
    })
    if (!placed.length) return gridLayout(graph.nodes)
    const maxBreadth = Math.max(...placed.map((node) => node.x), 0)
    const maxDepth = Math.max(...placed.map((node) => node.y), 0)
    const overrides: Record<number, EdgePathOverride> = {}
    for (const [child, link] of parents) {
      const source = placed.find((node) => node.iri === child)
      const target = placed.find((node) => node.iri === link.parent)
      if (source && target) overrides[link.edgeId] = elbow(target, source)
    }
    return {
      width: Math.max(900, maxBreadth + NODE_W + 200),
      height: Math.max(480, maxDepth + NODE_H + 130),
      groups: [],
      nodes: placed,
      edgePaths: overrides,
    }
  },
}

// ===== 划分图（G-03/04/05）：本体 → 类型 → 实例 的层级面积编码 =====

const MARK_PALETTE = [
  '#2563eb',
  '#059669',
  '#d97706',
  '#7c3aed',
  '#dc2626',
  '#0891b2',
  '#65a30d',
  '#ea580c',
  '#db2777',
  '#4f46e5',
]

/** 类型 → 调色板色的确定性映射（同一图谱内同名同色）。 */
export function typeColor(type: string, types: string[]): string {
  const index = types.indexOf(type)
  return MARK_PALETTE[(index < 0 ? 0 : index) % MARK_PALETTE.length]
}

type PartitionDatum = {
  name: string
  iri?: string
  typeIri?: string
  children?: PartitionDatum[]
}

function partitionRoot(graph: Pick<GraphView, 'nodes'>): PartitionDatum {
  const byType = new Map<string, GraphViewNode[]>()
  for (const node of graph.nodes) {
    byType.set(node.type_iri, [...(byType.get(node.type_iri) ?? []), node])
  }
  return {
    name: '__ontology__',
    children: [...byType.entries()].map(([type, members]) => ({
      name: type,
      typeIri: type,
      children: members.map((member) => ({
        name: String(member.attrs.name ?? member.row_key),
        iri: member.iri,
        typeIri: type,
      })),
    })),
  }
}

function clip(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

function shortType(iri: string): string {
  return iri.split(/[/#]/).filter(Boolean).at(-1) || iri
}

/** 环形扇区 path（角度从正上方顺时针）。 */
function sectorPath(
  cx: number,
  cy: number,
  inner: number,
  outer: number,
  a0: number,
  a1: number,
): string {
  const point = (radius: number, angle: number) =>
    `${(cx + radius * Math.sin(angle)).toFixed(2)},${(cy - radius * Math.cos(angle)).toFixed(2)}`
  const largeArc = a1 - a0 > Math.PI ? 1 : 0
  return [
    `M ${point(outer, a0)}`,
    `A ${outer} ${outer} 0 ${largeArc} 1 ${point(outer, a1)}`,
    `L ${point(inner, a1)}`,
    `A ${inner} ${inner} 0 ${largeArc} 0 ${point(inner, a0)}`,
    'Z',
  ].join(' ')
}

/** G-03 旭日图：内环类型、外环实例，实例角度按计数占比分配。 */
const sunburst: LayoutPlugin = {
  id: 'sunburst',
  compute: (graph) => {
    const W = 760
    const cx = W / 2
    const cy = W / 2
    const types = [...new Set(graph.nodes.map((node) => node.type_iri))]
    const root = d3partition<PartitionDatum>().size([2 * Math.PI, 1])(
      hierarchy<PartitionDatum>(partitionRoot(graph), (d) => d.children).count(),
    )
    const r0 = 120
    const r1 = 250
    const r2 = W / 2 - 16
    const marks: LayoutMark[] = []
    root.each((item) => {
      if (item.depth === 0) return
      const isType = item.depth === 1
      const typeIri = item.data.typeIri ?? ''
      const inner = isType ? r0 : r1
      const outer = isType ? r1 : r2
      const mid = (item.x0 + item.x1) / 2
      const labelRadius = (inner + outer) / 2
      marks.push({
        id: isType ? `type:${typeIri}` : `inst:${item.data.iri}`,
        iri: isType ? undefined : item.data.iri,
        kind: 'sector',
        path: sectorPath(cx, cy, inner, outer, item.x0, item.x1),
        x: cx + labelRadius * Math.sin(mid),
        y: cy - labelRadius * Math.cos(mid),
        fill: typeColor(typeIri, types),
        label:
          item.x1 - item.x0 > 0.16
            ? clip(isType ? shortType(typeIri) : item.data.name, 10)
            : undefined,
        sublabel: isType ? `${item.value ?? 0}` : undefined,
      })
    })
    return {
      width: W,
      height: W,
      groups: types.map((type) => ({ type, y: 0, nodes: [] })),
      nodes: [],
      marks,
    }
  },
}

/** G-04 矩形树图：类型分块、实例占面积（按实例计数），可下钻点击。 */
const treemapLayout: LayoutPlugin = {
  id: 'treemap',
  compute: (graph) => {
    const W = 1240
    const H = 760
    const types = [...new Set(graph.nodes.map((node) => node.type_iri))]
    const root = d3treemap<PartitionDatum>()
      .tile(treemapSquarify)
      .size([W, H])
      .paddingInner(3)
      .paddingTop(22)(hierarchy<PartitionDatum>(partitionRoot(graph), (d) => d.children).count())
    const marks: LayoutMark[] = []
    root.each((item) => {
      if (item.depth === 0) return
      const isType = item.depth === 1
      const w = item.x1 - item.x0
      const h = item.y1 - item.y0
      const typeIri = item.data.typeIri ?? ''
      marks.push({
        id: isType ? `type:${typeIri}` : `inst:${item.data.iri}`,
        iri: isType ? undefined : item.data.iri,
        kind: 'rect',
        x: (item.x0 + item.x1) / 2,
        y: (item.y0 + item.y1) / 2,
        w,
        h,
        fill: typeColor(typeIri, types),
        label:
          w > 76 && h > 28
            ? clip(isType ? shortType(typeIri) : item.data.name, isType ? 16 : 12)
            : undefined,
        sublabel: isType && h > 50 ? `${item.value ?? 0} 实例` : undefined,
        labelY: isType ? item.y0 + 14 : undefined,
      })
    })
    return {
      width: W,
      height: H,
      groups: types.map((type) => ({ type, y: 0, nodes: [] })),
      nodes: [],
      marks,
    }
  },
}

/** G-05 圆形打包图：类型大圆嵌套实例小圆（按实例计数定半径）。 */
const pack: LayoutPlugin = {
  id: 'pack',
  compute: (graph) => {
    const W = 760
    const types = [...new Set(graph.nodes.map((node) => node.type_iri))]
    const root = d3pack<PartitionDatum>().size([W, W]).padding(4)(
      hierarchy<PartitionDatum>(partitionRoot(graph), (d) => d.children).count(),
    )
    const marks: LayoutMark[] = []
    root.each((item) => {
      if (item.depth === 0) return
      const isType = item.depth === 1
      const typeIri = item.data.typeIri ?? ''
      marks.push({
        id: isType ? `type:${typeIri}` : `inst:${item.data.iri}`,
        iri: isType ? undefined : item.data.iri,
        kind: 'circle',
        x: item.x ?? 0,
        y: item.y ?? 0,
        r: item.r ?? 0,
        fill: typeColor(typeIri, types),
        label:
          (item.r ?? 0) > 26 ? clip(isType ? shortType(typeIri) : item.data.name, 12) : undefined,
        sublabel: isType && (item.r ?? 0) > 40 ? `${item.value ?? 0}` : undefined,
      })
    })
    return {
      width: W,
      height: W,
      groups: types.map((type) => ({ type, y: 0, nodes: [] })),
      nodes: [],
      marks,
    }
  },
}

// ===== 时间与组合（G-22 甘特、G-31 小多图）=====

/** 从 attrs 里取全部 ISO 日期，返回 [最早, 最晚]；只有一个日期即零长度区间。 */
function dateRange(attrs: Record<string, unknown>): [string, string] | null {
  const dates = Object.values(attrs)
    .filter((value): value is string => typeof value === 'string' && ISO_DATE.test(value))
    .map((value) => value.slice(0, 10))
    .sort()
  if (!dates.length) return null
  return [dates[0]!, dates[dates.length - 1]!]
}

/**
 * G-22 履历甘特图：按类型分泳道，每个有起止日期的实体画一根甘特条，
 * 横轴是统一时间轴（顶部给出年月刻度）。同一泳道内时间上重叠的区间
 * 用告警色高亮，便于发现"同一部门同时有两条在职记录"这类问题。
 */
const gantt: LayoutPlugin = {
  id: 'gantt',
  compute: (graph) => {
    const types = [...new Set(graph.nodes.map((node) => node.type_iri))]
    const rows = graph.nodes
      .map((node) => ({ node, range: dateRange(node.attrs) }))
      .filter(
        (item): item is { node: GraphViewNode; range: [string, string] } => item.range !== null,
      )
    if (!rows.length) {
      return { width: 1240, height: 480, groups: [], nodes: [], marks: [], titles: [] }
    }

    const times = rows.flatMap((item) => item.range.map((date) => new Date(date).getTime()))
    const min = Math.min(...times)
    const max = Math.max(...times)
    const span = Math.max(1, max - min)

    const GUTTER = 130
    const PLOT = 1010
    const ROW_H = 40
    const LANE_GAP = 30
    const plotX = (time: number) => GUTTER + ((time - min) / span) * PLOT

    const marks: LayoutMark[] = []
    const titles: LayoutTitle[] = []
    const groups: { type: string; y: number; nodes: PositionedNode[] }[] = []
    const placed: PositionedNode[] = []

    // 顶部时间刻度：最多 7 个等距年月，首尾必在轴端点内。
    const ticks = Math.min(7, Math.max(2, new Set(rows.map((r) => r.range[0].slice(0, 7))).size))
    for (let index = 0; index < ticks; index += 1) {
      const ratio = ticks === 1 ? 0 : index / (ticks - 1)
      const time = min + ratio * span
      titles.push({
        id: `tick-${index}`,
        x: plotX(time),
        y: 34,
        text: new Date(time).toISOString().slice(0, 7),
        anchor: 'middle',
      })
    }

    let y = 80
    for (const type of types) {
      const lane = rows.filter((item) => item.node.type_iri === type)
      if (!lane.length) continue
      groups.push({ type, y: y - 16, nodes: [] })
      for (const { node, range } of lane) {
        const start = new Date(range[0]).getTime()
        const end = new Date(range[1]).getTime()
        const x0 = plotX(start)
        const x1 = plotX(end)
        const width = Math.max(12, x1 - x0)
        const overlapped = lane.some(
          (other) =>
            other.node.iri !== node.iri &&
            new Date(other.range[0]).getTime() < end &&
            start < new Date(other.range[1]).getTime(),
        )
        marks.push({
          id: `bar:${node.iri}`,
          iri: node.iri,
          kind: 'rect',
          x: x0 + width / 2,
          y,
          w: width,
          h: 20,
          fill: overlapped ? '#dc2626' : typeColor(type, types),
          label: clip(String(node.attrs.name ?? node.row_key), 16),
          sublabel: `${range[0]} → ${range[1]}`,
        })
        placed.push({ ...node, x: x0 + width / 2, y })
        y += ROW_H
      }
      y += LANE_GAP
    }

    return {
      width: GUTTER + PLOT + 70,
      height: Math.max(480, y + 40),
      groups,
      nodes: placed,
      marks,
      titles,
    }
  },
}

/**
 * G-31 小多图对比：取实例最多的那一类实体，按度数取前若干个作为小图中心，
 * 每个中心画一张 1 跳邻域小图，网格并排、**统一半径**（同一比例尺），
 * 便于横向比较不同企业的关系规模；图块标题标注中心实体与邻居数。
 */
const smallMultiples: LayoutPlugin = {
  id: 'small_multiples',
  compute: (graph) => {
    const degree = new Map<string, number>()
    const neighbours = new Map<string, string[]>()
    for (const edge of graph.edges) {
      degree.set(edge.subject, (degree.get(edge.subject) ?? 0) + 1)
      degree.set(edge.object_, (degree.get(edge.object_) ?? 0) + 1)
      const forward = neighbours.get(edge.subject) ?? []
      forward.push(edge.object_)
      neighbours.set(edge.subject, forward)
      const backward = neighbours.get(edge.object_) ?? []
      backward.push(edge.subject)
      neighbours.set(edge.object_, backward)
    }
    const byIri = new Map(graph.nodes.map((node) => [node.iri, node] as const))
    const byType = new Map<string, GraphViewNode[]>()
    for (const node of graph.nodes) {
      byType.set(node.type_iri, [...(byType.get(node.type_iri) ?? []), node])
    }
    const target = [...byType.entries()].sort(
      (a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]),
    )[0]
    if (!target) {
      return { width: 940, height: 480, groups: [], nodes: [], titles: [] }
    }
    const centres = [...target[1]]
      .sort(
        (a, b) => (degree.get(b.iri) ?? 0) - (degree.get(a.iri) ?? 0) || a.iri.localeCompare(b.iri),
      )
      .slice(0, 6)

    const TILE_W = 470
    const TILE_H = 400
    // 统一比例尺：所有小图用同一邻居半径，图块大小也一致。
    const RADIUS = 125
    const MAX_NEIGHBOURS = 6
    const columns = Math.min(3, centres.length)
    const rowsCount = Math.ceil(centres.length / columns)

    const titles: LayoutTitle[] = []
    const placed: PositionedNode[] = []
    const used = new Set<string>()
    const tileSets: Set<string>[] = []

    centres.forEach((centre, index) => {
      if (used.has(centre.iri)) return
      const cx = (index % columns) * TILE_W + TILE_W / 2
      const cy = Math.floor(index / columns) * TILE_H + TILE_H / 2
      const ring = [...new Set(neighbours.get(centre.iri) ?? [])]
        .filter((iri) => !used.has(iri) && byIri.has(iri))
        .sort((a, b) => (degree.get(b) ?? 0) - (degree.get(a) ?? 0) || a.localeCompare(b))
        .slice(0, MAX_NEIGHBOURS)
      const members = [centre, ...ring.map((iri) => byIri.get(iri)!)]
      const tile = new Set(members.map((node) => node.iri))
      tileSets.push(tile)
      members.forEach((node) => used.add(node.iri))

      placed.push({ ...centre, x: cx, y: cy })
      ring.forEach((iri, ringIndex) => {
        const node = byIri.get(iri)!
        const angle = (2 * Math.PI * ringIndex) / ring.length - Math.PI / 2
        placed.push({
          ...node,
          x: cx + Math.cos(angle) * RADIUS,
          y: cy + Math.sin(angle) * RADIUS,
        })
      })
      titles.push({
        id: `tile:${centre.iri}`,
        x: cx,
        y: cy - TILE_H / 2 + 30,
        text: `${String(centre.attrs.name ?? centre.row_key)} · ${ring.length}`,
        anchor: 'middle',
      })
    })

    // 只保留落在同一个图块内的边：跨图块的边会把两张小图连起来，破坏"并排对比"。
    const edges = graph.edges.filter((edge) =>
      tileSets.some((tile) => tile.has(edge.subject) && tile.has(edge.object_)),
    )

    return {
      width: columns * TILE_W,
      height: Math.max(480, rowsCount * TILE_H),
      groups: [],
      nodes: placed,
      titles,
      edges,
    }
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
  clanTree,
  cycleView,
  bipartite,
  community,
  nary,
  sankey,
  chord,
  geo,
  impact,
  sunburst,
  treemapLayout,
  pack,
  gantt,
  smallMultiples,
]

export const LAYOUT_IDS = LAYOUTS.map((layout) => layout.id)

export function resolveLayout(id: string | null | undefined, hasCenter: boolean): LayoutPlugin {
  const found = id ? LAYOUTS.find((layout) => layout.id === id) : undefined
  if (found) return found
  // 缺省：有中心实体用距离环（G-11），全图总览用类型网格
  return hasCenter ? ring : typeGrid
}
