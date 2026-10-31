import type { Annotation } from '../../api'

const PX_PER_PT = 4 / 3

/** The highlight layer of one view (the original or a language): see-through colour at the highlights' page
 *  positions, drawn above the page, and a pin on each note and commented highlight that opens it. */
export default function Highlights({ annotations, activeId, onOpen }: { annotations: Annotation[]; activeId: string | null; onOpen: (id: string) => void }) {
  return (
    // No z-index on the wrapper: that would isolate it, and the multiply blend would no longer reach the
    // page below. Each highlight is raised instead.
    <div className="absolute inset-0 pointer-events-none">
      {annotations.flatMap((a) => a.kind === 'highlight' ? a.rects.map((r, i) => (
        <div key={`${a.id}-${i}`} className={`absolute z-[6] mix-blend-multiply ${a.id === activeId ? 'ring-2 ring-accent' : ''}`}
          style={{ left: r[0] * PX_PER_PT, top: r[1] * PX_PER_PT, width: (r[2] - r[0]) * PX_PER_PT,
                   height: (r[3] - r[1]) * PX_PER_PT, background: a.color, opacity: 0.55 }} />
      )) : [])}
      {annotations.filter((a) => a.kind === 'note' || (a.kind === 'highlight' && a.comment)).map((a) => {
        const r = a.kind === 'note' ? a.rects[0] : a.rects[a.rects.length - 1]
        return (
          <button key={`${a.id}-pin`} onClick={(e) => { e.stopPropagation(); onOpen(a.id) }} title={a.comment}
            className="absolute z-10 pointer-events-auto size-5 grid place-items-center rounded-full text-[11px] shadow-raised-sm border border-white"
            style={{ left: (a.kind === 'note' ? r[0] : r[2]) * PX_PER_PT, top: r[1] * PX_PER_PT - 10, background: a.color }}>✎</button>
        )
      })}
    </div>
  )
}
