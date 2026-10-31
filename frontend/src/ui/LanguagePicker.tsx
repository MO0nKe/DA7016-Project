import { useEffect, useId, useRef, useState } from 'react'
import { CheckIcon, ChevronDownIcon } from './icons'

/** `disabled`: why it can't be chosen ("Original language"); shown greyed with the reason. */
export type LanguageOption = { code: string; name: string; disabled?: string }

type Props = {
  options: LanguageOption[]; value: string | null; onChange: (code: string) => void
  label: string  // accessible name
  placeholder?: React.ReactNode  // the button's text when nothing is chosen ("+ Add")
  variant?: 'field' | 'chip'; className?: string; disabled?: boolean
}

/** The app's dropdown (a native select's menu is drawn by the OS): languages, and also zoom and folders, whose
 *  options are given as `code` (the value) and `name`. Its list is a popover. Keyboard: arrows, Home/End, Enter,
 *  Escape, and typing a letter jumps to the first option starting with it. */
export default function LanguagePicker({ options, value, onChange, label, placeholder, variant = 'field', className = '', disabled }: Props) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [at, setAt] = useState({ left: 0, top: 0, width: 0, up: false })
  const button = useRef<HTMLButtonElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const id = useId()
  const chosen = options.find((o) => o.code === value)

  const show = () => {
    const r = button.current!.getBoundingClientRect()
    const up = r.bottom + 280 > window.innerHeight && r.top > window.innerHeight - r.bottom
    const width = Math.max(r.width, 240)
    setAt({ left: Math.max(8, Math.min(r.left, window.innerWidth - width - 8)), top: up ? r.top - 4 : r.bottom + 4, width, up })
    const i = options.findIndex((o) => o.code === value)
    setActive(i >= 0 ? i : options.findIndex((o) => !o.disabled))
    setOpen(true)
  }
  const close = (refocus = true) => { setOpen(false); if (refocus) button.current?.focus() }
  const choose = (i: number) => { const o = options[i]; if (!o || o.disabled) return; onChange(o.code); close() }
  const move = (from: number, step: number) => {
    for (let i = from + step, n = 0; n < options.length; i += step, n++) {
      const j = (i + options.length) % options.length
      if (!options[j].disabled) return setActive(j)
    }
  }

  useEffect(() => {
    if (!open) return
    list.current?.focus()
    const away = (e: MouseEvent) => {
      if (!list.current?.contains(e.target as Node) && !button.current?.contains(e.target as Node)) close(false)
    }
    const shut = () => close(false)
    // The list is fixed, so scrolling the page under it would leave it behind; scrolling the list itself is fine.
    const scrolled = (e: Event) => { if (!list.current?.contains(e.target as Node)) shut() }
    document.addEventListener('mousedown', away)
    window.addEventListener('resize', shut)
    window.addEventListener('scroll', scrolled, true)
    return () => { document.removeEventListener('mousedown', away); window.removeEventListener('resize', shut); window.removeEventListener('scroll', scrolled, true) }
  }, [open])
  useEffect(() => { if (open) document.getElementById(`${id}-${active}`)?.scrollIntoView({ block: 'nearest' }) }, [open, active, id])

  const onListKey = (e: React.KeyboardEvent) => {
    e.stopPropagation()  // Escape closes the list, not the dialog around it
    if (e.key === 'ArrowDown') { e.preventDefault(); move(active, 1) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); move(active, -1) }
    else if (e.key === 'Home') { e.preventDefault(); move(-1, 1) }
    else if (e.key === 'End') { e.preventDefault(); move(options.length, -1) }
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(active) }
    else if (e.key === 'Escape' || e.key === 'Tab') { e.preventDefault(); close() }
    else if (e.key.length === 1) {
      const k = e.key.toLowerCase()
      const i = options.findIndex((o, n) => n > active && !o.disabled && o.name.toLowerCase().startsWith(k))
      const j = i >= 0 ? i : options.findIndex((o) => !o.disabled && o.name.toLowerCase().startsWith(k))
      if (j >= 0) setActive(j)
    }
  }

  return (
    <>
      <button ref={button} type="button" disabled={disabled} aria-label={label} aria-haspopup="listbox" aria-expanded={open}
        onClick={() => (open ? close() : show())}
        onKeyDown={(e) => { if (!open && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) { e.preventDefault(); show() } }}
        className={`${variant === 'chip' ? 'chip cursor-pointer hover:bg-well disabled:cursor-not-allowed disabled:text-faint'
          : 'field flex items-center gap-2 text-left disabled:text-faint'} ${className}`}>
        <span className="flex-1 truncate">{chosen?.name ?? placeholder}</span>
        {variant === 'field' && <ChevronDownIcon className="shrink-0 text-muted" />}
      </button>
      {open && (
        <ul ref={list} role="listbox" tabIndex={-1} aria-label={label} aria-activedescendant={`${id}-${active}`} onKeyDown={onListKey}
          className="popover fixed z-[60] max-h-72 overflow-auto overscroll-contain p-1.5 outline-none [scrollbar-width:thin] [scrollbar-color:rgb(0_0_0/0.2)_transparent]"
          style={{ left: at.left, width: at.width, ...(at.up ? { bottom: window.innerHeight - at.top } : { top: at.top }) }}>
          {options.map((o, i) => (
            <li key={o.code} id={`${id}-${i}`} role="option" aria-selected={o.code === value} aria-disabled={!!o.disabled}
              onMouseEnter={() => !o.disabled && setActive(i)} onClick={() => choose(i)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-xl text-sm
                ${o.disabled ? 'text-faint cursor-not-allowed' : 'text-ink cursor-pointer'}
                ${i === active && !o.disabled ? 'bg-black/[0.06]' : ''} ${o.code === value ? 'font-medium' : ''}`}>
              <span className="flex-1 truncate">{o.name}</span>
              {o.disabled && <span className="text-xs">{o.disabled}</span>}
              {o.code === value && <CheckIcon className="text-accent shrink-0" />}
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
