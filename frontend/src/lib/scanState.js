// Pure logic (no React) to apply the server events to the scan state.
const MAX_LOGS = 500
const MAX_FRESH = 40 // above this threshold new results are not animated (very long lists)
export const FRESH_MS = 3000 // how long a result counts as "just arrived"

export function fromSnapshot(snap) {
  return {
    ...snap,
    skew: snap.server_time ? Date.parse(snap.server_time) - Date.now() : 0,
    jobs: snap.jobs.map((j) => ({ ...j, findings: j.findings || [], logs: j.logs || [] })),
  }
}

/**
 * Applies a batch of events [[type, data], ...] and returns the new state.
 * It never mutates `scan`: the jobs it touches are copied once per batch.
 */
export function applyEvents(scan, events) {
  let next = scan
  let work = new Map()

  const commit = () => {
    if (next && work.size) {
      next = { ...next, jobs: next.jobs.map((j) => work.get(j.id) || j) }
    }
    work = new Map()
  }
  const job = (id) => {
    if (!next) return null
    let j = work.get(id)
    if (!j) {
      const orig = next.jobs.find((x) => x.id === id)
      if (!orig) return null
      j = { ...orig, findings: orig.findings.slice(), logs: orig.logs.slice() }
      work.set(id, j)
    }
    return j
  }

  for (const [type, data] of events) {
    if (type === 'snapshot') {
      work = new Map()
      next = fromSnapshot(data)
      continue
    }
    if (!next) continue
    if (type === 'job') {
      const j = job(data.id)
      if (j) {
        const { findings_count, ...rest } = data // the real number is findings.length
        Object.assign(j, rest)
      }
    } else if (type === 'log') {
      const j = job(data.job)
      if (j) {
        j.logs.push(data.line)
        if (j.logs.length > MAX_LOGS) j.logs.splice(0, j.logs.length - MAX_LOGS)
      }
    } else if (type === 'finding') {
      const j = job(data.job)
      if (j) j.findings.push(j.findings.length < MAX_FRESH ? { ...data.finding, fresh: Date.now() } : data.finding)
    } else if (type === 'scan') {
      commit()
      next = { ...next, ...data }
    }
  }
  commit()
  return next
}

// Groups the results, keeping the order of arrival.
export function groupFindings(findings) {
  const groups = new Map()
  for (const f of findings) {
    const key = f.group || 'Results'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(f)
  }
  return [...groups.entries()].map(([name, items]) => ({ name, items }))
}
