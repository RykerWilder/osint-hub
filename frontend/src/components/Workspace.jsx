import { useState } from 'react'
import Icon from './Icon.jsx'
import StatusGlyph from './StatusGlyph.jsx'
import ToolPane from './ToolPane.jsx'
import { reportUrl } from '../api.js'
import { TYPE_ICON } from '../lib/types.js'
import { FINISHED, JOB_STATUS, fmtClock, scanElapsed } from '../lib/format.js'
import { useNow } from '../hooks.js'

/**
 * Results of a search: a sidebar with the state of the search and the list of tools,
 * and, next to it, the results of the tool that is selected.
 * On narrow screens the sidebar stacks above and the tool list scrolls sideways.
 */
export default function Workspace({ scan, typeLabel, onCancel }) {
  const [tab, setTab] = useState(null)

  const running = scan.status === 'running'
  const now = useNow(running) + (scan.skew || 0)
  const total = scan.jobs.length
  const doneCount = scan.jobs.filter((j) => FINISHED.has(j.status)).length
  const count = scan.jobs.reduce((n, j) => n + j.findings.length, 0)
  const status = JOB_STATUS[scan.status] || JOB_STATUS.done

  const active = scan.jobs.some((j) => j.id === tab) ? tab : scan.jobs[0]?.id
  const job = scan.jobs.find((j) => j.id === active)
  const tabId = (id) => `tab-${id}`

  const onKeyDown = (e) => {
    const ids = scan.jobs.map((j) => j.id)
    const i = ids.indexOf(active)
    let next = null
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') next = ids[(i + 1) % ids.length]
    else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') next = ids[(i - 1 + ids.length) % ids.length]
    else if (e.key === 'Home') next = ids[0]
    else if (e.key === 'End') next = ids[ids.length - 1]
    if (next == null) return
    e.preventDefault()
    setTab(next)
    document.getElementById(tabId(next))?.focus()
  }

  return (
    <div className="grid lg:h-full lg:grid-cols-[300px_minmax(0,1fr)]">
      <aside className="border-b border-line bg-surface lg:overflow-y-auto lg:border-b-0 lg:border-r">
        <div className="p-4 sm:p-5">
          <p className="flex items-center gap-2 text-[13px] text-ink-2">
            <Icon name={TYPE_ICON[scan.type] || 'search'} size={14} className="shrink-0" />
            {typeLabel}
          </p>
          <h2 className="mt-1 break-all font-mono text-[19px] font-medium leading-snug">{scan.target}</h2>

          <p className="mt-3 flex items-center gap-2 text-[14px]">
            <StatusGlyph status={scan.status} size={14} />
            <span className={status.tone}>{status.label}</span>
            <span className="font-mono text-[13px] tabular-nums text-ink-2">{fmtClock(scanElapsed(scan, now))}</span>
          </p>

          <div className="mt-3 flex gap-1" role="progressbar" aria-label="Tool progress" aria-valuemin={0} aria-valuemax={total} aria-valuenow={doneCount}>
            {scan.jobs.map((j) => (
              <span key={j.id} title={`${j.tool_name}: ${(JOB_STATUS[j.status] || JOB_STATUS.queued).label}`} className="seg" data-status={j.status} />
            ))}
          </div>
          <p className="mt-2 text-[13px] text-ink-3">
            {doneCount} of {total} tools finished, {count} {count === 1 ? 'result' : 'results'}
          </p>
          {scan.status === 'cancelled' && <p className="mt-1 text-[13px] text-ink-3">Stopped. The results collected so far are saved.</p>}

          <div className="mt-4 flex flex-wrap gap-2">
            {running && (
              <button type="button" className="btn btn-danger" onClick={onCancel}>
                <Icon name="stop" size={13} />
                Stop
              </button>
            )}
            <a href={reportUrl(scan.id)} download className="btn">
              <Icon name="download" size={15} />
              Download report .txt
            </a>
          </div>
        </div>

        <nav className="border-t border-line px-2 py-2 sm:px-3" aria-label="Tools">
          <div role="tablist" aria-label="Tools" className="flex gap-1 overflow-x-auto lg:flex-col lg:overflow-visible" onKeyDown={onKeyDown}>
            {scan.jobs.map((j) => (
              <button
                key={j.id}
                type="button"
                role="tab"
                id={tabId(j.id)}
                aria-selected={active === j.id}
                aria-controls="panel"
                tabIndex={active === j.id ? 0 : -1}
                className="navitem lg:w-full"
                onClick={() => setTab(j.id)}
              >
                <StatusGlyph status={j.status} size={14} />
                <span className="min-w-0 flex-1 truncate">{j.tool_name}</span>
                <span className="count">{j.findings.length}</span>
              </button>
            ))}
          </div>
        </nav>
      </aside>

      <section id="panel" role="tabpanel" aria-labelledby={active ? tabId(active) : undefined} className="min-w-0 lg:overflow-y-auto">
        <div className="max-w-[1000px] p-4 sm:p-6">{job && <ToolPane key={job.id} scanId={scan.id} job={job} now={now} />}</div>
      </section>
    </div>
  )
}
