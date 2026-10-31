import type { BlockChange, Doc, Job, Language, Snippet } from '../../api'

export const FIGURE_NOTICE = 'Text inside images and figures rarely fits its space once translated, so it may look janky.'

/** What the Translations tab shows: nothing yet, a section (its original and translations),
 *  a selection's translation, or a dictionary entry. */
export type PanelView =
  | { kind: 'document' }
  | { kind: 'block'; id: string }
  | { kind: 'translating'; text: string; langs: string[] }
  | { kind: 'selection'; text: string; results: Snippet[] }
  | { kind: 'define'; text: string }

/** The panel's props, shared by its views. */
export type PanelProps = {
  doc: Doc; languages: Language[]
  langs: string[]  // the language views (tabs)
  viewLang: string  // the language view shown, or last shown (the Original view): what Translate fills in
  view: PanelView; setView: (v: PanelView) => void; currentPage: number
  showing: string | null  // the language the page shows (null: the original)
  onShow: (lang: string) => void  // show the pages in this language
  applyChange: (c: BlockChange, lang: string) => void
  job: Job | null; onJob: (j: Job) => void
  onTranslateInto: (lang: string) => void  // a translation started: add and show its language's tab
  onClose?: () => void
}
