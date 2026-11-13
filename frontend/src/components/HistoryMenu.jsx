import { useEffect, useRef, useState } from 'react'
import Icon from './Icon.jsx'
import { TYPE_ICON } from '../lib/types.js'
import { fmtDate } from '../lib/format.js'

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'

export default function HistoryMenu({ scans, activeId, typeLabels, onOpen, onDelete }) {
  const [open, setOpen] = useState(false)
  const [confirm, setConfirm] = useState(null)
  const panel = useRef(null)
  const trigger = useRef(null)

  const close = () => {
    setOpen(false)
    setConfirm(null)
    trigger.current?.focus()
  }

  useEffect(() => {
    if (!open) return undefined
    panel.current?.querySelector('button')?.focus()
    const onKey = (e) => {
      if (e.key === 'Escape') {
        close()
      } else if (e.key === 'Tab' && panel.current) {
        // keep the focus inside the panel while it is open
        const items = [...panel.current.querySelectorAll(FOCUSABLE)]
        if (!items.length) return
        const first = items[0]
        const last = items[items.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  return (
    <>
      <button ref={trigger} type="button" className="btn" aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}>
        <Icon name="history" size={15} />
        History
        <span className="count">{scans.length}</span>
      </button>

      {open && (
        <div className="fixed inset-0 z-40">
          <button type="button" tabIndex={-1} aria-label="Close history" className="absolute inset-0 cursor-default bg-base/75 backdrop-blur-[2px]" onClick={close} />
          <aside
            ref={panel}
            role="dialog"
            aria-modal="true"
            aria-label="Search history"
            className="absolute inset-y-0 right-0 flex w-[min(94vw,420px)] animate-drawer flex-col border-l border-line-strong bg-surface"
          >
            <div className="flex items-center justify-between border-b border-line px-5 py-3">
              <h2 className="text-[16px] font-semibold">History</h2>
              <button type="button" className="rounded-ctl p-1.5 text-ink-3 hover:bg-raised hover:text-ink" aria-label="Close history" onClick={close}>
                <Icon name="x" size={18} />
              </button>
            </div>
            {scans.length === 0 ? (
              <p className="px-5 py-6 text-sm text-ink-2">Finished searches will show up here, with their results.</p>
            ) : (
              <ul className="flex-1 overflow-y-auto py-2">
                {scans.map((s) => (
                  <li key={s.id} className="flex items-center gap-1 px-2">
                    <button
                      type="button"
                      className={`flex min-w-0 flex-1 items-center gap-3 rounded-ctl px-3 py-2.5 text-left hover:bg-raised ${s.id === activeId ? 'bg-raised shadow-[inset_2px_0_0_var(--color-signal)]' : ''}`}
                      onClick={() => {
                        onOpen(s.id)
                        close()
                      }}
                    >
                      <Icon name={TYPE_ICON[s.type] || 'search'} size={16} className="shrink-0 text-ink-2" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-mono text-[13.5px]" title={typeLabels[s.type]}>
                          {s.target}
                        </span>
                        <span className="block text-xs text-ink-3">
                          {fmtDate(s.created_at)}, {s.status === 'running' ? 'running' : `${s.findings_count} ${s.findings_count === 1 ? 'result' : 'results'}`}
                        </span>
                      </span>
                    </button>
                    {confirm === s.id ? (
                      <button
                        type="button"
                        className="btn btn-danger border-bad px-2 py-1 text-xs"
                        onClick={() => {
                          setConfirm(null)
                          onDelete(s.id)
                        }}
                        onBlur={() => setConfirm(null)}
                        autoFocus
                      >
                        Delete
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="rounded-ctl p-2 text-ink-3 hover:bg-raised hover:text-bad"
                        aria-label={`Delete search ${s.target}`}
                        onClick={() => setConfirm(s.id)}
                      >
                        <Icon name="trash" size={15} />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </aside>
        </div>
      )}
    </>
  )
}
