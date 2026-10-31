import type { DocSummary } from '../api'

/** A document's title as listed: its file name without .pdf. */
export const title = (d: DocSummary) => d.filename.replace(/\.pdf$/i, '')
/** A date as the library shows it ("30 Oct 2026"). */
export const day = (t: number | string) => new Date(t).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
