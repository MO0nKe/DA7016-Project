import { useEffect, useState } from 'react'
import { api, type Annotation } from '../../api'

/** The reader's notes on this document (highlights, comments, text boxes), saved as they change. `onOpen` shows the
 *  notes list when a new note should be written into at once. */
export function useAnnotations(docId: string, onError: (message: string) => void, onOpen: () => void) {
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [active, setActive] = useState<string | null>(null)
  useEffect(() => { api.annotations(docId).then(setAnnotations).catch(() => {}) }, [docId])

  const add = async (a: Partial<Annotation>, open = false) => {
    try {
      const saved = await api.addAnnotation(docId, a)
      setAnnotations((xs) => [...xs, saved])
      if (open) { setActive(saved.id); onOpen() }
      return saved
    } catch (e) { onError((e as Error).message) }
  }
  const update = async (a: Annotation) => {
    setAnnotations((xs) => xs.map((x) => (x.id === a.id ? a : x)))
    try { await api.updateAnnotation(docId, a) } catch (e) { onError((e as Error).message) }
  }
  const remove = async (id: string) => {
    setAnnotations((xs) => xs.filter((x) => x.id !== id))
    try { await api.removeAnnotation(docId, id) } catch (e) { onError((e as Error).message) }
  }
  return { annotations, active, setActive, add, update, remove }
}
