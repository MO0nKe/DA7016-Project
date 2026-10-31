// The document model and API payloads, mirroring backend/core/models.py and the routers in backend/api/.
// Keep them in sync by hand when the backend changes.

export type Style = {
  font_size: number | null; bold: boolean; italic: boolean; color: string | null
  background: string | null; align: string; family: string; line_height: number | null; font: string | null
  mark_color: string | null; hanging: boolean
}
export type Cell = { row: number; col: number; bbox: number[]; text: string; header: boolean; style: Style | null }
export type Edit = { instruction: string; before: string; after: string; model: string; ts: string; cost_usd: number; style_before: Partial<Style> }
export type Translation = {
  text: string; rich: string | null; html: string | null; cells: string[] | null
  status: 'done' | 'truncated' | 'error' | 'edited'; error: string | null; edits: Edit[]
  style: Partial<Style>  // a reviewer's look changes for this translation
  lang: string | null  // the language it's written in, when an edit asked for another one
}
export type Block = {
  id: string; order: number; label: string; type: string; bbox: number[]; text: string
  rich: string | null; html: string | null; cells: Cell[] | null; style: Style; source: 'text_layer' | 'ocr'
  translatable: boolean; in_figure: boolean; room: number; maths: Maths[]
  continues: string | null
  translations: Record<string, Translation>
}
// An inline formula drawn from a crop of the original page (backend Maths).
export type Maths = { text: string; bbox: number[]; descent: number; image: string }
export type Page = {
  index: number; width: number; height: number; source: 'text_layer' | 'ocr' | 'pending_ocr'
  dpi: number; image: string; background: string; text_quality: number; blocks: Block[]; figure_text_kept: boolean
  review: Record<string, unknown> | null  // structure review fixes applied (backend/pipeline/structure.py)
  obstacles: number[][]  // pictures and line art that text must not run into
}
export type Doc = {
  id: string; filename: string; created: string; pages: Page[]
  source_lang: string | null; unsupported_lang: string | null  // detected; see DocSummary
}
export type DocSummary = {
  id: string; filename: string; created: string; page_count: number; pending_ocr: number[]; languages: string[]
  // Detected from the text: a supported language's code, or (unsupported_lang) the name of one the app doesn't
  // support ("Spanish"). Both null when there's no text yet, or a shared script's words don't settle it.
  source_lang: string | null; unsupported_lang: string | null
}
export type Language = { code: string; name: string; rtl: boolean }
export type Job = {
  id: string; kind: string; doc_id: string; langs: string[]; status: 'running' | 'done' | 'error'
  total: number; done: number; failed: number; error: string | null
  phase: 'layout' | null  // a translation waiting for the structure review ('structure' jobs run on upload)
}
export type LangEstimate = { blocks: number; calls: number; cached_calls: number; chars: number; est_output_tokens: number }
export type Estimate = {
  languages: Record<string, LangEstimate>; blocks: number; figure_blocks: number; calls: number; uncached_calls: number
  est_output_tokens: number; minutes: number | null
}
export type Snippet = { lang: string; text: string; truncated: boolean; cached: boolean; error: string | null }
export type Health = { status: string; bodhan: string; openrouter: string; spends_credits: boolean }
export type OutlineItem = { level: number; title: string; page: number; top: number; block_id: string | null }
export type Annotation = {
  id: string; kind: 'highlight' | 'note' | 'text'; page: number; rects: number[][]; color: string
  quote: string; comment: string; font_size: number; created: string
  lang: string  // the view it was made on: '' the original, else a language
}
export type Term = { id: string; source: string; lang: string; target: string }
export type GlossaryMiss = { block_id: string; page: number; text: string; missing: Term[] }
export type Folder = { id: string; name: string; parent: string | null }
export type LibraryState = { folders: Folder[]; placement: Record<string, string> }
export type Definition = {
  word: string; lemma: string
  senses: { pos: string; definition: string; examples: string[]; synonyms: string[] }[]
}
export type BlockChange = { block: Block; page: number; lang: string; html: string }  // lang: where the change landed
