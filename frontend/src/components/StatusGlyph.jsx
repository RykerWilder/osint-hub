import { useEffect, useState } from 'react'
import Icon from './Icon.jsx'
import { JOB_STATUS } from '../lib/format.js'

const FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

const reduceMotion = () =>
  typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** Braille spinner: it only ticks while it is on screen, and it stands still if the user asked for less motion. */
function Spinner() {
  const [i, setI] = useState(0)
  useEffect(() => {
    if (reduceMotion()) return undefined
    const t = setInterval(() => setI((n) => (n + 1) % FRAMES.length), 90)
    return () => clearInterval(t)
  }, [])
  return (
    <span aria-hidden="true" className="inline-block w-[1ch] text-center font-mono leading-none text-amber">
      {reduceMotion() ? '…' : FRAMES[i]}
    </span>
  )
}

/** Icon of a module status. Every status has its own shape, so it never relies on colour alone. */
export default function StatusGlyph({ status, size = 15 }) {
  const info = JOB_STATUS[status] || JOB_STATUS.queued
  return (
    <span className="inline-flex shrink-0 items-center justify-center" style={{ width: size + 2, height: size + 2, fontSize: size }} title={info.label}>
      {status === 'running' ? <Spinner /> : <Icon name={info.icon} size={size} strokeWidth={2} style={{ color: info.color }} />}
      <span className="sr-only">{info.label}</span>
    </span>
  )
}
