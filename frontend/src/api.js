async function request(path, options) {
  let res
  try {
    res = await fetch(path, options)
  } catch {
    throw new Error('Cannot reach the server. Check that it is running.')
  }
  if (!res.ok) {
    let detail
    try {
      detail = (await res.json()).detail
    } catch {
      /* not a JSON response */
    }
    throw new Error(detail || `Server error (${res.status})`)
  }
  return res.status === 204 ? null : res.json()
}

export const getMeta = () => request('/api/tools')
export const listScans = () => request('/api/scans')
export const createScan = (payload) =>
  request('/api/scans', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
/**
 * Analyse a file: the file is the request body (no multipart).
 * onProgress receives a number from 0 to 1. Returns the created scan.
 */
export function uploadScan(file, { tools, onProgress } = {}) {
  const params = new URLSearchParams({ filename: file.name, modified: String(file.lastModified || '') })
  if (tools?.length) params.set('tools', tools.join(','))
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `/api/scans/file?${params}`)
    xhr.setRequestHeader('Content-Type', 'application/octet-stream')
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total)
    xhr.onload = () => {
      let body = null
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        /* not a JSON response */
      }
      if (xhr.status >= 200 && xhr.status < 300 && body) resolve(body)
      else if (xhr.status === 413) reject(new Error(body?.detail || 'File too large.'))
      else reject(new Error(body?.detail || `Server error (${xhr.status})`))
    }
    xhr.onerror = () => reject(new Error('Cannot reach the server. Check that it is running.'))
    xhr.send(file)
  })
}

export const cancelScan = (id) => request(`/api/scans/${id}/cancel`, { method: 'POST' })
export const deleteScan = (id) => request(`/api/scans/${id}`, { method: 'DELETE' })

export const reportUrl = (scanId, jobId) =>
  jobId ? `/api/scans/${scanId}/jobs/${jobId}/report.txt` : `/api/scans/${scanId}/report.txt`
export const eventsUrl = (scanId) => `/api/scans/${scanId}/events`
