import { useEffect, useState } from 'react'
import { api, type Annotation, type BlockChange, type Doc, type Language, type OutlineItem } from '../../api'
import GlossaryPanel from './GlossaryPanel'
import { TextIcon } from '../../ui/icons'

export type SideTab = 'contents' | 'pages' | 'search' | 'notes' | 'glossary'

type Props = {
  doc: Doc; lang: string | null; currentPage: number
  readAt: { page: number; top: number }
  goTo: (page: number, top?: number) => void
  showView: (lang: string) => void  // '' the original, else a language view
  tab: SideTab; setTab: (t: SideTab) => void
  annotations: Annotation[]; activeId: string | null; setActive: (id: string | null) => void
  onUpdate: (a: Annotation) => void; onDelete: (id: string) => void
  onFound: (blockId: string) => void
  languages: Language[]; onGlossaryBlock: (blockId: string) => void; onChange: (c: BlockChange) => void
  placingText: boolean; onAddText: () => void  // the next click on the original page places a text box
}

const COLORS = ['#fde047', '#86efac', '#93c5fd', '#f9a8d4']

/** Navigation and reading notes: the document's sections, and its highlights, comments and text boxes. */
export default function LeftSidebar({ doc, lang, currentPage, readAt, goTo, showView, tab, setTab, annotations: all, activeId, setActive, onUpdate, onDelete, onFound, languages, onGlossaryBlock, onChange, placingText, onAddText }: Props) {
  const annotations = all
  const viewName = (l: string) => l ? languages.find((x) => x.code === l)?.name ?? l : 'Original'
  const [outline, setOutline] = useState<OutlineItem[] | null>(null)
  const [query, setQuery] = useState('')
  const q = query.trim().toLowerCase()
  // Search the source text and every translation; table cells are searched too.
  const results = q.length < 2 ? [] : doc.pages.flatMap((p) => p.blocks.flatMap((b) => {
    const texts: [string, string][] = [['Original', b.cells ? b.cells.map((c) => c.text).join(' · ') : b.text],
      ...Object.entries(b.translations).map(([l, t]): [string, string] => [l, t.cells ? t.cells.join(' · ') : t.text])]
    return texts.filter(([, t]) => t.toLowerCase().includes(q)).map(([where, t]) => {
      const at = t.toLowerCase().indexOf(q)
      return { b, page: p.index, where, before: t.slice(Math.max(0, at - 40), at), hit: t.slice(at, at + q.length), after: t.slice(at + q.length, at + q.length + 60) }
    })
  }))
  useEffect(() => { api.outline(doc.id).then(setOutline).catch(() => setOutline([])) }, [doc.id])
  useEffect(() => {  // a new or clicked note gets its comment box focused and scrolled into view
    if (tab !== 'notes' || !activeId) return
    if (annotations.find((a) => a.id === activeId)?.kind === 'text') return  // typed into on the page itself
    const box = document.querySelector<HTMLTextAreaElement>(`[data-note="${activeId}"] textarea`)
    box?.scrollIntoView({ block: 'nearest' })
    if (box && !box.value) box.focus()
    // Not on every annotation change: typing a comment would scroll and refocus at each key.
  }, [activeId, tab, annotations.length])  // eslint-disable-line react-hooks/exhaustive-deps
  // The current section: the last heading at or above the top of the view (a little slack for rounding).
  const current = (outline ?? []).findLastIndex((i) => i.page < readAt.page || (i.page === readAt.page && i.top <= readAt.top + 4))
  const title = (i: OutlineItem) => i.title

  return (
    <aside className="w-80 shrink-0 bg-surface flex flex-col overflow-hidden">
      <div className="tab-row">
        {(['contents', 'pages', 'search', 'notes', 'glossary'] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} aria-pressed={tab === t}>
            {t === 'contents' ? 'Contents' : t === 'pages' ? 'Pages' : t === 'search' ? 'Search' : t === 'glossary' ? 'Glossary' : 'Notes'}
          </button>
        ))}
      </div>
      {tab === 'glossary' && (
        <div className="flex-1 overflow-auto">
          <GlossaryPanel doc={doc} lang={lang} languages={languages} onChange={onChange} onSelectBlock={onGlossaryBlock} />
        </div>
      )}
      {tab === 'pages' && (
        <div className="flex-1 overflow-auto p-3 grid grid-cols-2 gap-3 content-start">
          {doc.pages.map((p) => (
            <button key={p.index} onClick={() => goTo(p.index)} className="space-y-1 text-center">
              <img src={api.pageImage(doc.id, p.index)} alt={`Page ${p.index + 1}`} loading="lazy"
                style={{ aspectRatio: `${p.width} / ${p.height}` }}
                className={`w-full bg-white rounded-md shadow-raised-sm ${p.index === currentPage ? 'ring-2 ring-accent' : 'hover:ring-2 hover:ring-black/10'}`} />
              <span className="text-xs text-muted">
                {p.index + 1}{annotations.some((a) => a.page === p.index) ? ' ✎' : ''}
                {p.source === 'pending_ocr' ? ' · needs OCR' : ''}
              </span>
            </button>
          ))}
        </div>
      )}
      {tab === 'search' && (
        <div className="flex-1 flex flex-col min-h-0">
          <div className="p-2">
            <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search"
              className="field" />
            {q.length >= 2 && <p className="px-2 pt-1.5 text-xs text-muted">{results.length} match{results.length === 1 ? '' : 'es'}</p>}
          </div>
          <ul className="flex-1 overflow-auto px-2 pb-2 space-y-1">
            {results.slice(0, 200).map((r, i) => (
              <li key={i}>
                <button onClick={() => { goTo(r.page, r.b.bbox[1]); onFound(r.b.id) }}
                  className="list-row text-xs">
                  <span className="block text-muted mb-0.5">p. {r.page + 1} · {r.where}</span>
                  <span>{r.before && '…'}{r.before}<mark className="bg-yellow-200 rounded-sm">{r.hit}</mark>{r.after}{r.after && '…'}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {tab === 'notes' && (
        <div className="flex-1 overflow-auto p-2 space-y-2 text-sm">
          <button onClick={onAddText} aria-pressed={placingText} className="btn btn-sm btn-ghost w-full justify-start">
            <TextIcon />{placingText ? 'Click on the page…' : 'Add text box'}
          </button>
          {annotations.length === 0 && <p className="p-2 text-xs text-muted">No notes yet</p>}
          {[...new Set(annotations.map((a) => a.lang))].sort((a, b) => (a && viewName(a)).localeCompare(b && viewName(b))).map((l) => <section key={l} className="space-y-2">
          <h3 className="kicker px-1 pt-2">{viewName(l)}</h3>
          {annotations.filter((a) => a.lang === l).sort((a, b) => a.page - b.page || a.rects[0][1] - b.rects[0][1]).map((a) => (
            <div key={a.id} data-note={a.id} onClick={() => { setActive(a.id); showView(a.lang); goTo(a.page, a.rects[0][1]) }}
              className={`rounded-xl p-2.5 space-y-1.5 cursor-pointer bg-surface border shadow-raised-sm ${a.id === activeId ? 'border-accent' : 'border-black/[0.06]'}`}>
              <div className="flex items-center gap-1.5 text-xs text-muted">
                <span className="size-2.5 rounded-full" style={{ background: a.color }} />
                <span>{a.kind === 'text' ? 'Text box' : a.kind === 'note' ? 'Note' : 'Highlight'} · p. {a.page + 1}</span>
                <span className="ml-auto flex gap-1">
                  {COLORS.map((c) => (
                    <button key={c} title="Change colour" onClick={(e) => { e.stopPropagation(); onUpdate({ ...a, color: c }) }}
                      className="size-3 rounded-full border border-white shadow" style={{ background: c }} />
                  ))}
                  <button title="Delete" onClick={(e) => { e.stopPropagation(); onDelete(a.id) }} className="ml-1 hover:text-rose-600">✕</button>
                </span>
              </div>
              {a.quote && <p className="text-xs text-muted border-l-2 pl-2 line-clamp-3" style={{ borderColor: a.color }}>{a.quote}</p>}
              <textarea defaultValue={a.comment} key={a.id + a.comment} rows={a.id === activeId ? 3 : 1}
                placeholder={a.kind === 'text' ? 'Text' : 'Add a comment…'}
                onClick={(e) => e.stopPropagation()}
                onBlur={(e) => { if (e.target.value !== a.comment) onUpdate({ ...a, comment: e.target.value }) }}
                className="field text-xs rounded-xl py-1.5" />
            </div>
          ))}
          </section>)}
        </div>
      )}
      <nav className={`flex-1 overflow-auto p-2 text-sm ${tab === 'contents' ? '' : 'hidden'}`}>
        {outline === null && <p className="p-2 text-xs text-muted">Loading…</p>}
        {outline?.length === 0 && <p className="p-2 text-xs text-muted">No headings</p>}
        {outline?.map((i, n) => (
          <button key={n} onClick={() => goTo(i.page, i.top)} title={i.title}
            style={{ paddingLeft: 8 + (i.level - 1) * 14 }}
            aria-current={n === Math.max(current, 0)}
            className={`list-row truncate pr-2.5 ${i.level === 1 ? 'font-medium' : 'text-muted'}`}>
            {title(i)}
            <span className="float-right text-xs text-muted tabular-nums">{i.page + 1}</span>
          </button>
        ))}
      </nav>
    </aside>
  )
}
