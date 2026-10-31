// Per-browser reading memory: where each document was left, and which were opened recently.

export type Position = { scroll: number; page: number; zoom: number; at: number }

const KEY = 'reading'
const MAX_RECENT = 12

function all(): Record<string, Position> {
  try { return JSON.parse(localStorage.getItem(KEY) ?? '{}') } catch { return {} }
}

export const positionOf = (docId: string): Position | undefined => all()[docId]

export function savePosition(docId: string, p: Omit<Position, 'at'>) {
  const items = { ...all(), [docId]: { ...p, at: Date.now() } }
  // Keep only the most recent documents so this never grows without bound.
  const kept = Object.entries(items).sort((a, b) => b[1].at - a[1].at).slice(0, MAX_RECENT)
  localStorage.setItem(KEY, JSON.stringify(Object.fromEntries(kept)))
}

export const recent = (): [string, Position][] => Object.entries(all()).sort((a, b) => b[1].at - a[1].at)

export const forget = (docId: string) => {
  const items = all()
  delete items[docId]
  localStorage.setItem(KEY, JSON.stringify(items))
  // Its tabs too (useLanguageViews): the same PDF uploaded again gets the same id.
  localStorage.removeItem(`langs:${docId}`)
}
