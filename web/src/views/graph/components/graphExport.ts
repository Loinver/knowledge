/**
 * 图谱画布导出（第二批 4.9 通用验收）：SVG / PNG / CSV。
 * 纯浏览器端实现；PNG 经 canvas 栅格化，失败时抛出由调用方提示。
 */

export function serializeSvg(svg: SVGSVGElement): string {
  const clone = svg.cloneNode(true) as SVGSVGElement
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  return new XMLSerializer().serializeToString(clone)
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export async function exportSvg(svg: SVGSVGElement, filename: string): Promise<void> {
  const text = serializeSvg(svg)
  downloadBlob(new Blob([text], { type: 'image/svg+xml;charset=utf-8' }), filename)
}

export async function exportPng(svg: SVGSVGElement, filename: string, scale = 2): Promise<void> {
  const text = serializeSvg(svg)
  const width = Number(svg.getAttribute('width')) || svg.clientWidth || 900
  const height = Number(svg.getAttribute('height')) || svg.clientHeight || 600
  const blob = await new Promise<Blob | null>((resolve) => {
    const image = new Image()
    image.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = width * scale
      canvas.height = height * scale
      const context = canvas.getContext('2d')
      if (!context) {
        resolve(null)
        return
      }
      context.scale(scale, scale)
      context.drawImage(image, 0, 0, width, height)
      canvas.toBlob(resolve, 'image/png')
    }
    image.onerror = () => resolve(null)
    image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(text)}`
  })
  if (!blob) throw new Error('png_export_failed')
  downloadBlob(blob, filename)
}

function csvEscape(value: string): string {
  return `"${value.replaceAll('"', '""')}"`
}

export function exportCsv(
  rows: Record<string, unknown>[],
  columns: string[],
  filename: string,
): void {
  const body = [
    columns.map(csvEscape).join(','),
    ...rows.map((row) => columns.map((column) => csvEscape(String(row[column] ?? ''))).join(',')),
  ].join('\n')
  downloadBlob(new Blob([`\uFEFF${body}`], { type: 'text/csv;charset=utf-8' }), filename)
}
