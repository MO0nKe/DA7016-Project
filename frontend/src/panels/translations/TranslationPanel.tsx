import { useState } from 'react'
import { CloseIcon } from '../../ui/icons'
import BlockView from './BlockView'
import { Original, TranslationCard } from './Cards'
import DefinitionCard from './DefinitionCard'
import type { PanelProps } from './shared'
import TranslateView from './TranslateView'

export { FIGURE_NOTICE, type PanelView } from './shared'

/** The Translations panel, in two tabs: Translations, the one place a translation's details live (a section in
 *  every language view, a selection, a word); and Translate, the document into a language of choice. Its progress
 *  shows in that language's tab above the pages. */
export default function TranslationPanel(props: PanelProps) {
  const { languages, view, onClose } = props
  const name = (code: string) => languages.find((l) => l.code === code)?.name ?? code
  const [tab, setTab] = useState<'translations' | 'translate'>(view.kind === 'document' ? 'translate' : 'translations')
  const [seen, setSeen] = useState(view)
  if (view !== seen) {  // something newly chosen: show it
    setSeen(view)
    if (view.kind !== 'document') setTab('translations')
  }

  return (
    <div className="flex flex-col min-h-0 h-full">
      <div className="flex items-center gap-2 mx-4 pt-3 border-b border-ink">
        <div className="views" role="tablist" aria-label="Translations panel">
          {(['translations', 'translate'] as const).map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
              <span className="hang" />{t === 'translations' ? 'Translations' : 'Translate'}
            </button>
          ))}
        </div>
        {onClose && <button onClick={onClose} className="btn btn-sm btn-ghost btn-icon ml-auto" aria-label="Close panel"><CloseIcon /></button>}
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-4">
        {tab === 'translate' && <TranslateView {...props} />}
        {tab === 'translations' && view.kind === 'document' && <p className="text-sm text-faint">Select a section</p>}
        {tab === 'translations' && view.kind === 'block' && <BlockView key={view.id} {...props} id={view.id} name={name} />}
        {tab === 'translations' && view.kind === 'translating' && <>
          <Original text={view.text} />
          <p className="text-xs text-muted">Translating into {view.langs.map(name).join(', ')}…</p>
        </>}
        {tab === 'translations' && view.kind === 'selection' && <>
          <Original text={view.text} />
          {view.results.map((r) => (
            <TranslationCard key={r.lang} lang={r.lang} name={name(r.lang)} rtl={!!languages.find((l) => l.code === r.lang)?.rtl}
              text={r.error ? '' : r.text} error={r.error} />
          ))}
        </>}
        {tab === 'translations' && view.kind === 'define' && <>
          <Original text={view.text} title="Word" />
          <DefinitionCard key={view.text} word={view.text} />
        </>}
      </div>
    </div>
  )
}
