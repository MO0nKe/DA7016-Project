import { useLayoutEffect, useRef } from 'react'
import type { Mark } from './pages/marks'
import { TranslateIcon } from '../ui/icons'

const HIGHLIGHTS = ['#fde047', '#86efac', '#93c5fd', '#f9a8d4']
const MAX_TRANSLATE_CHARS = 20_000  // Bodhan's context limit (the backend's MAX_SNIPPET_CHARS)
const WORD = /^[A-Za-z][A-Za-z'-]*( [A-Za-z'-]+){0,2}[.,;:!?]?$/  // up to three English words: Define

export type Selection = { text: string; rect: DOMRect; mark?: Mark }

type Props = {
  selection: Selection; translateTitle: string
  onHighlight: (color: string, comment: boolean) => void
  onDefine: () => void
  onTranslate: () => void
}

/** The toolbar under selected text: highlight colours and Comment (on the original), Define and Translate.
 *  Buttons keep the selection (mousedown is prevented). */
export default function SelectionToolbar({ selection, translateTitle, onHighlight, onDefine, onTranslate }: Props) {
  const keep = (e: React.MouseEvent) => e.preventDefault()
  const { text, rect, mark } = selection
  const box = useRef<HTMLDivElement>(null)
  // Centred under the selection, but kept inside the window (near its edge the first swatch was cut off).
  useLayoutEffect(() => {
    const w = box.current!.offsetWidth
    box.current!.style.left = `${Math.max(8, Math.min(rect.left + rect.width / 2 - w / 2, window.innerWidth - w - 8))}px`
  })
  return (
    <div ref={box} style={{ top: rect.bottom + 8 }} className="fixed z-50 popover p-1.5 flex items-center gap-1">
      {mark && <>
        {HIGHLIGHTS.map((c) => (
          <button key={c} title="Highlight" aria-label="Highlight" onMouseDown={keep} onClick={() => onHighlight(c, false)}
            className="size-6 rounded-full border-2 border-white shadow-raised-sm hover:scale-110 transition-transform" style={{ background: c }} />
        ))}
        <button onMouseDown={keep} onClick={() => onHighlight(HIGHLIGHTS[0], true)} className="btn btn-sm btn-ghost">Comment</button>
        <span className="w-px h-4 bg-black/10 mx-0.5" />
      </>}
      {text.length > MAX_TRANSLATE_CHARS
        ? <span className="px-2 text-xs text-amber-800">Too long for one request; select less</span>
        : <>
          {WORD.test(text) && <button onMouseDown={keep} onClick={onDefine} className="btn btn-sm btn-ghost">Define</button>}
          <button onMouseDown={keep} onClick={onTranslate} title={translateTitle} className="btn btn-sm btn-primary">
            <TranslateIcon />Translate
          </button>
        </>}
    </div>
  )
}
