import { useEffect, useState } from 'react'
import { api, type DocSummary, type Estimate, type Language } from '../api'
import { eta, unsupportedNotice } from '../lib/format'
import LanguagePicker from '../ui/LanguagePicker'

/** After an upload: choose the language to translate the document into, then Translate (the document
 *  opens with the translation running) or open the original only. */
export default function TranslateDialog({ doc, languages, onOpen, onClose }: {
  doc: DocSummary; languages: Language[]; onOpen: (id: string) => void; onClose: () => void
}) {
  // The last language chosen, unless it's the document's own (which can't be chosen).
  const [lang, setLang] = useState(() => {
    const saved = (JSON.parse(localStorage.getItem('langs') ?? '["hi"]') as string[])[0] ?? 'hi'
    return saved !== doc.source_lang ? saved : doc.source_lang === 'en' ? 'hi' : 'en'
  })
  const [fetched, setFetched] = useState<{ lang: string; value: Estimate } | null>(null)
  const estimate = fetched?.lang === lang ? fetched.value : null  // none while another language's is shown
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { api.estimate(doc.id, [lang]).then((value) => setFetched({ lang, value })).catch((e) => setError(e.message)) }, [doc.id, lang])
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onClose])
  const translate = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.translate(doc.id, [lang])
      // The document opens with this language's tab (useLanguageViews), and the dialog offers it again next time.
      const tabs = JSON.parse(localStorage.getItem(`langs:${doc.id}`) ?? '[]') as string[]
      localStorage.setItem(`langs:${doc.id}`, JSON.stringify([...new Set([...tabs, lang])]))
      const saved = JSON.parse(localStorage.getItem('langs') ?? '[]') as string[]
      localStorage.setItem('langs', JSON.stringify([lang, ...saved.filter((l) => l !== lang)].slice(0, 4)))
      onOpen(doc.id)
    } catch (e) { setError((e as Error).message); setBusy(false) }
  }
  const scanned = doc.pending_ocr.length
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink/20 p-4" onClick={onClose}>
      <div role="dialog" aria-modal aria-labelledby="translate-title" className="popover w-full max-w-sm p-5 space-y-4" onClick={(e) => e.stopPropagation()}>
        <div>
          <h2 id="translate-title" className="font-serif text-lg text-ink">Translate</h2>
          <p className="text-xs text-muted truncate" title={doc.filename}>{doc.filename}</p>
        </div>
        <LanguagePicker label="Translate into" value={lang} onChange={setLang}
          options={languages.map((l) => ({ ...l, disabled: l.code === doc.source_lang ? 'Original language' : undefined }))} />
        {estimate && <p className="text-xs text-muted">{estimate.blocks === 0 ? 'Already translated.' : `${eta(estimate.minutes)}.`}</p>}
        {unsupportedNotice(doc) && <p className="text-xs text-amber-800">{unsupportedNotice(doc)}</p>}
        {scanned > 0 && <p className="text-xs text-amber-800">{scanned} scanned page{scanned === 1 ? '' : 's'} skipped until OCR.</p>}
        {error && <p className="text-xs text-rose-700">{error}</p>}
        <div className="flex gap-2 justify-end">
          <button onClick={() => onOpen(doc.id)} className="btn btn-ghost">Not now</button>
          <button onClick={translate} disabled={busy || !estimate || estimate.blocks === 0} className="btn btn-primary">
            {busy ? 'Starting…' : 'Translate'}
          </button>
        </div>
      </div>
    </div>
  )
}
