import { useEffect, useRef, useState } from 'react'
import { api, type Job, type Language } from '../api'
import LeftSidebar, { type SideTab } from '../panels/sidebar/LeftSidebar'
import TranslationPanel from '../panels/translations/TranslationPanel'
import { useConfirm } from '../ui/useConfirm'
import Toast from '../ui/Toast'
import { useAnnotations } from './hooks/useAnnotations'
import { useLanguageViews } from './hooks/useLanguageViews'
import { usePanels } from './hooks/usePanels'
import { usePeek } from './hooks/usePeek'
import { usePicks } from './hooks/usePicks'
import { usePromptEdits } from './hooks/usePromptEdits'
import { useReadingPosition } from './hooks/useReadingPosition'
import { useSelection } from './hooks/useSelection'
import { useStudioDocument } from './hooks/useStudioDocument'
import { useTranslationJob } from './hooks/useTranslationJob'
import PageView from './pages/PageView'
import PickBar from './PickBar'
import PromptBox from './PromptBox'
import SelectionToolbar, { type Selection } from './SelectionToolbar'
import StudioToolbar from './StudioToolbar'

type Props = {
  docId: string; languages: Language[]; onClose: () => void
  header: (extra?: React.ReactNode) => React.ReactNode
}

const TOAST_MS = 12_000
const FLASH_MS = 1_800

/** The workspace: navigation and notes on the left, the pages in the middle (the original, or a language view), the
 *  prompt box under them, and the Translations panel on the right with the details of whatever is selected. Each
 *  concern lives in a hook (hooks/); this component lays them out and connects them. */
export default function StudioPage({ docId, languages, header, onClose }: Props) {
  const panels = usePanels()
  const { doc, error, setError, pdf, reload, version, redraw, change, applyChange, ocrBusy, runOcr } = useStudioDocument(docId)
  const views = useLanguageViews(docId, doc, languages)
  const { view, setView, shownLang, show, shownLangs, langName } = views
  const position = useReadingPosition(docId, doc)
  const { attachScroller } = position
  const picks = usePicks()
  const selection = useSelection({ inLanguageView: view === 'translated', showRight: panels.showRight })
  const { panel, showPanel } = selection
  const edits = usePromptEdits({ docId, doc, editIds: selection.editIds, setEditIds: selection.setEditIds, shownLang, show, applyChange, redraw })

  const [sideTab, setSideTab] = useState<SideTab>('contents')
  const showSide = (t: SideTab) => { setSideTab(t); panels.showLeft() }
  const notes = useAnnotations(docId, setError, () => showSide('notes'))

  const { confirm, dialog } = useConfirm()
  const peek = usePeek()  // Alt held: the original shows through a language view
  const [toolbar, setToolbar] = useState<Selection | null>(null)
  const [toast, setToast] = useState<{ text: string; lang?: string; block?: string } | null>(null)
  const toldClipped = useRef(new Set<string>())  // "lang:block" already in a notice, so it isn't repeated
  const [flashId, setFlashId] = useState<string | null>(null)
  const [placingText, setPlacingText] = useState(false)  // the next click on the original page places a text box
  const [selectAfterJob, setSelectAfterJob] = useState<string | null>(null)  // one picked section: open it when done

  // A finished job: the pages are drawn again, and a translation's language is offered in a toast.
  const { job, setJob } = useTranslationJob(docId, async (done: Job) => {
    await reload()
    redraw()
    if (done.kind === 'structure') return  // the layout review from upload: its fixes are on the page now
    const ok = done.done > done.failed
    if (ok) views.setShownLang(done.langs[0])
    if (selectAfterJob) { showPanel({ kind: 'block', id: selectAfterJob }); setSelectAfterJob(null) }
    setToast(done.status === 'error' ? { text: `Translation stopped: ${done.error}` } : {
      text: `The ${done.langs.map(langName).join(', ')} translation is ready.${done.failed ? ` Some parts couldn't be translated and stay in the original.` : ''}`,
      lang: ok ? done.langs[0] : undefined,
    })
  })

  useEffect(() => { if (toast) { const t = setTimeout(() => setToast(null), TOAST_MS); return () => clearTimeout(t) } }, [toast])
  // Sections cut off to fit their page: say so once each, and offer the first one's full text in the panel.
  const noteClipped = (ids: string[]) => {
    const fresh = ids.filter((id) => !toldClipped.current.has(`${shownLang}:${id}`))
    if (!fresh.length) return
    fresh.forEach((id) => toldClipped.current.add(`${shownLang}:${id}`))
    setToast({ text: fresh.length === 1 ? 'A section is too long to fit and is cut off.' : `${fresh.length} sections are too long to fit and are cut off.`, block: fresh[0] })
  }
  useEffect(() => {  // Escape cancels placing a text box
    if (!placingText) return
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setPlacingText(false) }
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [placingText])
  useEffect(() => {  // a click elsewhere dismisses the selection toolbar
    const hide = () => { if (!window.getSelection()?.toString().trim()) setToolbar(null) }
    document.addEventListener('selectionchange', hide)
    return () => document.removeEventListener('selectionchange', hide)
  }, [])

  const flash = (id: string) => {
    setFlashId(id)
    setTimeout(() => setFlashId((f) => (f === id ? null : f)), FLASH_MS)
  }
  const openBlock = (blockId: string) => {
    const page = doc?.pages.find((p) => p.blocks.some((b) => b.id === blockId))
    if (!page) return
    position.goTo(page.index, page.blocks.find((b) => b.id === blockId)!.bbox[1])
    showPanel({ kind: 'block', id: blockId })
    flash(blockId)
  }
  const highlightSelection = (color: string, comment: boolean) => {
    if (!toolbar?.mark) return
    const { page, rects, lang } = toolbar.mark
    notes.add({ kind: 'highlight', page, rects, lang, color, quote: toolbar.text }, comment)
    window.getSelection()?.removeAllRanges()
    setToolbar(null)
  }
  // A language view's text is already in its language: the other tabs, or else back into the original's language.
  const otherLangs = view === 'translated' ? shownLangs.filter((l) => l !== shownLang) : shownLangs
  const selectionLangs = otherLangs.length ? otherLangs : view === 'translated' && doc?.source_lang ? [doc.source_lang] : [shownLang]
  /** Selected text → translated into every other tab's language → shown in the panel. */
  const translateSelection = async () => {
    if (!toolbar) return
    const { text } = toolbar
    setToolbar(null)
    showPanel({ kind: 'translating', text, langs: selectionLangs })
    try { showPanel({ kind: 'selection', text, results: await api.translateText(text, selectionLangs) }) }
    catch (e) { setError((e as Error).message); selection.resetPanel() }
  }
  const translatePicked = async () => {
    // Picking a section inside a figure is asking for it, so picked figure text is translated.
    try {
      setJob(await api.translate(docId, [shownLang], undefined, [...picks.picked], true))
      setSelectAfterJob(picks.picked.size === 1 ? [...picks.picked][0] : null)
      panels.slideRightOpen()
    } catch (e) { setError((e as Error).message) }
    picks.clear()
  }
  /** A tab goes; a language with translations only after a confirmation, and its translations (edits too) with it. */
  const removeLanguage = async (lang: string) => {
    if (views.translatedLangs.has(lang)) {
      if (!await confirm({ title: `Remove the ${langName(lang)} translation?`, detail: 'Its edits go too.', action: 'Remove' })) return
      try { await api.removeTranslation(docId, lang) } catch (e) { setError((e as Error).message); return }
      await reload()
      redraw()
    }
    views.removeLanguage(lang)
  }
  const pickedFigures = doc?.pages.flatMap((p) => p.blocks).filter((b) => b.in_figure && picks.picked.has(b.id)).length ?? 0

  const panelView = doc && (
    <TranslationPanel doc={doc} languages={languages} langs={shownLangs} viewLang={shownLang} view={panel} setView={selection.setPanel}
      currentPage={position.currentPage} showing={view === 'translated' ? shownLang : null} onShow={show} applyChange={applyChange}
      job={job} onJob={setJob} onTranslateInto={views.addLanguage} onClose={panels.toggleRight} />
  )

  return (
    <div className="h-screen flex flex-col">
      {header(doc && (
        <StudioToolbar doc={doc} languages={languages} job={job}
          leftShown={panels.leftShown} toggleLeft={panels.toggleLeft} rightShown={panels.rightShown} toggleRight={panels.toggleRight}
          currentPage={position.currentPage} goTo={position.goTo} zoomSetting={position.zoomSetting} setZoom={position.setZoom}
          view={view} setView={setView} shownLang={shownLang} show={show} shownLangs={shownLangs}
          langName={langName} addLanguage={views.addLanguage} removeLanguage={removeLanguage} />
      ))}
      {error && (
        <div role="alert" className="mx-3 mt-3 px-4 py-2 text-sm text-rose-800 rounded-2xl bg-rose-50 border border-rose-200 flex items-center gap-3">
          {error}<button onClick={() => setError(null)} className="btn btn-sm btn-ghost ml-auto">Dismiss</button>
          <button onClick={onClose} className="btn btn-sm">Back to library</button>
        </div>
      )}
      <div className="flex-1 flex min-h-0">
        {doc && panels.leftShown && (
          <div className={panels.leftInline ? 'flex border-r border-line' : 'fixed left-0 top-12 bottom-0 z-40 flex border-r border-line shadow-raised-lg'}>
            <LeftSidebar doc={doc} lang={shownLang} currentPage={position.currentPage} readAt={position.readAt}
              goTo={(p, t) => { position.goTo(p, t); panels.leftDone() }} showView={(l) => (l ? show(l) : setView('original'))}
              tab={sideTab} setTab={setSideTab} annotations={notes.annotations} activeId={notes.active}
              setActive={notes.setActive} onUpdate={notes.update} onDelete={notes.remove} onFound={flash}
              languages={languages} onChange={(c) => applyChange(c, shownLang)}
              placingText={placingText} onAddText={() => { setView('original'); setPlacingText(!placingText); panels.leftDone() }}
              onGlossaryBlock={(id) => { openBlock(id); panels.leftDone() }} />
          </div>
        )}
        {panels.sliding && <div className="fixed inset-0 top-12 z-30 bg-ink/20" onClick={panels.closeSliding} />}
        <div className="flex-1 min-w-0 flex flex-col">
          <div ref={attachScroller} onScroll={() => { position.onScroll(); setToolbar(null) }}
            className={`relative flex-1 min-h-0 overflow-auto p-3 sm:p-6 space-y-8 ${peek && view === 'translated' ? 'peek' : ''}`}>
            {doc?.pages.map((p) => (
              <PageView key={p.index} docId={docId} page={p} zoom={position.zoom} ocrBusy={ocrBusy} onOcr={runOcr}
                view={view} lang={shownLang} version={version} change={change}
                selected={selection.editIds} working={edits.working} onSelect={selection.select}
                pdf={pdf} shift={picks.shift} picked={picks.picked} onPick={picks.toggle} onClipped={(_, ids) => noteClipped(ids)}
                onHighlight={(text, rect, mark, ids, add) => { setToolbar({ text, rect, mark }); selection.selectText(ids, add) }}
                annotations={notes.annotations} activeAnnotation={notes.active}
                onOpenAnnotation={(id) => { notes.setActive(id); showSide('notes') }}
                placingText={placingText && view === 'original'} onUpdateAnnotation={notes.update} flashId={flashId}
                onPlaceText={(page, x, y) => {
                  setPlacingText(false)
                  notes.add({ kind: 'text', page, rects: [[x, y, x + 180, y + 22]], color: '#94a3b8', font_size: 11 }, true)
                }} />
            ))}
            {/* Room after the last page, so a heading near the end can still scroll to the top. */}
            <div aria-hidden style={{ height: 'calc(100vh - 8rem)' }} />
          </div>
          {doc && <PromptBox targets={edits.targets} langName={langName} onEdit={edits.edit} onUndo={edits.undo} />}
        </div>
        {panels.rightShown && (panels.rightInline
          ? <aside className="w-[360px] shrink-0 flex bg-surface border-l border-line"><div className="flex-1 overflow-hidden">{panelView}</div></aside>
          : <aside className="fixed right-0 top-12 bottom-0 z-40 w-[min(360px,100vw)] bg-surface border-l border-line shadow-raised-lg overflow-hidden">{panelView}</aside>)}
      </div>

      {picks.barShown && picks.picked.size > 0 && (
        <PickBar count={picks.picked.size} langName={langName(shownLang)} at={picks.at} figures={pickedFigures}
          onTranslate={translatePicked} onCancel={picks.clear} />
      )}
      {toolbar && (
        <SelectionToolbar selection={toolbar} translateTitle={`Translate into ${selectionLangs.map(langName).join(', ')}`}
          onHighlight={highlightSelection} onTranslate={translateSelection}
          onDefine={() => { showPanel({ kind: 'define', text: toolbar.text }); setToolbar(null) }} />
      )}
      {dialog}
      {toast && (
        <Toast text={toast.text} onDismiss={() => setToast(null)}
          action={toast.lang ? { label: 'Show translation', run: () => { show(toast.lang!); setToast(null) } }
            : toast.block ? { label: 'Show', run: () => { showPanel({ kind: 'block', id: toast.block! }); setToast(null) } } : undefined} />
      )}
    </div>
  )
}
