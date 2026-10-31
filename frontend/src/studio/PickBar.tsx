import { FIGURE_NOTICE } from '../panels/translations/TranslationPanel'
import { TranslateIcon } from '../ui/icons'

/** Shown when Shift is released with sections picked: translate them into the language view shown. */
export default function PickBar({ count, langName, at, figures, onTranslate, onCancel }: {
  count: number; langName: string; at: { x: number; y: number }; figures: number
  onTranslate: () => void; onCancel: () => void
}) {
  return (
    <div data-pick-bar style={{ left: at.x, top: at.y + 16 }} className="fixed z-50 -translate-x-1/2 popover p-1.5 flex items-center gap-1">
      <button onClick={onTranslate} className="btn btn-sm btn-primary">
        <TranslateIcon />Translate {count} section{count === 1 ? '' : 's'} into {langName}
      </button>
      <button onClick={onCancel} className="btn btn-sm btn-ghost">Cancel</button>
      {figures > 0 && <span className="max-w-56 px-1 text-xs text-amber-800">{FIGURE_NOTICE}</span>}
    </div>
  )
}
