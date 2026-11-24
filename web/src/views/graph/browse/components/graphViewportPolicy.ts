import { NODE_RADIUS, type Point } from '../../../../components/graph/viewport.ts'

export function showGraphLabel(scale: number, important: boolean, kind: 'node' | 'edge'): boolean {
  return important || scale >= (kind === 'node' ? 0.6 : 0.65)
}

/** Enlarged context nodes must share the available space, including their selection rings. */
export function nodeDisplayScales(
  nodes: (Point & { iri: string })[],
  important: ReadonlySet<string>,
  cameraScale: number,
): Map<string, number> {
  const desired = Math.max(1, 1 / cameraScale)
  const scales = new Map(nodes.map((node) => [node.iri, important.has(node.iri) ? desired : 1]))
  if (desired === 1 || !important.size) return scales
  const radius = NODE_RADIUS + 5
  const gap = 4
  for (let left = 0; left < nodes.length; left++) {
    const a = nodes[left]!
    for (let right = left + 1; right < nodes.length; right++) {
      const b = nodes[right]!
      const count = Number(important.has(a.iri)) + Number(important.has(b.iri))
      if (!count) continue
      const distance = Math.hypot(a.x - b.x, a.y - b.y)
      const limit = 1 + Math.max(0, distance - 2 * radius - gap) / (count * radius)
      if (important.has(a.iri)) scales.set(a.iri, Math.min(scales.get(a.iri)!, limit))
      if (important.has(b.iri)) scales.set(b.iri, Math.min(scales.get(b.iri)!, limit))
    }
  }
  return scales
}

/** Use code points and measured width units so CJK and emoji stay inside the circle. */
export function nodeNameLines(name: string): string[] {
  const chars = [...name.trim()]
  const lines: string[] = []
  let offset = 0
  for (let line = 0; line < 2 && offset < chars.length; line++) {
    let text = ''
    let width = 0
    while (offset < chars.length) {
      const char = chars[offset]!
      const units = char.codePointAt(0)! > 255 ? 2 : 1
      if (width + units > 10) break
      text += char
      width += units
      offset++
    }
    if (line === 1 && offset < chars.length) text = `${[...text].slice(0, -1).join('')}…`
    lines.push(text)
  }
  // Keep six-character names from ending with a single isolated glyph on the second line.
  if (lines.length === 2 && [...lines[1]!].length === 1) {
    const first = [...lines[0]!]
    lines[1] = first.pop()! + lines[1]
    lines[0] = first.join('')
  }
  return lines
}
