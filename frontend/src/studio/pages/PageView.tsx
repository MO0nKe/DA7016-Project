import { useEffect, useRef, useState } from 'react'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import { api, type Annotation, type BlockChange, type Page } from '../../api'
import Highlights from './Highlights'
import OriginalPage from './OriginalPage'
import { annotationAt, selectionMark, type Mark } from './marks'

const PX_PER_PT = 4 / 3

/** Swap in the renderer's current render.css and fit.js when a page was drawn by a newer renderer than this tab
 *  loaded (the backend restarted while the studio stayed open): stale styles draw the new HTML wrongly. */
function freshen(version: string | undefined): Promise<void> {
  const link = document.querySelector<HTMLLinkElement>('link[href^="/api/static/render.css"]')
  if (!version || !link || link.getAttribute('href')!.endsWith(`?v=${version}`)) return Promise.resolve()
  link.setAttribute('href', `/api/static/render.css?v=${version}`)  // index.html's own (no version) counts as stale once
  return new Promise((done) => {
    const script = Object.assign(document.createElement('script'), { src: `/api/static/fit.js?v=${version}`, onload: done, onerror: done })
    document.head.append(script)
  })
}

/** The translated sections fit.js had to cut off (data-overflow: too long even at its smallest size), each given a
 *  tooltip saying where the rest is. */
function clipped(root: Element): string[] {
  const ids = new Set<string>()
  root.querySelectorAll<HTMLElement>('[data-overflow]').forEach((el) => {
    const block = el.closest<HTMLElement>('[data-status="translated"]')
    if (!block) return
    block.title = 'Cut off: too long to fit here. The full text is in the Translations panel.'
    ids.add(block.dataset.blockId!)
  })
  return [...ids]
}

/** The smallest section under the middle of a selection's line (PDF points). */
function blockUnder(page: Page, [x0, y0, x1, y1]: number[]) {
  const x = (x0 + x1) / 2, y = (y0 + y1) / 2
  const area = (b: number[]) => (b[2] - b[0]) * (b[3] - b[1])
  return page.blocks.filter((b) => b.translatable && b.bbox[0] <= x && x <= b.bbox[2] && b.bbox[1] <= y && y <= b.bbox[3])
    .sort((a, b) => area(a.bbox) - area(b.bbox))[0]?.id
}

/** A section's edited translation, in the language it was edited in. */
export type ShownChange = BlockChange & { lang: string }

type Props = {
  docId: string; page: Page; zoom: number
  view: 'original' | 'translated'; lang: string  // the language the Translation view shows
  version: number  // bumped when the document's translations change (a job ended)
  selected: string[]  // the sections the prompt box edits
  working: string[]  // the sections an edit is under way for
  onSelect: (id: string | null, add: boolean) => void  // a click on a section (null: on the page around them); add: Ctrl/⌘ held
  change: ShownChange | null
  picked: Set<string>; onPick: (id: string, x: number, y: number) => void; pdf: PDFDocumentProxy | null; shift: boolean
  onHighlight: (text: string, rect: DOMRect, mark: Mark | undefined, blockIds: string[], add: boolean) => void  // blockIds: the sections it covers
  annotations: Annotation[]; activeAnnotation: string | null; onOpenAnnotation: (id: string) => void
  flashId: string | null; placingText: boolean; onPlaceText: (page: number, x: number, y: number) => void; onUpdateAnnotation: (a: Annotation) => void
  onOcr: (index: number) => void; ocrBusy: boolean
  onClipped: (page: number, ids: string[]) => void  // the page's translated sections cut off to fit, after each fit
}

/** One page, scaled by `zoom`: the original, or the page drawn again with each section in its translation. */
export default function PageView({ docId, page, zoom, view, lang, version, selected, working, onSelect, change, picked, onPick, onHighlight, onOcr, ocrBusy, pdf, shift, annotations, activeAnnotation, onOpenAnnotation, placingText, onPlaceText, onUpdateAnnotation, flashId, onClipped }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const frame = useRef<HTMLDivElement>(null)  // the language view's page, highlights included
  const [error, setError] = useState<string | null>(null)
  const w = page.width * PX_PER_PT, h = page.height * PX_PER_PT
  const translated = view === 'translated' && page.source !== 'pending_ocr'
  // Each view keeps its own notes: the original's, or this language's.
  const mine = annotations.filter((a) => a.page === page.index && a.lang === (translated ? lang : ''))

  // Selection and pick outlines are toggled on the DOM, so a swapped-in section needs no page redraw.
  const outline = () => host.current?.querySelectorAll('[data-block-id]').forEach((el) => {
    const id = (el as HTMLElement).dataset.blockId!
    el.classList.toggle('ds-selected', selected.includes(id))
    el.classList.toggle('ds-picked', picked.has(id))
    el.classList.toggle('ds-working', working.includes(id))
  })
  useEffect(() => { outline() })

  useEffect(() => {
    if (!translated) return
    let live = true
    api.renderPage(docId, page.index, lang).then((html) => {
      if (!live || !host.current) return
      host.current.innerHTML = html
      outline()  // the page arrived after the last render: selected sections stay outlined across views
      const version = host.current.querySelector<HTMLElement>('.ds-page')?.dataset.static
      Promise.all([document.fonts.ready, freshen(version)]).then(() => {
        if (!host.current) return
        window.dsFit?.(host.current)
        onClipped(page.index, clipped(host.current))
      })
      host.current.animate([{ opacity: 0.25 }, { opacity: 1 }], { duration: 180, easing: 'ease-out' })  // switching views cross-fades
      setError(null)
    }).catch((e) => setError(e.message))
    return () => { live = false }
    // `outline` reads the selection when the page arrives; it isn't a reason to fetch the page again.
  }, [docId, page.index, translated, lang, version])  // eslint-disable-line react-hooks/exhaustive-deps

  // An edited section is swapped in place, without drawing the page again.
  useEffect(() => {
    if (!translated || !change || change.page !== page.index || change.lang !== lang) return
    const old = host.current?.querySelector(`[data-block-id="${change.block.id}"]`)
    if (!old) return
    const tmp = document.createElement('div')
    tmp.innerHTML = change.html
    const next = tmp.firstElementChild
    if (!next) return
    old.replaceWith(next)
    document.fonts.ready.then(() => {
      window.dsFit?.(next)
      if (host.current) onClipped(page.index, clipped(host.current))
    })
    // Only when a change arrives: the view and language it applies to are read then.
  }, [change])  // eslint-disable-line react-hooks/exhaustive-deps


  return (
    <section id={`page-${page.index}`} className="flex gap-6 w-fit mx-auto">
      <figure className="space-y-1.5">
        {(error || page.source === 'pending_ocr') && <figcaption className="flex items-center gap-2 text-xs text-muted px-1">
          {error && <span className="text-rose-700">{error}</span>}
          {page.source === 'pending_ocr' && (
            <>
              <span>Scanned page</span>
              <button disabled={ocrBusy} onClick={() => onOcr(page.index)} className="btn btn-sm btn-primary ml-auto">
                {ocrBusy ? 'Running OCR…' : 'Run OCR'}
              </button>
            </>
          )}
        </figcaption>}
        <div style={{ width: w * zoom, height: h * zoom }} className="shadow-page bg-white overflow-hidden rounded-[3px]">
          <div style={{ width: w, height: h, transform: `scale(${zoom})`, transformOrigin: 'top left' }}>
            {translated
              ? <div ref={frame} className="relative" style={{ width: w, height: h }}>
                  <div ref={host} className={`studio-page ${shift ? 'shift-held' : ''}`}
                    onMouseDown={(e) => { if (e.shiftKey) e.preventDefault() }}  // shift picks sections, not text
                    onMouseUp={(e) => {
                      const sel = window.getSelection()
                      const text = sel?.toString().trim()
                      if (!text || !sel || !sel.rangeCount || !host.current) return
                      const range = sel.getRangeAt(0)
                      const ids = [...host.current.querySelectorAll<HTMLElement>('[data-block-id]')]
                        .filter((el) => range.intersectsNode(el)).map((el) => el.dataset.blockId!)
                      // shortcut: the boxes are where the text is drawn now; a later edit of the section can move its text out from under them.
                      const mark = selectionMark(frame.current!, range, page, lang, '[data-block-id]') ?? undefined
                      onHighlight(text, range.getBoundingClientRect(), mark, ids, e.ctrlKey || e.metaKey)
                    }}
                    onClick={(e) => {
                      if (window.getSelection()?.toString().trim()) return  // finishing a selection, not a click
                      const id = ((e.target as HTMLElement).closest('[data-block-id]') as HTMLElement | null)?.dataset.blockId
                      if (e.shiftKey) { if (id) onPick(id, e.clientX, e.clientY); return }
                      const r = frame.current!.getBoundingClientRect()
                      const hit = annotationAt(mine, (e.clientX - r.left) / r.width * page.width, (e.clientY - r.top) / r.height * page.height)
                      if (hit) { onOpenAnnotation(hit.id); return }
                      onSelect(id ?? null, e.ctrlKey || e.metaKey)
                    }} />
                  <Highlights annotations={mine} activeId={activeAnnotation} onOpen={onOpenAnnotation} />
                </div>
              : pdf
              ? <OriginalPage pdf={pdf} page={page} shift={shift} picked={picked} onPick={onPick} selected={selected} onSelect={onSelect}
                  onHighlight={(text, rect, mark, add) => onHighlight(text, rect, mark, [...new Set(mark?.rects.map((r) => blockUnder(page, r)).filter((id) => id !== undefined))], !!add)} annotations={mine}
                  activeId={activeAnnotation} onOpenAnnotation={onOpenAnnotation}
                  placingText={placingText} onPlaceText={onPlaceText} onUpdateAnnotation={onUpdateAnnotation} flashId={flashId} />
              : <img src={api.pageImage(docId, page.index)} width={w} height={h} alt="" draggable={false} />}
          </div>
        </div>
      </figure>
    </section>
  )
}
