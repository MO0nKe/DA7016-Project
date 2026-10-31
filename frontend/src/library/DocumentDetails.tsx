import { Fragment } from 'react'
import { api, type DocSummary, type LibraryState } from '../api'
import LanguagePicker from '../ui/LanguagePicker'
import { day, title } from './documents'

/** The selected document: its first page, a few facts, and Open. */
export default function DocumentDetails({ doc, lib, name, opened, onOpen, onDelete, onMove }: {
  doc: DocSummary; lib: LibraryState; name: (code: string) => string; opened?: { page: number; at: number }
  onOpen: (id: string) => void; onDelete: (d: DocSummary) => void; onMove: (folder: string | null) => void
}) {
  const facts: [string, React.ReactNode][] = [
    ['Pages', doc.page_count],
    ['Language', doc.source_lang ? name(doc.source_lang) : doc.unsupported_lang ?? '—'],
    ['Translations', doc.languages.map(name).join(', ') || '—'],
    ['Added', day(doc.created)],
    ...(opened ? [['Last read', `Page ${opened.page + 1} · ${day(opened.at)}`] as [string, React.ReactNode]] : []),
    ...(doc.pending_ocr.length ? [['Scanned', <span key="ocr" className="text-amber-700">{doc.pending_ocr.length} page{doc.pending_ocr.length === 1 ? '' : 's'} need OCR</span>] as [string, React.ReactNode]] : []),
  ]
  return (
    <div className="p-4 space-y-4">
      <img src={api.pageImage(doc.id, 0)} alt="" className="w-full h-44 object-cover object-top rounded border border-line bg-white" />
      <h2 className="font-semibold text-ink break-words">{title(doc)}</h2>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
        {facts.map(([k, v]) => <Fragment key={k}><dt className="text-muted">{k}</dt><dd className="text-ink">{v}</dd></Fragment>)}
        <dt className="text-muted self-center">Folder</dt>
        <dd>
          <LanguagePicker label="Folder" className="h-7 text-xs" value={lib.placement[doc.id] ?? ''} onChange={(f) => onMove(f || null)}
            options={[{ code: '', name: 'Unfiled' }, ...lib.folders.map((f) => ({ code: f.id, name: f.name }))]} />
        </dd>
      </dl>
      <div className="flex gap-2">
        <button onClick={() => onOpen(doc.id)} className="btn btn-primary flex-1">Open</button>
        <button onClick={() => onDelete(doc)} className="btn btn-ghost text-rose-700">Delete</button>
      </div>
    </div>
  )
}
