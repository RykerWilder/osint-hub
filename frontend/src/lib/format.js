export function fmtDuration(ms) {
  if (ms == null || Number.isNaN(ms)) return ''
  const s = Math.max(0, Math.round(ms / 1000))
  if (s < 60) return `${s} s`
  return `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, '0')} s`
}

// How long a tool has been running. `now` is already corrected for the server clock offset.
export function jobElapsed(job, now) {
  if (!job.started_at) return null
  const end = job.finished_at ? Date.parse(job.finished_at) : now
  return end - Date.parse(job.started_at)
}

export function scanElapsed(scan, now) {
  const end = scan.finished_at ? Date.parse(scan.finished_at) : now
  return end - Date.parse(scan.created_at)
}

export function fmtDate(iso) {
  try {
    return new Date(iso).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}

export function shortUrl(url) {
  return url.replace(/^https?:\/\/(www\.)?/i, '').replace(/\/$/, '')
}

export function isWebUrl(url) {
  return typeof url === 'string' && /^https?:\/\//i.test(url)
}

export function fmtBytes(n) {
  if (!Number.isFinite(n)) return ''
  if (n < 1024) return `${n} bytes`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
}

// mm:ss for compact counters
export function fmtClock(ms) {
  if (ms == null || Number.isNaN(ms)) return '--:--'
  const s = Math.max(0, Math.round(ms / 1000))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

// Status of a module: label, text colour class, CSS colour and icon (never colour alone: every status has its own icon)
export const JOB_STATUS = {
  queued: { label: 'Queued', tone: 'text-ink-3', color: 'var(--color-ink-3)', icon: 'circle' },
  running: { label: 'Running', tone: 'text-amber', color: 'var(--color-amber)', icon: null },
  done: { label: 'Done', tone: 'text-signal', color: 'var(--color-signal)', icon: 'check' },
  error: { label: 'Error', tone: 'text-bad', color: 'var(--color-bad)', icon: 'x' },
  timeout: { label: 'Timed out', tone: 'text-amber', color: 'var(--color-amber)', icon: 'clock' },
  cancelled: { label: 'Cancelled', tone: 'text-ink-3', color: 'var(--color-ink-3)', icon: 'minus' },
}

export const FINISHED = new Set(['done', 'error', 'timeout', 'cancelled'])
