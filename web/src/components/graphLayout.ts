import type { GraphView } from '../api/graph'

export function layoutGraph(nodes: GraphView['nodes'], neighborhood: boolean) {
  if (!neighborhood) {
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

export function graphPaths(nodes: ReturnType<typeof layoutGraph>['nodes'], edges: GraphView['edges']) {
  const byIri = new Map(nodes.map((node) => [node.iri, node]))
  const pairs = new Map<string, GraphView['edges']>()
  for (const edge of edges) {
    const key = JSON.stringify([edge.subject, edge.object_].sort())
    const group = pairs.get(key) ?? []
    group.push(edge)
    pairs.set(key, group)
  }
  return [...pairs.values()].flatMap((edges) =>
    edges.map((edge, index) => {
      const source = byIri.get(edge.subject)!
      const target = byIri.get(edge.object_)!
      let path: string
      if (source.iri === target.iri) {
        const bend = 90 + index * 35
        path = `M ${source.x - 40} ${source.y - 26} C ${source.x - bend} ${source.y - bend}, ${source.x + bend} ${source.y - bend}, ${source.x + 40} ${source.y - 26}`
      } else {
        const [first, last] = source.iri < target.iri ? [source, target] : [target, source]
        const dx = last.x - first.x
        const dy = last.y - first.y
        const length = Math.hypot(dx, dy)
        const offset = (index - (edges.length - 1) / 2) * 42
        const cx = (first.x + last.x) / 2 - (dy / length) * offset
        const cy = (first.y + last.y) / 2 + (dx / length) * offset
        const boundary = (node: typeof source) => {
          const vx = cx - node.x
          const vy = cy - node.y
          const scale = Math.min(80 / Math.abs(vx), 26 / Math.abs(vy))
          return `${node.x + vx * scale} ${node.y + vy * scale}`
        }
        path = `M ${boundary(source)} Q ${cx} ${cy} ${boundary(target)}`
      }
      return { ...edge, path, key: `${edge.kind}-${edge.id}` }
    }),
  )
}
