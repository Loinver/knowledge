export type DesignerPoint = { x: number; y: number }
export type DesignerLink = { id: number; source: number; target: number; labelWidth?: number }

/** Clip an endpoint to the card boundary, leaving the arrow outside its contents. */
function boundary(center: DesignerPoint, toward: DesignerPoint, width: number, height: number) {
  const dx = toward.x - center.x
  const dy = toward.y - center.y
  const ratio = Math.min(width / 2 / (Math.abs(dx) || 1e-9), height / 2 / (Math.abs(dy) || 1e-9))
  return { x: center.x + dx * ratio, y: center.y + dy * ratio }
}

/** Stable lanes retain every relation, including reverse edges and multiple self loops. */
export function designerEdges(
  links: DesignerLink[],
  positions: Record<string, DesignerPoint>,
  width: number,
  height: number,
) {
  const groups = new Map<string, DesignerLink[]>()
  for (const link of links) {
    if (!positions[link.source] || !positions[link.target]) continue
    const key = [link.source, link.target].sort((a, b) => a - b).join(':')
    const group = groups.get(key) ?? []
    group.push(link)
    groups.set(key, group)
  }
  return [...groups.values()]
    .flatMap((group) =>
      group
        .sort((a, b) => a.id - b.id)
        .map((link, index) => {
          const from = positions[link.source]!
          const to = positions[link.target]!
          const a = { x: from.x + width / 2, y: from.y + height / 2 }
          const b = { x: to.x + width / 2, y: to.y + height / 2 }
          if (link.source === link.target) {
            const rise = 68 + index * 42
            const left = a.x - width * 0.28
            const right = a.x + width * 0.28
            return {
              ...link,
              d: `M${left} ${from.y} C${left - 32} ${from.y - rise} ${right + 32} ${from.y - rise} ${right} ${from.y}`,
              lx: a.x,
              ly: from.y - rise * 0.75,
            }
          }
          const dx = b.x - a.x
          const dy = b.y - a.y
          const length = Math.hypot(dx, dy) || 1
          const direction = link.source < link.target ? 1 : -1
          const laneStep =
            Math.abs(dx) < Math.abs(dy)
              ? Math.max(76, ...group.map((item) => (item.labelWidth ?? 60) * 1.7))
              : 76
          const offset = (index - (group.length - 1) / 2) * laneStep * direction
          const control = {
            x: (a.x + b.x) / 2 - (dy / length) * offset,
            y: (a.y + b.y) / 2 + (dx / length) * offset,
          }
          const start = boundary(a, control, width, height)
          const end = boundary(b, control, width, height)
          return {
            ...link,
            d: `M${start.x} ${start.y} Q${control.x} ${control.y} ${end.x} ${end.y}`,
            lx: start.x / 4 + control.x / 2 + end.x / 4,
            ly: start.y / 4 + control.y / 2 + end.y / 4,
          }
        }),
    )
    .sort((a, b) => a.id - b.id)
}
