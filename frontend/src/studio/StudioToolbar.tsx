import type { Doc, Job, Language } from '../api'
import { percent } from '../lib/format'
import { ChevronLeftIcon, ChevronRightIcon, MenuIcon, TranslateIcon } from '../ui/icons'
import LanguagePicker from '../ui/LanguagePicker'
import type { View } from './hooks/useLanguageViews'

const ZOOMS = [0.5, 0.65, 0.8, 1, 1.25, 1.5]

type Props = {
  doc: Doc; languages: Language[]; job: Job | null
  leftShown: boolean; toggleLeft: () => void; rightShown: boolean; toggleRight: () => void
  currentPage: number; goTo: (page: number) => void
  zoomSetting: number; setZoom: (z: number) => void
  view: View; setView: (v: View) => void; shownLang: string; show: (lang: string) => void
  shownLangs: string[]; langName: (code: string) => string
  addLanguage: (lang: string) => void; removeLanguage: (lang: string) => void
}

/** The studio's part of the top bar: the sidebar toggle, page navigation, zoom, the view tabs
 *  (Original | languages | +; the shown one is underlined, a running translation fills its tab's
 *  line) and the Translations panel button. */
export default function StudioToolbar(p: Props) {
  const { doc, view, shownLang, langName } = p
  return (
    <>
      <span className="hidden 2xl:inline text-sm font-medium text-ink truncate max-w-56" title={doc.filename}>{doc.filename.replace(/\.pdf$/i, '')}</span>
      <button className="btn btn-ghost btn-icon" onClick={p.toggleLeft} aria-pressed={p.leftShown} aria-label="Contents, pages, search, notes and glossary"
        title={p.leftShown ? 'Hide the sidebar' : 'Show the sidebar'}><MenuIcon /></button>
      <div className="flex items-center gap-1 text-sm">
        <button className="btn btn-ghost btn-icon" aria-label="Previous page" disabled={p.currentPage === 0} onClick={() => p.goTo(p.currentPage - 1)}><ChevronLeftIcon /></button>
        <span className="tabular-nums px-1.5 whitespace-nowrap text-muted">{p.currentPage + 1} / {doc.pages.length}</span>
        <button className="btn btn-ghost btn-icon" aria-label="Next page" disabled={p.currentPage >= doc.pages.length - 1} onClick={() => p.goTo(p.currentPage + 1)}><ChevronRightIcon /></button>
      </div>
      <LanguagePicker label="Zoom" className="h-8 w-28" value={String(p.zoomSetting)} onChange={(z) => p.setZoom(Number(z))}
        options={[{ code: '0', name: 'Fit width' }, ...ZOOMS.map((z) => ({ code: String(z), name: `${Math.round(z * 100)}%` }))]} />
      <div className="views" role="tablist" aria-label="Show the pages">
        <button role="tab" aria-selected={view === 'original'} onClick={() => p.setView('original')} title="Or hold Alt over a language view">
          <span className="hang" />Original
        </button>
        {p.shownLangs.map((l) => {
          const running = p.job?.status === 'running' && p.job.langs.includes(l) ? percent(p.job) : null
          return (
          <button key={l} role="tab" aria-selected={view === 'translated' && shownLang === l} data-running={running !== null || undefined}
            onClick={() => p.show(l)} className="group" title={running === null ? undefined : p.job?.phase === 'layout' ? 'Checking the layout first' : `Translating, ${running}%`}>
            <span className="hang" />
            {running !== null && <span className="hang hang-progress" style={{ width: `${running}%` }} />}
            {langName(l)}
            {running === null && (  // not while it's being translated
              <span role="button" aria-label={`Remove ${langName(l)}`} title={`Remove ${langName(l)}`}
                onClick={(e) => { e.stopPropagation(); p.removeLanguage(l) }}
                className="-mr-1 text-faint hover:text-ink opacity-0 group-hover:opacity-100">×</span>
            )}
          </button>
          )
        })}
      </div>
      <LanguagePicker variant="chip" label="Add a language" placeholder="+" value={null} className="h-7 w-7 justify-center"
        onChange={p.addLanguage}
        options={p.languages.filter((l) => !p.shownLangs.includes(l.code))
          .map((l) => ({ ...l, disabled: l.code === doc.source_lang ? 'Original language' : undefined }))} />
      <div className="flex-1" />
      <button className="btn btn-ghost" aria-pressed={p.rightShown} onClick={p.toggleRight} title={p.rightShown ? 'Hide the Translations panel' : 'Show the Translations panel'}>
        <TranslateIcon />Translations
      </button>
    </>
  )
}
