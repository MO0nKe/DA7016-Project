/** Each language as the first letter of its own name, written in its own script (हि Hindi, म Marathi, த Tamil): the
 *  chips are distinct for languages that share a script, and still show which script each one is written in. */
const LETTERS: Record<string, string> = {
  en: 'En', hi: 'हि', bn: 'বা', ta: 'த', te: 'తె', kn: 'ಕ', ml: 'മ', mr: 'म', gu: 'ગુ', pa: 'ਪੰ', or: 'ଓ', as: 'অ',
  ur: 'ا', ne: 'ने', sa: 'सं', kok: 'को', mai: 'मै', doi: 'डो', brx: 'ब', sat: 'ᱥ', ks: 'ک', 'ks-Deva': 'क',
  mni: 'ꯃ', 'mni-Beng': 'ম', sd: 'सि', 'sd-Arab': 'س',
}

export const scriptLetter = (code: string) => LETTERS[code] ?? code.slice(0, 2)
