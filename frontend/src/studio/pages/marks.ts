/** Where a text selection sits on a page, for turning it into a highlight: line boxes in PDF points, and the view
 *  it was made on ("" the original, else a language). */
export type Mark = { page: number; rects: number[][]; lang: string }

/** The selection's line boxes in PDF points, merged per line; null if it leaves `box` (one page, `width` × `height`
 *  points on screen at any zoom). Only text nodes inside an element matching `within` count. */
export function selectionMark(box: HTMLElement, range: Range, page: { index: number; width: number; height: number },
  lang: string, within: string): Mark | null {
  if (!box.contains(range.startContainer) || !box.contains(range.endContainer)) return null
  const r0 = box.getBoundingClientRect()
  const toPt = (x: number, y: number) => [((x - r0.left) / r0.width) * page.width, ((y - r0.top) / r0.height) * page.height]
  // Boxes of the selected text only, text node by text node (an element's own client rects would
  // include whole boxes and paint far beyond the selection).
  const boxes: DOMRect[] = []
  const walker = document.createTreeWalker(box, NodeFilter.SHOW_TEXT)
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!node.textContent?.trim() || !range.intersectsNode(node) || !node.parentElement?.closest(within)) continue
    const part = document.createRange()
    part.selectNodeContents(node)
    if (node === range.startContainer) part.setStart(node, range.startOffset)
    if (node === range.endContainer) part.setEnd(node, range.endOffset)
    boxes.push(...part.getClientRects())
  }
  const lines: number[][] = []
  for (const r of boxes) {
    if (r.width < 1 || r.height < 1) continue
    const [x0, y0] = toPt(r.left, r.top), [x1, y1] = toPt(r.right, r.bottom)
    const same = lines.find((l) => Math.abs(l[1] - y0) < 2 && Math.abs(l[3] - y1) < 2)
    if (same) { same[0] = Math.min(same[0], x0); same[2] = Math.max(same[2], x1) }
    else lines.push([x0, y0, x1, y1])
  }
  if (!lines.length) return null
  lines.sort((a, b) => a[1] - b[1])
  return { page: page.index, rects: lines.map((l) => l.map((v) => Math.round(v * 100) / 100)), lang }
}

/** The annotation whose box holds a point (PDF points), if any. */
export const annotationAt = <A extends { rects: number[][] }>(annotations: A[], x: number, y: number) =>
  annotations.find((a) => a.rects.some((r) => r[0] <= x && x <= r[2] && r[1] <= y && y <= r[3]))
