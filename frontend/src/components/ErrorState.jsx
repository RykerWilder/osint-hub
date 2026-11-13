import Icon from './Icon.jsx'

/** A problem the person can act on: what happened, and a button to try again. */
export default function ErrorState({ title, message, actionLabel, onAction }) {
  return (
    <div role="alert" className="max-w-[64ch]">
      <h2 className="flex items-center gap-2 text-[18px] font-semibold text-bad">
        <Icon name="alert" size={18} className="shrink-0" />
        {title}
      </h2>
      <p className="mt-1.5 text-[14.5px] text-ink-2">{message}</p>
      <button type="button" className="btn mt-4" onClick={onAction}>
        {actionLabel}
      </button>
    </div>
  )
}
