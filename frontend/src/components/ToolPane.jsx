import { useState } from 'react'
import Icon from './Icon.jsx'
import StatusGlyph from './StatusGlyph.jsx'
import Findings from './Findings.jsx'
import Terminal from './Terminal.jsx'
import { reportUrl } from '../api.js'
import { JOB_STATUS, fmtDuration, jobElapsed } from '../lib/format.js'

/** Content of one tool tab: status line, results, and the raw log on demand. */
export default function ToolPane({ scanId, job, now }) {
  const [showLog, setShowLog] = useState(false)
  const count = job.findings.length
  const status = JOB_STATUS[job.status] || JOB_STATUS.queued
  const elapsed = jobElapsed(job, now)
  const running = job.status === 'running'
  const finished = !['queued', 'running'].includes(job.status)

  const detail = running && elapsed != null ? `${status.label}, ${fmtDuration(elapsed)}` : job.summary || status.label

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
        <div className="min-w-0">
          <h3 className="text-[20px] font-semibold leading-tight">{job.tool_name}</h3>
          <p className="mt-1.5 flex min-w-0 items-center gap-2.5 text-[14px]">
            <StatusGlyph status={job.status} />
            <span className={status.tone}>{detail}</span>
            {finished && elapsed != null && job.summary && <span className="font-mono text-[12.5px] text-ink-3">{fmtDuration(elapsed)}</span>}
          </p>
        </div>
        <a href={reportUrl(scanId, job.id)} download className="btn" aria-label={`Download the ${job.tool_name} report as a text file`}>
          <Icon name="download" size={15} />
          Download .txt
        </a>
      </div>

      {job.error && (
        <p className="mt-4 flex items-start gap-2 text-sm text-bad">
          <Icon name="alert" size={15} className="mt-0.5 shrink-0" />
          {job.error}
        </p>
      )}

      <div className="mt-5">
        {count > 0 && <Findings findings={job.findings} />}
        {count === 0 && running && <p className="text-sm text-ink-3">Waiting for the first results. Some tools only show everything at the end.</p>}
        {count === 0 && job.status === 'queued' && <p className="text-sm text-ink-3">Queued: it starts as soon as there is room.</p>}
        {count === 0 && finished && !job.error && <p className="text-sm text-ink-3">This tool found nothing.</p>}
      </div>

      {job.logs.length > 0 && (
        <div className="mt-6 border-t border-line pt-3">
          <button
            type="button"
            className="inline-flex items-center gap-2 text-[13px] text-ink-2 hover:text-signal"
            aria-expanded={showLog}
            onClick={() => setShowLog((v) => !v)}
          >
            <Icon name="terminal" size={14} />
            {showLog ? 'Hide log' : `Show log (${job.logs.length} ${job.logs.length === 1 ? 'line' : 'lines'})`}
          </button>
          {showLog && <Terminal lines={job.logs} running={running} />}
        </div>
      )}
    </div>
  )
}
