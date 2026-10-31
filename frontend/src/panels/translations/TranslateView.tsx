import { useEffect, useMemo, useState } from 'react'
import { api, type Estimate } from '../../api'
import { eta, unsupportedNotice } from '../../lib/format'
import LanguagePicker from '../../ui/LanguagePicker'
import { FIGURE_NOTICE, type PanelProps } from './shared'

/** The Translate tab: translate the whole document (or this page) into a language of choice, the language view
 *  shown by default. Starting adds and shows its tab, where the progress fills in. */
export default function TranslateView({ doc, viewLang, currentPage, job, onJob, onTranslateInto, languages }: PanelProps) {
  const [chosen, setLang] = useState<string | null>(null)
  const lang = chosen ?? (viewLang || (doc.source_lang === 'en' ? 'hi' : 'en'))
  const [scope, setScope] = useState<'page' | 'all'>('all')
  const [figures, setFigures] = useState(false)  // text inside images and figures: only when asked
  const [estimate, setEstimate] = useState<Estimate | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pages = useMemo(() => (scope === 'page' ? [currentPage] : undefined), [scope, currentPage])
  const running = job?.status === 'running' && job.kind !== 'structure'  // a translation waits for the layout review
  const name = languages.find((l) => l.code === lang)?.name ?? lang
  useEffect(() => {
    api.estimate(doc.id, [lang], pages, undefined, figures)
      .then((e) => { setEstimate(e); setError(null) }).catch((e) => setError(e.message))
  }, [doc, lang, pages, figures, job?.status])
  const pending = doc.pages.filter((p) => p.source === 'pending_ocr').length

  return (
    <>
      <div className="space-y-3">
        <LanguagePicker label="Translate into" value={lang} onChange={setLang}
          options={languages.map((l) => ({ ...l, disabled: l.code === doc.source_lang ? 'Original language' : undefined }))} />
        <div className="seg">
          {([['all', 'Whole document'], ['page', `Page ${currentPage + 1}`]] as const).map(([s, label]) => (
            <button key={s} onClick={() => setScope(s)} aria-pressed={scope === s}>{label}</button>
          ))}
        </div>
        {estimate && estimate.figure_blocks > 0 && (
          <div className="flex gap-3 text-xs text-muted">
            <button role="switch" aria-checked={figures} onClick={() => setFigures(!figures)} className="toggle mt-0.5"
              aria-label="Also translate text inside images and figures" />
            <span>
              Text in images ({estimate.figure_blocks})
              {figures && <span className="block text-amber-800 mt-0.5">{FIGURE_NOTICE}</span>}
            </span>
          </div>
        )}
        {estimate && estimate.blocks > 0 && <p className="text-xs text-muted">{eta(estimate.minutes)}</p>}
        {unsupportedNotice(doc) && <p className="text-xs text-amber-800">{unsupportedNotice(doc)}</p>}
        {pending > 0 && <p className="text-xs text-amber-800">{pending} scanned page{pending === 1 ? '' : 's'} skipped until OCR</p>}
        {error && <p className="text-xs text-rose-700">{error}</p>}
        <button disabled={!estimate || running || estimate.blocks === 0} className="btn btn-primary w-full"
          onClick={async () => {
            setError(null)
            try { onJob(await api.translate(doc.id, [lang], pages, undefined, figures)); onTranslateInto(lang) }
            catch (e) { setError((e as Error).message) }
          }}>
          {running ? 'Translating…' : estimate?.blocks === 0 ? `Translated into ${name}` : `Translate into ${name}`}
        </button>
      </div>
    </>
  )
}
