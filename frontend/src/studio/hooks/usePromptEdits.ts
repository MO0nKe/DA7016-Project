import { useState } from 'react'
import { api, type Block, type BlockChange, type Doc } from '../../api'
import type { Target } from '../PromptBox'

type Props = {
  docId: string; doc: Doc | null; editIds: string[]; setEditIds: (ids: string[]) => void
  shownLang: string; show: (lang: string) => void
  applyChange: (c: BlockChange, lang: string) => void; redraw: () => void
}

/** Prompt-box edits of the selected sections, in the language view shown (in the Original view, the last one shown).
 *  One request per section, all at once. An edit lands in the language it was written in ("put this in Tamil" lands
 *  in Tamil), and the pages then show that view. */
export function usePromptEdits({ docId, doc, editIds, setEditIds, shownLang, show, applyChange, redraw }: Props) {
  const blocksById = new Map(doc?.pages.flatMap((p) => p.blocks).map((b) => [b.id, b]))
  const targets: Target[] = editIds.flatMap((id) => (blocksById.has(id) ? [{ block: blocksById.get(id)!, lang: shownLang }] : []))
  const [working, setWorking] = useState<string[]>([])  // sections with an edit or undo under way, until each lands

  const changeAll = async (call: (block: Block, lang: string) => Promise<BlockChange>, only: (t: Target) => boolean = () => true) => {
    const ready = targets.filter(only)
    setWorking(ready.map((t) => t.block.id))
    const results = await Promise.allSettled(ready.map(async (t) => {
      try {
        const c = await call(t.block, t.lang)
        applyChange(c, c.lang)
        return c.lang
      } finally { setWorking((w) => w.filter((id) => id !== t.block.id)) }
    }))
    if (ready.length > 1) redraw()  // the pages swap one section at a time; several are drawn again together
    const landed = results.flatMap((r) => (r.status === 'fulfilled' ? [r.value] : []))
    if (landed.length) show(landed.find((l) => l !== shownLang) ?? landed[0])
    const failed = ready.filter((_, i) => results[i].status === 'rejected')
    if (!failed.length) return
    const reason = ((results.find((r) => r.status === 'rejected') as PromiseRejectedResult).reason as Error).message
    if (failed.length === ready.length) throw new Error(reason)
    setEditIds(failed.map((t) => t.block.id))  // so trying again doesn't change the others twice
    throw new Error(`${failed.length} of ${ready.length} sections weren't changed (still selected, Apply tries them again): ${reason}`)
  }

  return {
    targets, working,
    edit: (instruction: string) => changeAll((block, lang) => api.edit(docId, block.id, lang, instruction)),
    undo: () => changeAll((block, lang) => api.revert(docId, block.id, lang),
      (t) => (t.block.translations[t.lang]?.edits.length ?? 0) > 0),
  }
}
