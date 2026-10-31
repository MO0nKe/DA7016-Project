import { useEffect, useState } from 'react'

/** Sections picked with Shift-click for translating. Their outlines show while Shift is held; when it's released the
 *  pick bar appears next to the last pick, and Escape or a click outside it drops the picks. */
export function usePicks() {
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [barShown, setBarShown] = useState(false)
  const [at, setAt] = useState({ x: 0, y: 0 })
  const [shift, setShift] = useState(false)

  const clear = () => { setPicked(new Set()); setBarShown(false) }
  const toggle = (id: string, x: number, y: number) => {
    setPicked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n })
    setAt({ x, y })
    setBarShown(false)
  }

  useEffect(() => {
    const down = (e: KeyboardEvent) => { if (e.key === 'Shift') setShift(true) }
    const up = (e: KeyboardEvent) => { if (e.key === 'Shift') { setShift(false); setBarShown(true) } }
    const reset = () => setShift(false)
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('blur', reset)
    return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up); window.removeEventListener('blur', reset) }
  }, [])
  useEffect(() => {
    if (!barShown) return
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') clear() }
    const away = (e: MouseEvent) => { if (!(e.target as Element).closest('[data-pick-bar]') && !e.shiftKey) clear() }
    window.addEventListener('keydown', esc)
    window.addEventListener('mousedown', away)
    return () => { window.removeEventListener('keydown', esc); window.removeEventListener('mousedown', away) }
  }, [barShown])

  return { picked, barShown, at, shift, toggle, clear }
}
