import { useState } from 'react'
import type { Translation } from '../../api'
import { UndoIcon } from '../../ui/icons'

const PRESETS = ['More formal', 'Simpler language', 'Shorter', 'Keep technical terms in English', 'Fix grammar']

export type EditActions = {
  edit: (instruction: string, regenerate?: boolean) => Promise<void>  // OpenRouter prompt edit
  revert: () => Promise<void>  // undo the last edit
}

type Props = { t: Translation; actions: EditActions }

/** Reviewer tools for one section's translation: quick changes, undo, and the edit history.
 *  Other changes are asked for in the prompt box under the pages. */
export default function EditMenu({ t, actions }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    try { await fn() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  const edit = (text: string, regenerate = false) => text.trim() && run(() => actions.edit(text.trim(), regenerate))
  const last = t.edits.at(-1)

  return (
    <div className="space-y-2.5 text-left" onMouseDown={(e) => e.stopPropagation()}>
      <div className="flex flex-wrap gap-1.5">
        {PRESETS.map((p) => <button key={p} disabled={busy} onClick={() => edit(p)} className="btn btn-sm">{p}</button>)}
      </div>
      {busy && <p className="text-xs text-muted">Working…</p>}
      {last && (
        <div className="flex flex-wrap items-center gap-1.5">
          <button disabled={busy} onClick={() => edit(last.instruction, true)} className="btn btn-sm">Try again</button>
          <button disabled={busy} onClick={() => run(actions.revert)} className="btn btn-sm ml-auto"><UndoIcon />Undo</button>
        </div>
      )}
      {error && <p className="text-xs text-rose-700">{error}</p>}
      {t.edits.length > 0 && (
        <details className="text-xs text-muted">
          <summary className="cursor-pointer select-none">History ({t.edits.length})</summary>
          <ol className="mt-1 space-y-0.5">
            {[...t.edits].reverse().map((e, i) => (
              <li key={i}>“{e.instruction}” · {e.model}{e.cost_usd ? ` · $${e.cost_usd.toFixed(6)}` : ''} · {e.ts.slice(11, 16)}</li>
            ))}
          </ol>
        </details>
      )}
    </div>
  )
}
