import { useEffect, useState } from 'react'
import { api, type BlockChange, type Doc, type GlossaryMiss, type Language, type Term } from '../../api'
import LanguagePicker from '../../ui/LanguagePicker'

type Props = {
  doc: Doc; lang: string | null; languages: Language[]
  onSelectBlock: (id: string) => void; onChange: (c: BlockChange) => void
}

const FIX = 'Use the pinned glossary terms for this section.'

/** Pinned term translations, and the translated sections that don't use them yet. */
export default function GlossaryPanel({ doc, lang, languages, onSelectBlock, onChange }: Props) {
  const [terms, setTerms] = useState<Term[]>([])
  const [misses, setMisses] = useState<GlossaryMiss[]>([])
  const [form, setForm] = useState({ source: '', target: '', lang: lang ?? 'hi' })
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const name = (code: string) => languages.find((l) => l.code === code)?.name ?? code

  const refresh = () => {
    api.glossary().then(setTerms).catch((e) => setError(e.message))
    if (lang) api.glossaryCheck(doc.id, lang).then(setMisses).catch((e) => setError(e.message))
  }
  useEffect(refresh, [doc, lang])

  const add = async () => {
    if (!form.source.trim() || !form.target.trim()) return
    try { await api.addTerm({ ...form, source: form.source.trim(), target: form.target.trim() }); setForm({ ...form, source: '', target: '' }); refresh() }
    catch (e) { setError((e as Error).message) }
  }
  /** Prompt-edit each section (OpenRouter); the backend adds the pinned terms to the prompt. */
  const fix = async (ids: string[]) => {
    for (const id of ids) {
      setBusy(id)
      try { onChange(await api.edit(doc.id, id, lang!, FIX)) } catch (e) { setError((e as Error).message); break }
    }
    setBusy(null)
    refresh()
  }

  const input = 'field'
  const card = 'rounded-2xl bg-surface border border-black/[0.06] shadow-raised-sm p-3.5 space-y-3'
  return (
    <div className="p-3 space-y-3">
      <div className={card}>
        <h3 className="text-sm font-medium text-ink">Pin a term</h3>
        <div className="grid grid-cols-2 gap-2">
          <input className={input} placeholder="Term, e.g. enrolment" value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} />
          <LanguagePicker label="Language" value={form.lang} onChange={(lang) => setForm({ ...form, lang })}
            options={languages.filter((l) => l.code !== 'en')} />
          <input className={`${input} col-span-2`} placeholder="Always translate it as…" value={form.target} lang={form.lang}
            onChange={(e) => setForm({ ...form, target: e.target.value })} onKeyDown={(e) => { if (e.key === 'Enter') add() }} />
        </div>
        <button onClick={add} className="btn btn-sm btn-primary">Pin term</button>
        {terms.length > 0 && (
          <ul className="divide-y divide-black/[0.06] text-sm">
            {terms.map((t) => (
              <li key={t.id} className="flex items-center gap-2 py-1.5">
                <span className="truncate">{t.source}</span><span className="text-muted">→</span>
                <span className="truncate font-medium" lang={t.lang}>{t.target}</span>
                <span className="ml-auto text-xs text-muted">{name(t.lang)}</span>
                <button onClick={() => api.removeTerm(t.id).then(refresh)} className="btn btn-sm btn-ghost btn-icon" aria-label={`Unpin ${t.source}`}>✕</button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className={card}>
        <h3 className="text-sm font-medium text-ink">Check {lang ? name(lang) : ''} translation</h3>
        {!lang && <p className="text-xs text-muted">Choose a language in the top bar.</p>}
        {lang && misses.length === 0 && <p className="text-xs text-muted">All sections use your terms.</p>}
        {misses.length > 0 && <>
          <p className="text-xs text-muted">{misses.length} section{misses.length > 1 ? 's miss' : ' misses'} a pinned term.</p>
          <ul className="space-y-2">
            {misses.map((m) => (
              <li key={m.block_id} className="text-xs rounded-xl bg-well shadow-inset p-2.5 space-y-1">
                <button onClick={() => onSelectBlock(m.block_id)} className="text-left text-ink line-clamp-2 hover:underline">p. {m.page + 1} · {m.text}</button>
                <div className="flex items-center gap-2">
                  <span className="text-amber-700">missing: {m.missing.map((t) => `${t.source} → ${t.target}`).join(', ')}</span>
                  <button disabled={busy !== null} onClick={() => fix([m.block_id])} className="ml-auto btn btn-sm">
                    {busy === m.block_id ? 'Fixing…' : 'Fix'}
                  </button>
                </div>
              </li>
            ))}
          </ul>
          <button disabled={busy !== null} onClick={() => fix(misses.map((m) => m.block_id))}
            className="btn btn-sm w-full">Fix all</button>
        </>}
        {error && <p className="text-xs text-rose-600">{error}</p>}
      </div>
    </div>
  )
}
