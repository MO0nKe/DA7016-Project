// Every backend call. Requests go to /api, which Vite proxies to the FastAPI backend in development.

import type { Annotation, BlockChange, Definition, Doc, DocSummary, Estimate, Folder, GlossaryMiss, Health, Job, Language, LibraryState, OutlineItem, Snippet, Term } from './types'

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api${path}`, init)
  if (!r.ok) {
    let detail = r.statusText
    try { detail = (await r.json()).detail ?? detail } catch { /* not JSON */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  const type = r.headers.get('content-type') ?? ''
  return (type.includes('application/json') ? r.json() : r.text()) as Promise<T>
}
const json = (method: string, body: unknown): RequestInit =>
  ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const q = (params: Record<string, string | number | boolean | undefined | null>) => {
  const s = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') s.set(k, String(v))
  const str = s.toString()
  return str ? `?${str}` : ''
}

export const api = {
  health: () => call<Health>('/health'),
  languages: () => call<Language[]>('/languages'),
  documents: () => call<DocSummary[]>('/documents'),
  document: (id: string) => call<Doc>(`/documents/${id}`),
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return call<DocSummary>('/documents', { method: 'POST', body: form })
  },
  remove: (id: string) => call(`/documents/${id}`, { method: 'DELETE' }),
  ocr: (id: string, pages: number[]) => call<Doc>(`/documents/${id}/ocr`, json('POST', { pages })),
  estimate: (id: string, langs: string[], pages?: number[], blocks?: string[], includeFigures = false) =>
    call<Estimate>(`/documents/${id}/estimate${q({ langs: langs.join(','), pages: pages?.join(','), blocks: blocks?.join(','), include_figures: includeFigures || undefined })}`),
  translate: (id: string, langs: string[], pages?: number[], blockIds?: string[], includeFigures = false, force = false) =>
    call<Job>(`/documents/${id}/translate`, json('POST', { langs, pages: pages ?? null, block_ids: blockIds ?? null, include_figures: includeFigures, force })),
  /** Every section's translation into this language goes, edits included. */
  removeTranslation: (id: string, lang: string) => call(`/documents/${id}/translations/${lang}`, { method: 'DELETE' }),
  translateText: (text: string, langs: string[]) => call<Snippet[]>('/translate-text', json('POST', { text, langs })),
  job: (id: string) => call<Job>(`/jobs/${id}`),
  documentJob: (id: string) => call<Job | null>(`/documents/${id}/job`),
  romaniseText: (text: string, lang: string) =>
    call<{ text: string; truncated: boolean }>('/transliterate-text', json('POST', { text, lang })),
  edit: (id: string, block: string, lang: string, instruction: string, regenerate = false) =>
    call<BlockChange>(`/documents/${id}/blocks/${block}/edit`, json('POST', { lang, instruction, regenerate })),
  revert: (id: string, block: string, lang: string) =>
    call<BlockChange>(`/documents/${id}/blocks/${block}/revert`, json('POST', { lang })),
  annotations: (id: string) => call<Annotation[]>(`/documents/${id}/annotations`),
  addAnnotation: (id: string, a: Partial<Annotation>) => call<Annotation>(`/documents/${id}/annotations`, json('POST', a)),
  updateAnnotation: (id: string, a: Annotation) => call<Annotation>(`/documents/${id}/annotations/${a.id}`, json('PUT', a)),
  removeAnnotation: (id: string, annId: string) => call(`/documents/${id}/annotations/${annId}`, { method: 'DELETE' }),
  glossary: () => call<Term[]>('/glossary'),
  addTerm: (t: Omit<Term, 'id'>) => call<Term>('/glossary', json('POST', t)),
  removeTerm: (id: string) => call(`/glossary/${id}`, { method: 'DELETE' }),
  glossaryCheck: (id: string, lang: string) => call<GlossaryMiss[]>(`/documents/${id}/glossary-check?lang=${lang}`),
  library: () => call<LibraryState>('/library'),
  addFolder: (name: string, parent: string | null) => call<Folder>('/folders', json('POST', { name, parent })),
  renameFolder: (id: string, name: string) => call<Folder>(`/folders/${id}`, json('PATCH', { name })),
  moveFolder: (id: string, parent: string | null) => call<Folder>(`/folders/${id}`, json('PATCH', { parent, move: true })),
  removeFolder: (id: string) => call(`/folders/${id}`, { method: 'DELETE' }),
  placeDocument: (id: string, folderId: string | null) => call(`/documents/${id}/folder`, json('PUT', { folder_id: folderId })),
  define: (word: string) => call<Definition>(`/define?word=${encodeURIComponent(word)}`),
  outline: (id: string) => call<OutlineItem[]>(`/documents/${id}/outline`),
  pageImage: (id: string, page: number) => `/api/documents/${id}/pages/${page}/original.png`,
  /** One page drawn in a language (null: the original text), over the page with its text removed. */
  renderPage: (id: string, page: number, lang: string | null) => call<string>(`/documents/${id}/pages/${page}/render${q({ lang })}`),
}
