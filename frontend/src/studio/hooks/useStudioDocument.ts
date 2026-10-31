import { useCallback, useEffect, useState } from 'react'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import { api, type BlockChange, type Doc } from '../../api'
import { getDocument } from '../../lib/pdf'
import type { ShownChange } from '../pages/PageView'

/** The open document: its model (reloaded after jobs), its PDF for the Original view, block changes swapped into the
 *  pages, and OCR of scanned pages. `version` goes up whenever the language views must be drawn again. */
export function useStudioDocument(docId: string) {
  const [doc, setDoc] = useState<Doc | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null)
  const [version, setVersion] = useState(0)
  const [change, setChange] = useState<ShownChange | null>(null)
  const [ocrBusy, setOcrBusy] = useState(false)

  const reload = useCallback(() => api.document(docId).then(setDoc).catch((e) => setError(e.message)), [docId])
  useEffect(() => { reload() }, [reload])
  useEffect(() => {
    let live = true
    const task = getDocument({ url: `/api/documents/${docId}/source.pdf` })
    task.promise.then(setPdf).catch((e) => { if (live) setError(`Could not open the PDF: ${e.message}`) })
    return () => { live = false; task.destroy() }  // destroying rejects the promise with "Loading aborted"
  }, [docId])

  const redraw = () => setVersion((v) => v + 1)

  /** A section's translation was edited: the document updates, and the page swaps the section in. */
  const applyChange = (c: BlockChange, lang: string) => {
    setDoc((d) => d && { ...d, pages: d.pages.map((p) => p.index !== c.page ? p
      : { ...p, blocks: p.blocks.map((b) => (b.id === c.block.id ? c.block : b)) }) })
    setChange({ ...c, lang })
  }

  const runOcr = async (index: number) => {
    setOcrBusy(true)
    try { setDoc(await api.ocr(docId, [index])); redraw() }
    catch (e) { setError((e as Error).message) }
    finally { setOcrBusy(false) }
  }

  return { doc, error, setError, pdf, reload, version, redraw, change, applyChange, ocrBusy, runOcr }
}
