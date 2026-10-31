import { useEffect, useState } from 'react'
import { api, type Block, type Translation } from '../../api'
import type { EditActions } from './EditMenu'
import { Original, TranslationCard } from './Cards'
import type { PanelProps } from './shared'

/** A translation as plain text: a table's cells row by row, otherwise its text. */
function translationText(block: Block | undefined, t: Translation) {
  if (block?.cells && t.cells && t.cells.length === block.cells.length) {
    const rows = new Map<number, string[]>()
    block.cells.forEach((c, i) => rows.set(c.row, [...(rows.get(c.row) ?? []), t.cells![i]]))
    return [...rows.entries()].sort((a, b) => a[0] - b[0]).map(([, r]) => r.join(' | ')).join('\n')
  }
  return t.text
}

/** A section: its original text and every translation, which one the pages show, edits, and missing languages. */
export default function BlockView({ doc, languages, langs, id, name, showing, onShow, applyChange, onJob, job }: PanelProps & { id: string; name: (c: string) => string }) {
  const page = doc.pages.find((p) => p.blocks.some((b) => b.id === id))
  const block = page?.blocks.find((b) => b.id === id)
  const [busy, setBusy] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  // Languages asked for stay "Translating…" until the job they started ends.
  useEffect(() => { if (job?.status !== 'running') setBusy([]) }, [job?.status])  // eslint-disable-line react/set-state-in-effect
  if (!page || !block) return <p className="text-sm text-muted">This section is no longer in the document.</p>

  const translations = Object.fromEntries(Object.entries(block.translations).filter(([, t]) => t.status !== 'error'))
  const shownLangs = [...new Set([...Object.keys(translations), ...langs])]
  const missing = langs.filter((l) => !translations[l])
  const translate = async (codes: string[]) => {
    setError(null)
    setBusy((b) => [...b, ...codes])
    // Asking for one section is asking for it, so text inside a figure is translated too.
    try { onJob(await api.translate(doc.id, codes, undefined, [block.id], true)) }
    catch (e) { setError((e as Error).message); setBusy((b) => b.filter((c) => !codes.includes(c))) }
  }
  const actions = (lang: string): EditActions => ({
    edit: async (instruction, regenerate) => applyChange(await api.edit(doc.id, block.id, lang, instruction, regenerate), lang),
    revert: async () => applyChange(await api.revert(doc.id, block.id, lang), lang),
  })

  return (
    <>
      <Original text={block.cells ? block.cells.map((c) => c.text).join(' | ') : block.text} />
      <div className="space-y-2.5">
        {shownLangs.map((l) => {
          const t = translations[l]
          return (
            <TranslationCard key={l} lang={l} name={name(l)} rtl={!!languages.find((x) => x.code === l)?.rtl}
              text={t ? translationText(block, t) : ''} shown={showing === l} onShow={() => onShow(l)}
              edit actions={actions(l)} translation={t}
              onTranslate={() => translate([l])} busy={busy.includes(l)} />
          )
        })}
        {missing.length > 1 && (
          <button onClick={() => translate(missing)} disabled={missing.every((l) => busy.includes(l))} className="btn btn-sm w-full">
            Translate all
          </button>
        )}
        {error && <p className="text-xs text-rose-700">{error}</p>}
      </div>
    </>
  )
}
