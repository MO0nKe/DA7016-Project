import { useState } from 'react'
import type { Block } from '../api'
import { scriptLetter } from '../lib/scripts'
import { SendIcon, UndoIcon } from '../ui/icons'

/** A selected section and the language view the prompt edits (a section not translated yet is edited from its original). */
export type Target = { block: Block; lang: string }

type Props = {
  targets: Target[]  // the selected sections; none: the box is grayed out
  langName: (code: string) => string
  onEdit: (instruction: string) => Promise<void>
  onUndo: () => Promise<void>  // undo each selected section's last edit
}

/** The prompt box under the pages: ask for a change to the selected sections' translations (their wording,
 *  language, maths, bold, alignment, bullets). Grayed out until a section is selected. */
export default function PromptBox({ targets, langName, onEdit, onUndo }: Props) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const ready = targets.filter((t) => t.lang)  // none: the document has no language view yet
  const edits = ready.some((t) => (t.block.translations[t.lang]?.edits.length ?? 0) > 0)

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    try { await fn() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  const send = () => { if (ready.length && !busy && text.trim()) run(async () => { await onEdit(text.trim()); setText('') }) }
  const placeholder = !targets.length ? 'Select a section to edit' : ready.length ? 'Describe a change' : 'Add a language with + first'

  return (
    <div className="shrink-0 px-3 pb-3 sm:px-6">
      <div className={`mx-auto max-w-2xl card bg-bark p-1.5 border-ink focus-within:ring-2 focus-within:ring-accent/20 ${ready.length ? '' : 'opacity-60'}`} aria-busy={busy}>
        <div className="flex items-end gap-1">
          {[...new Set(ready.map((t) => t.lang))].map((l) => (
            <span key={l} className="script m-1" title={`Edits the ${langName(l)} view`}>{scriptLetter(l)}</span>
          ))}
          <textarea value={text} onChange={(e) => { setText(e.target.value); setError(null) }} disabled={!ready.length || busy} rows={1}
            placeholder={placeholder} aria-label="Ask for a change to the selected sections"
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            className="field text-sm resize-none flex-1 border-0 focus:ring-0 disabled:cursor-not-allowed" />
          {edits && (
            <button onClick={() => run(onUndo)} disabled={busy} title="Undo" aria-label="Undo" className="btn btn-ghost btn-icon"><UndoIcon /></button>
          )}
          <button onClick={send} disabled={!ready.length || busy || !text.trim()} title="Apply" aria-label="Apply"
            className={`btn btn-primary btn-icon ${busy ? 'bg-accent border-accent animate-pulse' : ''}`}><SendIcon /></button>
        </div>
        {error && <p className="px-2 pt-1 text-xs text-rose-700">{error}</p>}
      </div>
    </div>
  )
}
