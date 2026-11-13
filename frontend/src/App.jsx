import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import TopBar from './components/TopBar.jsx'
import CommandBar from './components/CommandBar.jsx'
import Workspace from './components/Workspace.jsx'
import ErrorState from './components/ErrorState.jsx'
import DropOverlay from './components/DropOverlay.jsx'
import { cancelScan, createScan, deleteScan, getMeta, listScans, uploadScan } from './api.js'
import { openScan, useFileDrop, useScanIdFromHash, useScanStream } from './hooks.js'
import { DEFAULT_TYPES } from './lib/types.js'

const EMPTY_DRAFT = { value: '', type: 'username', manual: false, file: null }

export default function App() {
  const [meta, setMeta] = useState(null)
  const [metaError, setMetaError] = useState(null)
  const [scans, setScans] = useState([])
  const [draft, setDraft] = useState(EMPTY_DRAFT)
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState(null)
  const [formError, setFormError] = useState(null)
  const submitted = useRef(null) // the search started from the command bar: { id, target, file }

  const scanId = useScanIdFromHash()
  const { scan, error: streamError } = useScanStream(scanId)

  const loadMeta = useCallback(() => {
    setMetaError(null)
    getMeta().then(setMeta, (e) => setMetaError(e.message))
  }, [])
  const refreshScans = useCallback(() => {
    listScans().then(setScans, () => {})
  }, [])

  useEffect(() => {
    loadMeta()
    refreshScans()
  }, [loadMeta, refreshScans])

  // Refresh the history when a search changes state (started, finished, stopped)
  useEffect(() => {
    refreshScans()
  }, [scan?.id, scan?.status, refreshScans])

  // When the search started from the command bar is over, clear the input so the next one starts clean.
  // If the user already typed something else in the meantime, it is left alone.
  useEffect(() => {
    const sent = submitted.current
    if (!sent || !scan || scan.id !== sent.id || scan.status === 'running') return
    submitted.current = null
    setDraft((d) => {
      const unchanged = sent.file ? d.file === sent.file : d.value.trim() === sent.target
      return unchanged ? { ...d, value: '', file: null, manual: false } : d
    })
  }, [scan?.id, scan?.status])

  const appName = meta?.app.name
  useEffect(() => {
    document.title = appName || 'osint-hub'
  }, [appName])

  const typeLabels = useMemo(() => Object.fromEntries((meta?.types || DEFAULT_TYPES).map((t) => [t.id, t.label])), [meta])
  const maxMb = meta?.limits?.max_upload_mb ?? 100

  const chooseFile = useCallback((file) => {
    setFormError(null)
    setDraft((d) => ({ ...d, file, type: 'file', manual: true }))
  }, [])
  const dragging = useFileDrop(chooseFile, !!meta && !busy)

  const start = async (payload) => {
    setBusy(true)
    setProgress(null)
    setFormError(null)
    try {
      let created
      if (payload.type === 'file') {
        if (payload.file.size > maxMb * 1024 * 1024) throw new Error(`File too large: the limit is ${maxMb} MB.`)
        created = await uploadScan(payload.file, { tools: payload.tools, onProgress: setProgress })
      } else {
        created = await createScan(payload)
      }
      submitted.current = { id: created.id, target: payload.target, file: payload.file }
      openScan(created.id)
      if (window.innerWidth < 1024) {
        setTimeout(() => document.getElementById('results')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80)
      }
    } catch (e) {
      setFormError(e.message)
    } finally {
      setBusy(false)
      setProgress(null)
    }
  }

  const remove = async (id) => {
    try {
      await deleteScan(id)
    } catch {
      /* already deleted */
    }
    if (id === scanId) openScan(null)
    refreshScans()
  }

  const message = (text) => <p className="p-4 font-mono text-sm text-ink-3 sm:p-6">{text}</p>

  let view
  if (scan) {
    view = <Workspace key={scan.id} scan={scan} typeLabel={typeLabels[scan.type] || scan.type} onCancel={() => cancelScan(scan.id).catch(() => {})} />
  } else if (scanId && streamError) {
    view = (
      <div className="p-4 sm:p-6">
        <ErrorState title="Search not found" message={streamError} actionLabel="Back to start" onAction={() => openScan(null)} />
      </div>
    )
  } else {
    view = message('Loading search…')
  }

  let body
  if (meta) {
    body = (
      <>
        {/* One command bar for both states: centred on an empty page, docked to the top once a search is open */}
        <div className={scanId ? 'shrink-0 border-b border-line bg-surface' : 'flex flex-1 overflow-y-auto'}>
          <CommandBar meta={meta} draft={draft} setDraft={setDraft} busy={busy} progress={progress} error={formError} onSubmit={start} hasScan={!!scanId} />
        </div>
        {scanId && (
          <main id="results" className="min-h-0 flex-1 lg:overflow-hidden">
            {view}
          </main>
        )}
      </>
    )
  } else if (metaError) {
    body = (
      <main className="flex-1 overflow-y-auto p-4 sm:p-6">
        <div className="mx-auto w-full max-w-[760px] pt-[8vh]">
          <ErrorState title="The server is not responding" message={metaError} actionLabel="Try again" onAction={loadMeta} />
        </div>
      </main>
    )
  } else {
    body = <main className="flex-1">{message('Connecting to the backend…')}</main>
  }

  return (
    <div className="flex min-h-dvh flex-col lg:h-dvh lg:overflow-hidden">
      <TopBar name={appName} scans={scans} activeId={scanId} typeLabels={typeLabels} onOpen={openScan} onDelete={remove} />
      {body}
      {dragging && <DropOverlay maxMb={maxMb} />}
    </div>
  )
}
