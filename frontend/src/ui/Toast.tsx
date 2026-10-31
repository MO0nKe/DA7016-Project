import { CloseIcon } from './icons'

/** A message in the bottom-right corner after background work, with an optional action. */
export default function Toast({ text, action, onDismiss }: {
  text: string; action?: { label: string; run: () => void }; onDismiss: () => void
}) {
  return (
    <div className="toast" role="status">
      <span>{text}</span>
      {action && <button className="btn btn-sm btn-primary" onClick={action.run}>{action.label}</button>}
      <button className="btn btn-sm btn-ghost btn-icon" aria-label="Dismiss" onClick={onDismiss}><CloseIcon /></button>
    </div>
  )
}
