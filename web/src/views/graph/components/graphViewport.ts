import type { GraphView } from '@/api/graph'

export type Point = { x: number; y: number }
export type Camera = Point & { scale: number }
export type ViewportSize = { width: number; height: number }
export type Bounds = Point & ViewportSize
export type Positions = Record<string, Point>
export const NODE_RADIUS = 42
export const MIN_SCALE = 0.12
export const MAX_SCALE = 3

export function worldPoint(point: Point, camera: Camera): Point {
  return { x: (point.x - camera.x) / camera.scale, y: (point.y - camera.y) / camera.scale }
}

export function screenPoint(point: Point, camera: Camera): Point {
  return { x: point.x * camera.scale + camera.x, y: point.y * camera.scale + camera.y }
}

export function zoomAt(camera: Camera, anchor: Point, nextScale: number): Camera {
  const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, nextScale))
  const point = worldPoint(anchor, camera)
  return { x: anchor.x - point.x * scale, y: anchor.y - point.y * scale, scale }
}

export function wheelCamera(
  camera: Camera,
  wheel: { deltaX: number; deltaY: number; deltaMode: number; ctrlKey: boolean; metaKey: boolean },
  anchor: Point,
  viewport: ViewportSize,
): Camera {
  const xUnit = wheel.deltaMode === 1 ? 16 : wheel.deltaMode === 2 ? viewport.width : 1
  const yUnit = wheel.deltaMode === 1 ? 16 : wheel.deltaMode === 2 ? viewport.height : 1
  if (wheel.ctrlKey || wheel.metaKey) {
    return zoomAt(camera, anchor, camera.scale * Math.exp(-wheel.deltaY * yUnit * 0.002))
  }
  return { ...camera, x: camera.x - wheel.deltaX * xUnit, y: camera.y - wheel.deltaY * yUnit }
}

export function centerCamera(camera: Camera, point: Point, viewport: ViewportSize): Camera {
  return {
    ...camera,
    x: viewport.width / 2 - point.x * camera.scale,
    y: viewport.height / 2 - point.y * camera.scale,
  }
}

/** Panel resize preserves the world point at the viewport center and the current zoom. */
export function resizeCamera(camera: Camera, previous: ViewportSize, next: ViewportSize): Camera {
  return {
    ...camera,
    x: camera.x + (next.width - previous.width) / 2,
    y: camera.y + (next.height - previous.height) / 2,
  }
}

export function fitCamera(bounds: Bounds, viewport: ViewportSize, padding = 64): Camera {
  const scale = Math.max(
    MIN_SCALE,
    Math.min(
      1,
      Math.max(1, viewport.width - padding * 2) / Math.max(1, bounds.width),
      Math.max(1, viewport.height - padding * 2) / Math.max(1, bounds.height),
    ),
  )
  return centerCamera(
    { x: 0, y: 0, scale },
    { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 },
    viewport,
  )
}

export function viewportBounds(camera: Camera, viewport: ViewportSize): Bounds {
  return {
    ...worldPoint({ x: 0, y: 0 }, camera),
    width: viewport.width / camera.scale,
    height: viewport.height / camera.scale,
  }
}

export function pointBounds(points: Point[], padding = NODE_RADIUS): Bounds {
  if (!points.length) return { x: 0, y: 0, width: 1, height: 1 }
  const x = Math.min(...points.map((point) => point.x)) - padding
  const y = Math.min(...points.map((point) => point.y)) - padding
  return {
    x,
    y,
    width: Math.max(...points.map((point) => point.x)) + padding - x,
    height: Math.max(...points.map((point) => point.y)) + padding - y,
  }
}

/** Only new nodes are placed. Hidden positions remain available when a filter is cleared. */
export function mergePositions(
  previous: Positions,
  nodes: (Point & { iri: string })[],
  edges: Pick<GraphView['edges'][number], 'subject' | 'object_'>[],
): Positions {
  const positions = { ...previous }
  const base = new Map(nodes.map((node) => [node.iri, node]))
  const occupied = nodes.flatMap((node) => (previous[node.iri] ? [previous[node.iri]!] : []))
  const incremental = Object.keys(previous).length > 0
  for (const node of nodes) {
    if (positions[node.iri]) continue
    let point = { x: node.x, y: node.y }
    if (incremental) {
      const neighbour = edges
        .flatMap((edge) =>
          edge.subject === node.iri
            ? [edge.object_]
            : edge.object_ === node.iri
              ? [edge.subject]
              : [],
        )
        .find((iri) => previous[iri] && base.has(iri))
      if (neighbour) {
        point = {
          x: point.x + previous[neighbour]!.x - base.get(neighbour)!.x,
          y: point.y + previous[neighbour]!.y - base.get(neighbour)!.y,
        }
      }
    }
    const anchor = point
    let attempt = 0
    while (occupied.some((other) => Math.hypot(point.x - other.x, point.y - other.y) < 96)) {
      attempt++
      const radius = 100 * Math.ceil(attempt / 8)
      const angle = (attempt % 8) * (Math.PI / 4)
      point = { x: anchor.x + Math.cos(angle) * radius, y: anchor.y + Math.sin(angle) * radius }
    }
    positions[node.iri] = point
    occupied.push(point)
  }
  return positions
}

export function dragPosition(origin: Point, start: Point, current: Point, scale: number): Point {
  return {
    x: origin.x + (current.x - start.x) / scale,
    y: origin.y + (current.y - start.y) / scale,
  }
}

export function isDrag(start: Point, current: Point): boolean {
  return Math.hypot(current.x - start.x, current.y - start.y) > 4
}

export function showGraphLabel(scale: number, important: boolean, kind: 'node' | 'edge'): boolean {
  return important || scale >= (kind === 'node' ? 0.6 : 0.65)
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
