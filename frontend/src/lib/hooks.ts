import { useEffect, useState } from 'react'

/** Whether a CSS media query matches, kept up to date. */
export function useMedia(query: string) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const m = window.matchMedia(query)
    const update = () => setMatches(m.matches)
    m.addEventListener('change', update)
    update()
    return () => m.removeEventListener('change', update)
  }, [query])
  return matches
}

/** An element's content width, kept up to date. */
export function useWidth(el: HTMLElement | null) {
  const [width, setWidth] = useState(0)
  useEffect(() => {
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [el])
  return width
}
