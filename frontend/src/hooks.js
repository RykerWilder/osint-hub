import { useEffect, useState } from 'react'
import { applyEvents } from './lib/scanState.js'
import { eventsUrl } from './api.js'

const HASH = /^#\/scan\/([a-f0-9]{10})$/
const readHash = () => {
  const m = window.location.hash.match(HASH)
  return m ? m[1] : null
}

/** ID of the open scan, read from the address (#/scan/ID): reloading the page loses nothing. */
export function useScanIdFromHash() {
  const [id, setId] = useState(readHash)
  useEffect(() => {
    const onChange = () => setId(readHash())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return id
}

export const openScan = (id) => {
  window.location.hash = id ? `#/scan/${id}` : '#/'
}

/** Follows a scan in real time (SSE). Events are batched every ~120 ms. */
export function useScanStream(scanId) {
  const [scan, setScan] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    setScan(null)
    setError(null)
    if (!scanId) return undefined

    let queue = []
    let timer = null
    const flush = () => {
      timer = null
      const batch = queue
      queue = []
      if (batch.length) setScan((prev) => applyEvents(prev, batch))
    }
    const push = (type, data) => {
      queue.push([type, data])
      if (!timer) timer = setTimeout(flush, 120)
    }

    const es = new EventSource(eventsUrl(scanId))
    for (const type of ['snapshot', 'job', 'log', 'finding', 'scan']) {
      es.addEventListener(type, (e) => push(type, JSON.parse(e.data)))
    }
    es.addEventListener('end', () => {
      clearTimeout(timer)
      flush()
      es.close()
    })
    es.onerror = () => {
      // CLOSED = the server answered with an error (e.g. unknown scan): it will not retry on its own
      if (es.readyState === EventSource.CLOSED) setError('This search no longer exists or the server is not responding.')
    }
    return () => {
      clearTimeout(timer)
      es.close()
    }
  }, [scanId])

  return { scan, error }
}

/** Current time, refreshed every second, only while needed. */
export function useNow(active) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (!active) return undefined
    setNow(Date.now())
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [active])
  return now
}

/**
 * Dragging a file anywhere on the page: `dragging` is true while a file is over the window,
 * `onFile` receives the first dropped file. Dragging text or links is ignored.
 */
export function useFileDrop(onFile, enabled = true) {
  const [dragging, setDragging] = useState(false)
  useEffect(() => {
    if (!enabled) {
      setDragging(false)
      return undefined
    }
    let depth = 0
    const hasFiles = (e) => Array.from(e.dataTransfer?.types || []).includes('Files')
    const enter = (e) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      depth += 1
      setDragging(true)
    }
    const over = (e) => hasFiles(e) && e.preventDefault()
    const leave = (e) => {
      if (!hasFiles(e)) return
      depth = Math.max(0, depth - 1)
      if (depth === 0) setDragging(false)
    }
    const drop = (e) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      depth = 0
      setDragging(false)
      const file = e.dataTransfer.files?.[0]
      if (file) onFile(file)
    }
    window.addEventListener('dragenter', enter)
    window.addEventListener('dragover', over)
    window.addEventListener('dragleave', leave)
    window.addEventListener('drop', drop)
    return () => {
      window.removeEventListener('dragenter', enter)
      window.removeEventListener('dragover', over)
      window.removeEventListener('dragleave', leave)
      window.removeEventListener('drop', drop)
    }
  }, [onFile, enabled])
  return dragging
}
