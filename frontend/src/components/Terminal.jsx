import { useEffect, useRef } from 'react'

function tone(line) {
  if (line.startsWith('[+]')) return 'text-signal'
  if (line.startsWith('[!]') || /error|traceback/i.test(line.slice(0, 40))) return 'text-amber'
  if (line.startsWith('$ ')) return 'text-signal'
  if (line.startsWith('[-]') || line.startsWith('[*]') || line.startsWith('[i]')) return 'text-ink-3'
  return 'text-ink-2'
}

export default function Terminal({ lines, running }) {
  const ref = useRef(null)
  const stick = useRef(true)

  useEffect(() => {
    const el = ref.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [lines.length])

  const onScroll = () => {
    const el = ref.current
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 28
  }

  return (
    <div className="term mt-2">
      <div
        ref={ref}
        onScroll={onScroll}
        role="log"
        aria-label="Tool log"
        tabIndex={0}
        className="max-h-72 overflow-auto px-3.5 py-3 font-mono text-[12px] leading-[1.65]"
      >
        {lines.length === 0 && <p className="text-ink-3">No output yet.</p>}
        {lines.map((line, i) => (
          <p key={i} className={`whitespace-pre-wrap break-all ${tone(line)} ${running && i === lines.length - 1 ? 'caret' : ''}`}>
            {line}
          </p>
        ))}
      </div>
    </div>
  )
}
