import { useEffect, useRef, useState } from 'react'

const HOLD_MS = 150  // a hold, not a tap: a tapped Alt is the browser's menu key

/** Alt (Option on a Mac) held over a language view shows the original: the translated sections fade out, and the
 *  page image under them is the original page. Released, they come back. Alt as part of a shortcut, or typed into a
 *  field, doesn't count. */
export function usePeek() {
  const [peek, setPeek] = useState(false)
  const peeking = useRef(false)
  useEffect(() => {
    let timer: number | undefined
    const stop = () => { clearTimeout(timer); timer = undefined; peeking.current = false; setPeek(false) }
    const down = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && e.target.closest('input, textarea, select, [contenteditable]')
      if (e.key !== 'Alt' || typing) { stop(); return }
      if (!e.repeat && timer === undefined) timer = window.setTimeout(() => { peeking.current = true; setPeek(true) }, HOLD_MS)
    }
    const up = (e: KeyboardEvent) => {
      if (e.key !== 'Alt') return
      if (peeking.current) e.preventDefault()  // a peek, not a tap: don't open the browser's menu
      stop()
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('blur', stop)
    return () => { stop(); window.removeEventListener('keydown', down); window.removeEventListener('keyup', up); window.removeEventListener('blur', stop) }
  }, [])
  return peek
}
