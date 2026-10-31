import { useState } from 'react'
import type { Translation } from '../../api'
import { CopyIcon, PencilIcon } from '../../ui/icons'
import EditMenu, { type EditActions } from './EditMenu'
import Romanise from './Romanise'

export function Original({ text, title = 'Original' }: { text: string; title?: string }) {
  return (
    <div className="space-y-1">
      <h3 className="kicker">{title}</h3>
      <p className="text-sm text-muted whitespace-pre-wrap border-l-2 border-line pl-3 max-h-48 overflow-auto">{text}</p>
    </div>
  )
}

/** One language's translation: the text, Copy, Romanise; optionally "show on page" and the edit tools. */
export function TranslationCard({ lang, name, rtl, text, error, shown, onShow, edit, actions, translation, onTranslate, busy }: {
  lang: string; name: string; rtl: boolean; text: string; error?: string | null
  shown?: boolean; onShow?: () => void  // which translation the pages show
  edit?: boolean; actions?: EditActions; translation?: Translation
  onTranslate?: () => void; busy?: boolean  // not translated into this language yet
}) {
  const [editing, setEditing] = useState(false)
  return (
    <div className={`pt-3 space-y-2 border-t ${shown ? 'border-t-2 border-ink' : 'border-line'}`}>
      <div className="flex items-center gap-2">
        <span className="kicker text-ink">{name}</span>
        {onShow && (text
          ? <button role="radio" aria-checked={!!shown} onClick={onShow} className={`chip ml-auto ${shown ? 'text-accent-strong' : 'text-muted'}`}>
              <span className={`size-2 rounded-full border ${shown ? 'bg-accent border-accent' : 'border-black/30'}`} />{shown ? 'Shown' : 'Show'}
            </button>
          : null)}
      </div>
      {error && <p className="text-xs text-rose-700">{error}</p>}
      {text
        ? <p className="text-[15px] leading-relaxed text-ink whitespace-pre-wrap break-words" lang={lang} dir={rtl ? 'rtl' : undefined}>{text}</p>
        : onTranslate && <button onClick={onTranslate} disabled={busy} className="btn btn-sm">{busy ? 'Translating…' : 'Translate'}</button>}
      {text && (
        <div className="flex items-center gap-1 -ml-2">
          <button onClick={() => navigator.clipboard.writeText(text)} title="Copy" aria-label="Copy" className="btn btn-sm btn-ghost btn-icon"><CopyIcon /></button>
          {edit && actions && translation && (
            <button onClick={() => setEditing(!editing)} aria-pressed={editing} title="Edit" aria-label="Edit" className="btn btn-sm btn-ghost btn-icon"><PencilIcon /></button>
          )}
          <div className="ml-auto"><Romanise key={`${lang}:${text}`} text={text} lang={lang} /></div>
        </div>
      )}
      {editing && actions && translation && <EditMenu t={translation} actions={actions} />}
    </div>
  )
}
