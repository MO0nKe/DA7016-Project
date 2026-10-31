import { useState } from 'react'
import type { PanelView } from '../../panels/translations/TranslationPanel'

/** What is selected: what the Translations panel shows, and the sections the prompt box edits (the one opened in the
 *  panel, those selected text covers, or those clicked; Ctrl/⌘ adds). They stay selected while the prompt is typed;
 *  a click on the page around them, or "Whole document" in the panel, lets them go. */
export function useSelection({ inLanguageView, showRight }: { inLanguageView: boolean; showRight: () => void }) {
  const [panel, setPanelView] = useState<PanelView>({ kind: 'document' })
  const [editIds, setEditIds] = useState<string[]>([])

  const setPanel = (v: PanelView) => {
    setPanelView(v)
    if (v.kind === 'block') setEditIds([v.id]); else if (v.kind === 'document') setEditIds([])
  }
  const showPanel = (v: PanelView) => { setPanel(v); showRight() }

  return {
    panel, setPanel, showPanel, editIds, setEditIds,
    /** Back to the document view without letting the selected sections go (a failed selection translation). */
    resetPanel: () => setPanelView({ kind: 'document' }),
    /** A click on a section, or on the page around them (null). A language view opens a clicked section in the panel;
     *  the Original view only shows it there if the panel is open. */
    select: (id: string | null, add: boolean) => {
      if (add) { if (id) setEditIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id])); return }
      if (!id) { setEditIds([]); if (panel.kind === 'block') setPanelView({ kind: 'document' }); return }
      if (inLanguageView) showPanel({ kind: 'block', id }); else setPanel({ kind: 'block', id })
    },
    /** Selected text selects the sections it covers. */
    selectText: (ids: string[], add: boolean) => {
      if (ids.length) setEditIds((old) => (add ? [...new Set([...old, ...ids])] : ids))
    },
  }
}
