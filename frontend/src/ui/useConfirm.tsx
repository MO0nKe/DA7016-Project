import { useState } from 'react'
import ConfirmDialog, { type Question } from './ConfirmDialog'

/** The app's questions, in place of the browser's: `await confirm({ title, detail, action })` is true on yes;
 *  `await prompt({ title, action, value })` is the text entered (trimmed, never empty), or null. Render `dialog`
 *  somewhere in the page. */
export function useConfirm() {
  const [ask, setAsk] = useState<(Question & { resolve: (ok: boolean, text: string) => void }) | null>(null)
  const confirm = (q: Question) => new Promise<boolean>((resolve) => setAsk({ ...q, value: undefined, resolve }))
  const prompt = (q: Question & { value: string }) => new Promise<string | null>((resolve) =>
    setAsk({ ...q, resolve: (ok, text) => resolve(ok ? text : null) }))
  const answer = (ok: boolean, text: string) => { ask?.resolve(ok, text); setAsk(null) }
  const dialog = ask && <ConfirmDialog {...ask} onAnswer={answer} />
  return { confirm, prompt, dialog }
}
