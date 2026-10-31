import { useEffect } from 'react'

export type MenuItem = { label: string; run: () => void; danger?: boolean }

/** A right-click menu at a point; any click elsewhere, Escape or a scroll closes it. */
export default function ContextMenu({ x, y, items, onClose }: { x: number; y: number; items: MenuItem[]; onClose: () => void }) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('mousedown', onClose)
    window.addEventListener('keydown', esc)
    window.addEventListener('scroll', onClose, true)
    return () => { window.removeEventListener('mousedown', onClose); window.removeEventListener('keydown', esc); window.removeEventListener('scroll', onClose, true) }
  }, [onClose])
  return (
    <div role="menu" className="popover fixed z-50 py-1 min-w-40" style={{ left: x, top: y }} onMouseDown={(e) => e.stopPropagation()}>
      {items.map((i) => (
        <button key={i.label} role="menuitem" onClick={() => { onClose(); i.run() }}
          className={`block w-full text-left px-3 py-1.5 text-sm hover:bg-well ${i.danger ? 'text-rose-700' : 'text-ink'}`}>{i.label}</button>
      ))}
    </div>
  )
}
