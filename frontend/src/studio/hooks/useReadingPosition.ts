import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Doc } from '../../api'
import { useWidth } from '../../lib/hooks'
import { positionOf, savePosition } from '../../lib/reading'

const PX_PER_PT = 4 / 3
const LINE = 24  // px below the scroller's top: where goTo puts a target, and what counts as "being read"

/** Where the reader is: zoom (0 = fit the width), scroll position (restored on open, remembered as they read), the
 *  current page, the point at the top of the view (for the contents' current section), and `goTo`. */
export function useReadingPosition(docId: string, doc: Doc | null) {
  const saved = useMemo(() => positionOf(docId), [docId])  // where this document was left
  // Narrow screens always start fitted (a zoom saved on a big screen would spill over).
  const [zoomSetting, setZoom] = useState(window.innerWidth < 1024 ? 0 : saved?.zoom ?? 0.8)
  const [currentPage, setCurrentPage] = useState(0)
  const [readAt, setReadAt] = useState({ page: 0, top: 0 })  // the point at the top of the view, in PDF points
  const scroller = useRef<HTMLDivElement | null>(null)
  const [scrollerEl, setScrollerEl] = useState<HTMLDivElement | null>(null)
  const attachScroller = useCallback((el: HTMLDivElement | null) => { scroller.current = el; setScrollerEl(el) }, [])
  const scrollWidth = useWidth(scrollerEl)

  const widest = Math.max(...(doc?.pages.map((p) => p.width) ?? [595])) * PX_PER_PT
  const fit = scrollWidth ? Math.min(2, Math.max(0.3, (scrollWidth - 8) / widest)) : 0.8
  const zoom = zoomSetting || fit

  // Restore the scroll position once the pages exist (their frames have fixed sizes, so no wait for drawing).
  const restored = useRef(false)
  useEffect(() => {
    if (!doc || restored.current || !scroller.current) return
    restored.current = true
    if (saved) requestAnimationFrame(() => scroller.current?.scrollTo({ top: saved.scroll }))
  }, [doc, saved])

  const saveTimer = useRef(0)
  const remember = () => {
    clearTimeout(saveTimer.current)
    saveTimer.current = window.setTimeout(() => {
      if (scroller.current) savePosition(docId, { scroll: scroller.current.scrollTop, page: currentPage, zoom: zoomSetting })
    }, 300)
  }
  useEffect(remember, [zoomSetting, currentPage])  // eslint-disable-line react-hooks/exhaustive-deps

  const track = () => {
    const top = scroller.current?.scrollTop ?? 0
    const sections = [...(scroller.current?.querySelectorAll('section[id^="page-"]') ?? [])] as HTMLElement[]
    const visible = sections.findLast((s) => s.offsetTop - 80 <= top)
    if (visible) setCurrentPage(Number(visible.id.slice(5)))
    const line = top + LINE  // the same line goTo scrolls a heading to, so a clicked heading is "current"
    const pageTopOf = (s: HTMLElement) => ((s.querySelector('figure > div') as HTMLElement | null) ?? s).offsetTop
    const at = sections.findLast((s) => pageTopOf(s) <= line + 1)
    if (at) setReadAt({ page: Number(at.id.slice(5)), top: (line - pageTopOf(at)) / (PX_PER_PT * zoom) })
  }
  useEffect(track, [doc, zoom])  // eslint-disable-line react-hooks/exhaustive-deps

  /** Scroll to a page, or to a point on it (`top` in PDF points from the page top). */
  const goTo = (i: number, top = 0) => {
    const section = document.getElementById(`page-${i}`)
    const frame = section?.querySelector('figure > div') as HTMLElement | null
    if (!section || !scroller.current) return
    const pageTop = (frame ?? section).offsetTop  // relative to the scroller, which is the positioned parent
    scroller.current.scrollTo({ top: pageTop + top * PX_PER_PT * zoom - LINE, behavior: 'smooth' })
  }

  return { attachScroller, zoom, zoomSetting, setZoom, currentPage, readAt, goTo, onScroll: () => { track(); remember() } }
}
