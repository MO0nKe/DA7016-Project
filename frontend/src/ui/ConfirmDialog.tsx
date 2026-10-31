import { useEffect, useRef, useState } from 'react'

/** `value` asks for text (its starting value) instead of a yes or no. */
export type Question = { title: string; detail?: string; action: string; value?: string }

/** A question over the page (useConfirm asks it): yes or no, or a line of text. Cancel is focused (the field, when
 *  there is one); Enter answers, Escape or a click outside cancels. */
export default function ConfirmDialog({ title, detail, action, value, onAnswer }: Question & { onAnswer: (ok: boolean, text: string) => void }) {
  const first = useRef<HTMLInputElement & HTMLButtonElement>(null)
  const [text, setText] = useState(value ?? '')
  const asking = value !== undefined
  useEffect(() => { first.current?.focus(); if (asking) first.current?.select() }, [asking])
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onAnswer(false, '') }
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onAnswer])
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink/20 p-4" onClick={() => onAnswer(false, '')}>
      <form role={asking ? 'dialog' : 'alertdialog'} aria-modal aria-labelledby="confirm-title" aria-describedby={detail ? 'confirm-detail' : undefined}
        className="popover w-full max-w-sm p-5 space-y-4" onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => { e.preventDefault(); if (!asking || text.trim()) onAnswer(true, text.trim()) }}>
        <div className="space-y-1">
          <h2 id="confirm-title" className="font-serif text-lg text-ink">{title}</h2>
          {detail && <p id="confirm-detail" className="text-sm text-muted">{detail}</p>}
        </div>
        {asking && <input ref={first} value={text} onChange={(e) => setText(e.target.value)} aria-labelledby="confirm-title" className="field" />}
        <div className="flex gap-2 justify-end">
          <button type="button" ref={asking ? undefined : first} onClick={() => onAnswer(false, '')} className="btn btn-ghost">Cancel</button>
          <button type="submit" disabled={asking && !text.trim()} className="btn btn-primary">{action}</button>
        </div>
      </form>
    </div>
  )
}
