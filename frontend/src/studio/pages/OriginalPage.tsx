import { useEffect, useRef } from 'react'
import type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist'
import type { TextLayerBuilder } from 'pdfjs-dist/web/pdf_viewer.mjs'
import { viewer } from '../../lib/pdf'
import type { Annotation, Page } from '../../api'
import Highlights from './Highlights'
import { annotationAt, selectionMark, type Mark } from './marks'

const PX_PER_PT = 4 / 3

type Props = {
  pdf: PDFDocumentProxy; page: Page
  shift: boolean; picked: Set<string>; onPick: (id: string, x: number, y: number) => void
  selected: string[]  // the sections the prompt box edits
  onSelect: (id: string | null, add: boolean) => void  // a click on a section (null: on the page around them); add: Ctrl/⌘ held
  onHighlight: (text: string, rect: DOMRect, mark?: Mark, add?: boolean) => void
  annotations: Annotation[]; activeId: string | null; onOpenAnnotation: (id: string) => void
  placingText: boolean; onPlaceText: (page: number, x: number, y: number) => void
  onUpdateAnnotation: (a: Annotation) => void
  flashId: string | null  // a block to outline briefly (search result)
}

/** One page of the original, as pdf.js draws it (with its text layer, for exact selection), with
 *  highlights, notes and text boxes over it. */
export default function OriginalPage({ pdf, page, shift, picked, onPick, selected, onSelect, onHighlight, annotations, activeId, onOpenAnnotation, placingText, onPlaceText, onUpdateAnnotation, flashId }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const text = useRef<HTMLDivElement>(null)
  const w = page.width * PX_PER_PT, h = page.height * PX_PER_PT

  useEffect(() => {
    let cancelled = false
    let layer: TextLayerBuilder | null = null
    let drawing: ReturnType<PDFPageProxy['render']> | null = null
    pdf.getPage(page.index + 1).then(async (p) => {
      if (cancelled || !canvas.current || !text.current) return
      const viewport = p.getViewport({ scale: PX_PER_PT })
      const ratio = Math.min(window.devicePixelRatio || 1, 2) * 1.5  // extra pixels so zoom stays sharp
      canvas.current.width = Math.floor(viewport.width * ratio)
      canvas.current.height = Math.floor(viewport.height * ratio)
      drawing = p.render({ canvas: canvas.current, viewport, transform: [ratio, 0, 0, ratio, 0, 0] })
      await drawing.promise
      if (cancelled) return
      canvas.current.animate([{ opacity: 0.25 }, { opacity: 1 }], { duration: 180, easing: 'ease-out' })  // switching views cross-fades
      text.current.replaceChildren()  // drop any layer from an earlier, cancelled run
      text.current.style.setProperty('--total-scale-factor', String(PX_PER_PT))
      const host = text.current
      // The viewer's builder (not the bare TextLayer) keeps drag-selection from running down the page.
      const { TextLayerBuilder } = await viewer
      if (cancelled) return
      layer = new TextLayerBuilder({ pdfPage: p, onAppend: (div: HTMLDivElement) => host.append(div) })
      await layer.render({ viewport } as Parameters<TextLayerBuilder["render"]>[0])  // images is optional at runtime
    }).catch((e) => { if (e?.name !== 'RenderingCancelledException') console.warn('page render failed', e) })
    // React may run this twice in dev: cancel the first draw so it releases the canvas for the second.
    return () => { cancelled = true; drawing?.cancel(); layer?.cancel() }
  }, [pdf, page.index])

  /** Screen point → PDF points on this page (the page is CSS-scaled by the zoom). */
  const toPt = (clientX: number, clientY: number) => {
    const r = box.current!.getBoundingClientRect()
    return [((clientX - r.left) / r.width) * page.width, ((clientY - r.top) / r.height) * page.height]
  }

  /** The smallest block whose box contains the click (boxes are in PDF points). */
  const blockAt = (e: React.MouseEvent) => {
    const [x, y] = toPt(e.clientX, e.clientY)
    const hits = page.blocks.filter((b) => b.bbox[0] <= x && x <= b.bbox[2] && b.bbox[1] <= y && y <= b.bbox[3])
    hits.sort((a, b) => (a.bbox[2] - a.bbox[0]) * (a.bbox[3] - a.bbox[1]) - (b.bbox[2] - b.bbox[0]) * (b.bbox[3] - b.bbox[1]))
    return hits[0]?.id
  }

  return (
    <div ref={box} className={`relative ${placingText ? 'cursor-crosshair' : ''}`} style={{ width: w, height: h }}
      onMouseDown={(e) => { if (e.shiftKey) e.preventDefault() }}  // shift picks blocks, not text
      onMouseUp={(e) => {
        const sel = window.getSelection()
        const t = sel?.toString().trim()
        if (t && sel && sel.rangeCount) {
          const range = sel.getRangeAt(0)
          onHighlight(t, range.getBoundingClientRect(), selectionMark(box.current!, range, page, '', '.textLayer') ?? undefined, e.ctrlKey || e.metaKey)
        }
      }}
      onClick={(e) => {
        if (window.getSelection()?.toString().trim()) return  // finishing a highlight, not a click
        if (e.shiftKey) { const id = blockAt(e); if (id) onPick(id, e.clientX, e.clientY); return }
        const [x, y] = toPt(e.clientX, e.clientY)
        if (placingText) { onPlaceText(page.index, x, y); return }
        const hit = annotationAt(annotations, x, y)
        if (hit) { onOpenAnnotation(hit.id); return }
        onSelect(blockAt(e) ?? null, e.ctrlKey || e.metaKey)
      }}>
      <canvas ref={canvas} style={{ width: w, height: h }} className="absolute inset-0" />
      {page.blocks.filter((b) => picked.has(b.id) || b.id === flashId || selected.includes(b.id) || (shift && b.translatable)).map((b) => (  // picks stay until dismissed
        <div key={b.id} className={`absolute pointer-events-none rounded-sm z-[3] ${picked.has(b.id) || b.id === flashId || selected.includes(b.id) ? 'outline-2 outline-accent bg-accent/10' : 'outline-1 outline-dashed outline-accent/60'}`}
          style={{ left: b.bbox[0] * PX_PER_PT - 2, top: b.bbox[1] * PX_PER_PT - 2,
                   width: (b.bbox[2] - b.bbox[0]) * PX_PER_PT + 4, height: (b.bbox[3] - b.bbox[1]) * PX_PER_PT + 4 }} />
      ))}
      <div ref={text} className="absolute inset-0" />
      <Highlights annotations={annotations} activeId={activeId} onOpen={onOpenAnnotation} />
      {annotations.filter((a) => a.kind === 'text').map((a) => {
        const [x0, y0, x1, y1] = a.rects[0]
        return (
          // Resizable in place; the new size is saved when the mouse is released.
          <textarea key={a.id} defaultValue={a.comment} placeholder="Type here" autoFocus={a.id === activeId && !a.comment}
            onClick={(e) => e.stopPropagation()} onFocus={() => onOpenAnnotation(a.id)}
            onBlur={(e) => { if (e.target.value !== a.comment) onUpdateAnnotation({ ...a, comment: e.target.value }) }}
            onMouseUp={(e) => {
              const el = e.currentTarget
              const nw = el.offsetWidth / PX_PER_PT, nh = el.offsetHeight / PX_PER_PT
              if (Math.abs(nw - (x1 - x0)) > 1 || Math.abs(nh - (y1 - y0)) > 1)
                onUpdateAnnotation({ ...a, comment: el.value, rects: [[x0, y0, x0 + nw, y0 + nh]] })
            }}
            className={`absolute z-20 resize p-0.5 bg-transparent text-ink leading-tight outline-none rounded-sm
              border border-dashed ${a.id === activeId ? 'border-accent' : 'border-transparent hover:border-black/30'}`}
            style={{ left: x0 * PX_PER_PT, top: y0 * PX_PER_PT, width: (x1 - x0) * PX_PER_PT, height: (y1 - y0) * PX_PER_PT,
                     fontSize: a.font_size * PX_PER_PT, fontFamily: 'Helvetica, Arial, sans-serif' }} />
        )
      })}
    </div>
  )
}
