import { useState } from 'react'
import { api } from '../../api'

/** "Romanise" link under a piece of translated text: shows it in Latin script (Bodhan transliterate,
 *  fetched on click; repeats are free from the cache). Nothing for English. */
export default function Romanise({ text, lang }: { text: string; lang: string }) {
  const [shown, setShown] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (lang === 'en' || !text.trim()) return null

  const load = async () => {
    setBusy(true)
    setError(null)
    try { setShown((await api.romaniseText(text, lang)).text) } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  return (
    <div className="mt-1.5 text-xs">
      {shown === null
        ? <button onClick={load} disabled={busy} className="btn btn-sm btn-ghost -ml-2">{busy ? 'Romanising…' : 'Romanise'}</button>
        : <>
            <p className="text-sm text-muted italic whitespace-pre-wrap" lang={`${lang}-Latn`}>{shown}</p>
            <button onClick={() => setShown(null)} className="btn btn-sm btn-ghost -ml-2">Hide romanisation</button>
          </>}
      {error && <p className="text-rose-600">{error}</p>}
    </div>
  )
}
