// How API values are shown to the reader.

import type { Job } from '../api'

/** The warning for a document in a language the app doesn't translate from, or null. */
export const unsupportedNotice = (d: { unsupported_lang: string | null }) => d.unsupported_lang &&
  `This document seems to be in ${d.unsupported_lang === 'an unsupported language' ? 'a language the app doesn\'t support' : `${d.unsupported_lang}, which the app doesn't support`}. Translations from it will be unreliable.`

/** How far a translation job is, 0–100. */
export const percent = (j: Job) => (j.total ? Math.floor((100 * j.done) / j.total) : 0)
/** The estimated time for a translation, as shown to the reader. */
export const eta = (minutes: number | null) => (minutes && minutes >= 1.5 ? `About ${Math.round(minutes)} minutes` : 'Under a minute or two')
