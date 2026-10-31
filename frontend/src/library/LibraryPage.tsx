import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type DocSummary, type Folder, type Language, type LibraryState } from '../api'
import { useMedia } from '../lib/hooks'
import { scriptLetter } from '../lib/scripts'
import { forget, recent } from '../lib/reading'
import { useConfirm } from '../ui/useConfirm'
import ContextMenu, { type MenuItem } from '../ui/ContextMenu'
import { FilePlusIcon, FolderIcon, FolderPlusIcon, GridIcon, LibraryIcon, ListIcon, MenuIcon, SearchIcon } from '../ui/icons'
import DocumentDetails from './DocumentDetails'
import { day, title } from './documents'
import TranslateDialog from './TranslateDialog'
import LanguagePicker from '../ui/LanguagePicker'

type Place = 'all' | 'unfiled' | string  // a folder id
type SortKey = 'title' | 'pages' | 'added' | 'opened'
const SORTS = [{ code: 'opened', name: 'Opened' }, { code: 'added', name: 'Added' }, { code: 'title', name: 'Title' }, { code: 'pages', name: 'Pages' }]
type Menu = { x: number; y: number; items: MenuItem[] }

/** The library, laid out like Zotero's: folders on the left, the folder's documents as a table or as cards (their
 *  first page) on the paper, the selected document's details on the right. Double-click (or Enter) opens a
 *  document; drag documents onto folders to file them; right-click for more; drop PDFs anywhere on the list to add
 *  them. */
export default function Library({ onOpen, languages, header }: {
  onOpen: (id: string) => void; languages: Language[]; header: (extra?: React.ReactNode) => React.ReactNode
}) {
  const [docs, setDocs] = useState<DocSummary[]>([])
  const [loaded, setLoaded] = useState(false)  // no "Drop PDFs here" before the first list arrives
  const [lib, setLib] = useState<LibraryState>({ folders: [], placement: {} })
  const [place, setPlace] = useState<Place>(() => localStorage.getItem('libraryPlace') ?? 'all')
  const [selected, setSelected] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<{ key: SortKey; up: boolean }>({ key: 'opened', up: false })
  const [cards, setCards] = useState(() => localStorage.getItem('libraryLayout') === 'cards')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [dropTarget, setDropTarget] = useState<string | null>(null)
  const [menu, setMenu] = useState<Menu | null>(null)
  const { confirm, prompt, dialog } = useConfirm()
  const [uploaded, setUploaded] = useState<DocSummary | null>(null)  // just uploaded: ask what to translate it into
  const input = useRef<HTMLInputElement>(null)
  const wide = useMedia('(min-width: 768px)')  // folders beside the table, or sliding over it below this
  const roomy = useMedia('(min-width: 1100px)')  // room for the details pane
  const [foldersOpen, setFoldersOpen] = useState(false)
  const name = (code: string) => languages.find((l) => l.code === code)?.name ?? code
  const fail = (e: unknown) => setError((e as Error).message)

  const refresh = () => Promise.all([api.documents().then(setDocs), api.library().then((l) => {
    setLib(l)
    // A remembered folder may be gone, or belong to the other data dir (mock and live share localStorage).
    setPlace((p) => p === 'all' || p === 'unfiled' || l.folders.some((f) => f.id === p) ? p : 'all')
  })]).catch(fail).finally(() => setLoaded(true))
  useEffect(() => { refresh() }, [])
  useEffect(() => { localStorage.setItem('libraryPlace', place) }, [place])
  useEffect(() => { localStorage.setItem('libraryLayout', cards ? 'cards' : 'list') }, [cards])
  const closeMenu = useCallback(() => setMenu(null), [])

  const opened = Object.fromEntries(recent().map(([id, p]) => [id, p]))
  const folderOf = (d: DocSummary) => lib.placement[d.id] ?? null
  const current = lib.folders.find((f) => f.id === place)
  const value = (d: DocSummary): string | number => sort.key === 'title' ? title(d).toLowerCase() : sort.key === 'pages' ? d.page_count
    : sort.key === 'added' ? d.created : opened[d.id]?.at ?? 0
  const shown = docs
    .filter((d) => place === 'all' || (place === 'unfiled' ? !folderOf(d) : folderOf(d) === place))
    .filter((d) => d.filename.toLowerCase().includes(query.trim().toLowerCase()))
    .sort((a, b) => (value(a) < value(b) ? -1 : value(a) > value(b) ? 1 : 0) * (sort.up ? 1 : -1))
  const doc = docs.find((d) => d.id === selected) ?? null

  const upload = async (file?: File) => {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const d = await api.upload(file)
      if (current) await api.placeDocument(d.id, current.id)  // new uploads land in the open folder
      setSelected(d.id)
      setUploaded(d)
      refresh()
    } catch (e) { fail(e) } finally { setBusy(false) }
  }
  const newFolder = async (parent: string | null) => {
    const n = await prompt({ title: 'New folder', action: 'Create', value: '' })
    if (n) { const f = await api.addFolder(n, parent).catch(fail); if (f) { await refresh(); setPlace(f.id) } }
  }
  const renameFolder = async (f: Folder) => {
    const n = await prompt({ title: 'Rename folder', action: 'Rename', value: f.name })
    if (n) { await api.renameFolder(f.id, n).catch(fail); refresh() }
  }
  const deleteFolder = async (f: Folder) => {
    if (!await confirm({ title: `Delete the folder "${f.name}"?`, detail: 'Its documents stay in the library.', action: 'Delete' })) return
    await api.removeFolder(f.id).catch(fail)
    if (place === f.id) setPlace(f.parent ?? 'all')
    refresh()
  }
  const deleteDoc = async (d: DocSummary) => {
    if (!await confirm({ title: `Delete ${d.filename}?`, action: 'Delete' })) return
    await api.remove(d.id).catch(fail)
    forget(d.id)
    setSelected(null)
    refresh()
  }
  const drop = async (target: string | null, e: React.DragEvent) => {
    e.preventDefault()
    setDropTarget(null)
    const [kind, id] = e.dataTransfer.getData('text/plain').split(':')
    if (!id || id === target) return
    await (kind === 'doc' ? api.placeDocument(id, target) : api.moveFolder(id, target)).catch(fail)
    refresh()
  }
  const dropProps = (target: string | null, key: string) => ({
    onDragOver: (e: React.DragEvent) => { if (!e.dataTransfer.types.includes('Files')) { e.preventDefault(); setDropTarget(key) } },
    onDragLeave: () => setDropTarget(null),
    onDrop: (e: React.DragEvent) => drop(target, e),
  })
  const contextMenu = (e: React.MouseEvent, items: MenuItem[]) => { e.preventDefault(); e.stopPropagation(); setMenu({ x: e.clientX, y: e.clientY, items }) }
  const go = (p: Place) => { setPlace(p); setSelected(null); setFoldersOpen(false) }

  const row = (key: string, depth = 0) => ({
    className: `list-row flex items-center gap-2 truncate ${dropTarget === key ? 'ring-2 ring-accent' : ''}`,
    style: { paddingLeft: 8 + depth * 14 },
  })
  const tree = (parent: string | null, depth: number): React.ReactNode =>
    lib.folders.filter((f) => f.parent === parent).sort((a, b) => a.name.localeCompare(b.name)).map((f) => (
      <div key={f.id}>
        <button draggable onDragStart={(e) => e.dataTransfer.setData('text/plain', `folder:${f.id}`)} {...dropProps(f.id, f.id)}
          onClick={() => go(f.id)} aria-current={place === f.id} {...row(f.id, depth + 1)}
          onContextMenu={(e) => contextMenu(e, [
            { label: 'New subfolder', run: () => newFolder(f.id) },
            { label: 'Rename', run: () => renameFolder(f) },
            { label: 'Delete folder', run: () => deleteFolder(f), danger: true },
          ])}>
          <FolderIcon className="shrink-0 text-muted" /><span className="truncate">{f.name}</span>
        </button>
        {tree(f.id, depth + 1)}
      </div>
    ))

  const toolbar = (
    <>
      {!wide && <button className="btn btn-icon btn-ghost" aria-label="Folders" onClick={() => setFoldersOpen(!foldersOpen)}><MenuIcon /></button>}
      <button className="btn btn-icon btn-ghost" title="New folder" aria-label="New folder" onClick={() => newFolder(current?.id ?? null)}><FolderPlusIcon /></button>
      <button className="btn btn-icon btn-ghost" title="Add a PDF" aria-label="Add a PDF" disabled={busy} onClick={() => input.current?.click()}><FilePlusIcon /></button>
      <input ref={input} type="file" accept="application/pdf" className="hidden" onChange={(e) => { upload(e.target.files?.[0]); e.target.value = '' }} />
      {busy && <span className="text-xs text-muted">Adding…</span>}
      {error && <button className="text-xs text-rose-700 truncate max-w-80" title="Dismiss" onClick={() => setError(null)}>{error}</button>}
      <div className="flex-1" />
      {cards && <LanguagePicker label="Sort" options={SORTS} value={sort.key} className="h-8 w-28"
        onChange={(key) => setSort({ key: key as SortKey, up: key === 'title' })} />}
      <span className="flex">
        <button className="btn btn-icon btn-ghost" title="List" aria-label="List" aria-pressed={!cards} onClick={() => setCards(false)}><ListIcon /></button>
        <button className="btn btn-icon btn-ghost" title="Cards" aria-label="Cards" aria-pressed={cards} onClick={() => setCards(true)}><GridIcon /></button>
      </span>
      <label className="relative w-56">
        <SearchIcon className="absolute left-2 top-2 text-faint" />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search" aria-label="Search the library" className="field pl-8" />
      </label>
    </>
  )
  // A document in either layout: click selects, double-click opens, drag files it, right-click for more.
  const item = (d: DocSummary) => ({
    draggable: true,
    onDragStart: (e: React.DragEvent) => e.dataTransfer.setData('text/plain', `doc:${d.id}`),
    onClick: () => setSelected(d.id),
    onDoubleClick: () => onOpen(d.id),
    onContextMenu: (e: React.MouseEvent) => { setSelected(d.id); contextMenu(e, [
      { label: 'Open', run: () => onOpen(d.id) },
      { label: 'Delete', run: () => deleteDoc(d), danger: true },
    ]) },
    'aria-selected': d.id === selected,
  })
  const scripts = (d: DocSummary) => d.languages.map((l) => <span key={l} className="script" title={name(l)}>{scriptLetter(l)}</span>)
  const column = (key: SortKey, label: string, className = '') => (
    <th className={`px-3 py-1.5 font-medium text-left ${className}`}>
      <button onClick={() => setSort({ key, up: sort.key === key ? !sort.up : key === 'title' })} className="hover:text-ink">
        {label}{sort.key === key && <span aria-hidden className="ml-1">{sort.up ? '▲' : '▼'}</span>}
      </button>
    </th>
  )

  return (
    <>
      {header(toolbar)}
      {dialog}
      {uploaded && <TranslateDialog doc={uploaded} languages={languages} onOpen={onOpen} onClose={() => setUploaded(null)} />}
      {menu && <ContextMenu {...menu} onClose={closeMenu} />}
      <div className="flex-1 flex min-h-0">
        {!wide && foldersOpen && <div className="fixed inset-0 top-12 z-30 bg-ink/20" onClick={() => setFoldersOpen(false)} />}
        <nav className={`${wide ? 'w-56 shrink-0' : `fixed left-0 top-12 bottom-0 z-40 w-64 shadow-raised-lg ${foldersOpen ? '' : 'hidden'}`}
          bg-surface border-r border-line p-2 space-y-0.5 overflow-auto`}
          onContextMenu={(e) => contextMenu(e, [{ label: 'New folder', run: () => newFolder(null) }])}>
          <button onClick={() => go('all')} aria-current={place === 'all'} {...row('all')}><LibraryIcon className="shrink-0 text-muted" />My library</button>
          {tree(null, 0)}
          <button onClick={() => go('unfiled')} aria-current={place === 'unfiled'} {...dropProps(null, 'root')} {...row('root')}>
            <FolderIcon className="shrink-0 text-faint" />Unfiled
          </button>
        </nav>

        <main className={`flex-1 min-w-0 overflow-auto relative ${cards ? '' : 'bg-surface'} ${dragging ? 'ring-2 ring-inset ring-accent bg-accent/[0.03]' : ''}`}
          onDragOver={(e) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); setDragging(true) } }}
          onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false) }}
          onDrop={(e) => { if (!e.dataTransfer.files.length) return; e.preventDefault(); setDragging(false); upload(e.dataTransfer.files[0]) }}
          onClick={(e) => { if (e.target === e.currentTarget) setSelected(null) }}
          onKeyDown={(e) => {
            const i = shown.findIndex((d) => d.id === selected)
            const step = { ArrowDown: 1, ArrowUp: -1, ...(cards ? { ArrowRight: 1, ArrowLeft: -1 } : {}) }[e.key]
            if (step) {
              e.preventDefault()
              const next = shown[Math.min(shown.length - 1, Math.max(0, i + step))]
              if (next) setSelected(next.id)
            } else if (e.key === 'Enter' && doc) onOpen(doc.id)
            else if ((e.key === 'Delete' || e.key === 'Backspace') && doc) deleteDoc(doc)
          }} tabIndex={-1}>
          {cards ? (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(168px,1fr))] gap-5 p-5">
              {shown.map((d) => (
                <div key={d.id} {...item(d)} title={d.filename}
                  className="doc-card cursor-default select-none">
                  <img src={api.pageImage(d.id, 0)} alt="" loading="lazy" className="w-full aspect-[3/4] object-contain object-top bg-white" />
                  <div className="p-2.5 space-y-1.5">
                    <p className="text-sm text-ink truncate">{title(d)}</p>
                    <div className="flex items-center gap-1 text-xs text-muted">
                      {scripts(d)}<span className="ml-auto tabular-nums">{d.page_count} p</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
          <table className="w-full text-sm table-fixed">
            <thead className="sticky top-0 bg-surface border-b border-line text-xs text-muted">
              <tr>
                {column('title', 'Title')}
                {column('pages', 'Pages', 'w-20')}
                <th className="px-3 py-1.5 font-medium text-left w-40 hidden lg:table-cell">Translations</th>
                {column('added', 'Added', 'w-32 hidden sm:table-cell')}
                {column('opened', 'Opened', 'w-32 hidden sm:table-cell')}
              </tr>
            </thead>
            <tbody>
              {shown.map((d) => {
                const on = d.id === selected
                return (
                  <tr key={d.id} {...item(d)} className={`cursor-default select-none ${on ? 'bg-wash' : 'odd:bg-well/60 hover:bg-black/[0.03]'}`}>
                    <td className="px-3 py-1.5 truncate" title={d.filename}>{title(d)}</td>
                    <td className="px-3 py-1.5 tabular-nums text-muted">{d.page_count}</td>
                    <td className="px-3 py-1 hidden lg:table-cell" aria-label={d.languages.map(name).join(', ')}>
                      <span className="flex gap-1 overflow-hidden">{scripts(d)}</span>
                    </td>
                    <td className="px-3 py-1.5 hidden sm:table-cell text-muted">{day(d.created)}</td>
                    <td className="px-3 py-1.5 hidden sm:table-cell text-muted">{opened[d.id] ? day(opened[d.id].at) : ''}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          )}
          {loaded && shown.length === 0 && (
            <p className="absolute inset-0 grid place-items-center text-sm text-faint pointer-events-none">
              {query ? 'No matches' : 'Drop PDFs here'}
            </p>
          )}
        </main>

        {roomy && (
          <aside className="w-72 shrink-0 bg-surface border-l border-line overflow-auto">
            {doc ? <DocumentDetails doc={doc} lib={lib} name={name} opened={opened[doc.id]} onOpen={onOpen} onDelete={deleteDoc}
              onMove={async (folder) => { await api.placeDocument(doc.id, folder).catch(fail); refresh() }} />
              : <p className="h-full grid place-items-center text-sm text-faint">{shown.length} document{shown.length === 1 ? '' : 's'}</p>}
          </aside>
        )}
      </div>
    </>
  )
}
