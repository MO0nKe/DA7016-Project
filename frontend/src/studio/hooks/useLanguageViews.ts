import { useEffect, useState } from 'react'
import type { Doc, Language } from '../../api'

export type View = 'original' | 'translated'

/** The views of the pages: Original, and one per language (the tabs). A language has a view when the document has
 *  translations in it, or when it was added to this document (kept per document; a new document starts with the
 *  language last chosen anywhere). `shownLang` is the language view shown, or the last one shown while the
 *  Original is. */
export function useLanguageViews(docId: string, doc: Doc | null, languages: Language[]) {
  const [added, setAdded] = useState<string[]>(() => JSON.parse(localStorage.getItem(`langs:${docId}`)
    ?? JSON.stringify((JSON.parse(localStorage.getItem('langs') ?? '["hi"]') as string[]).slice(0, 1))))
  const [chosenView, setView] = useState<View>('original')
  const [chosenLang, setShownLang] = useState(added[0] ?? '')
  const langName = (code: string) => languages.find((l) => l.code === code)?.name ?? code
  useEffect(() => { localStorage.setItem(`langs:${docId}`, JSON.stringify(added)) }, [docId, added])

  const langs = added.filter((l) => l !== doc?.source_lang)  // never a view in the document's own language
  const translatedLangs = new Set(doc?.pages.flatMap((p) => p.blocks.flatMap((b) =>
    Object.entries(b.translations).filter(([, t]) => t.status !== 'error').map(([l]) => l))))
  const shownLangs = [...new Set([...translatedLangs, ...langs])].sort((a, b) => langName(a).localeCompare(langName(b)))
  // The shown language always has a tab ('' when there is none); with no tabs, the pages show the original.
  const shownLang = shownLangs.includes(chosenLang) ? chosenLang : shownLangs[0] ?? ''
  const view: View = shownLangs.length ? chosenView : 'original'

  const show = (lang: string) => { setShownLang(lang); setView('translated') }
  return {
    view, setView, shownLang, setShownLang, show, shownLangs, translatedLangs, langName,
    /** A new tab for this document, shown at once; also the default for the next new document. */
    addLanguage: (lang: string) => {
      if (!added.includes(lang)) setAdded([...added, lang])
      localStorage.setItem('langs', JSON.stringify([lang]))
      show(lang)
    },
    removeLanguage: (lang: string) => setAdded(added.filter((l) => l !== lang)),
  }
}
