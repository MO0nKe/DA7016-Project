import { useEffect, useState } from 'react'
import { api, type Health, type Language } from './api'
import Library from './library/LibraryPage'
import Studio from './studio/StudioPage'
import PannaMark from './ui/PannaMark'

export default function App() {
  const [docId, setDocId] = useState<string | null>(() => new URLSearchParams(location.search).get('doc'))
  const [languages, setLanguages] = useState<Language[]>([])
  const [health, setHealth] = useState<Health | null>(null)

  useEffect(() => {
    api.languages().then(setLanguages).catch(() => {})
    api.health().then(setHealth).catch(() => {})
  }, [])
  // Opening a document adds a history entry, so the browser's Back returns to the library.
  const open = (id: string | null) => {
    if (id === docId) return
    setDocId(id)
    history.pushState(null, '', id ? `?doc=${id}` : location.pathname)
  }
  useEffect(() => {
    const sync = () => setDocId(new URLSearchParams(location.search).get('doc'))
    window.addEventListener('popstate', sync)
    return () => window.removeEventListener('popstate', sync)
  }, [])

  const header = (extra?: React.ReactNode) => (
    <header className="min-h-12 shrink-0 flex flex-wrap items-center gap-x-2 gap-y-2 px-3 py-1.5 sm:py-0 bg-surface border-b border-ink relative z-[45]">
      {/* Above the slide-over panels (z-40), so its dropdowns show over them. */}
      <button onClick={() => open(null)} className="flex items-center gap-2 font-serif text-xl text-ink" aria-label="Panna: back to the library">
        <PannaMark size={26} />
        <span className="hidden sm:inline" aria-hidden="true">Panna</span>
      </button>
      <div className="order-last basis-full sm:order-none sm:basis-0 flex-1 flex items-center gap-2 min-w-0 overflow-x-auto [scrollbar-width:none] [&>*]:shrink-0 py-1.5">{extra}</div>
      {health && (
        <span title={`Bodhan: ${health.bodhan}\nOpenRouter: ${health.openrouter}`}
          className={`kicker ml-auto sm:ml-0 inline-flex items-center gap-1.5 ${health.spends_credits ? 'text-rose-700' : 'text-emerald-700'}`}>
          <span className={`size-1.5 rounded-full ${health.spends_credits ? 'bg-rose-600' : 'bg-emerald-600'}`} />
          {health.spends_credits ? 'Live' : 'Mock'}
        </span>
      )}
    </header>
  )

  return docId
    ? <Studio docId={docId} languages={languages} header={header} onClose={() => open(null)} />
    : <div className="h-screen flex flex-col"><Library onOpen={open} languages={languages} header={header} /></div>
}
