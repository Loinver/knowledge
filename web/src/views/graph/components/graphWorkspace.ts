import type { GraphView } from '@/api/graph'

export const edgeKey = (edge: GraphView['edges'][number]) => `${edge.kind}:${edge.id}`
export const entityName = (node: Pick<GraphView['nodes'][number], 'attrs' | 'row_key'>) =>
  String(node.attrs.name ?? node.attrs.title ?? node.attrs.label ?? node.row_key)

/** Keep branch ownership outside the merged result so shared nodes survive a collapse. */
export function mergeNeighborhoods(base: GraphView, branches: Iterable<GraphView>): GraphView {
  const nodes = new Map(base.nodes.map((node) => [node.iri, node]))
  const edges = new Map(base.edges.map((edge) => [edgeKey(edge), edge]))
  let truncated = base.truncated
  for (const branch of branches) {
    if (branch.graph_revision_id !== base.graph_revision_id) continue
    truncated ||= branch.truncated
    for (const node of branch.nodes) {
      if (nodes.has(node.iri) || nodes.size < 500) nodes.set(node.iri, node)
      else truncated = true
    }
    for (const edge of branch.edges) {
      if (!nodes.has(edge.subject) || !nodes.has(edge.object_)) continue
      if (edges.has(edgeKey(edge)) || edges.size < 2000) edges.set(edgeKey(edge), edge)
      else truncated = true
    }
  }
  return { ...base, nodes: [...nodes.values()], edges: [...edges.values()], truncated }
}
