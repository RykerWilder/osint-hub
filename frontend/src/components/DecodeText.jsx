import { useEffect, useState } from 'react'

const GLYPHS = '01<>/\\[]{}#$%&*+=?ABCDEF'
const MAX_CHARS = 80 // beyond this length the rest of the text appears immediately
const FRAMES = 14

const canAnimate = () =>
  typeof window !== 'undefined' && typeof window.matchMedia === 'function' && !window.matchMedia('(prefers-reduced-motion: reduce)').matches

function scramble(text, frame) {
  const chars = [...text.slice(0, MAX_CHARS)]
  const revealed = Math.floor((frame / FRAMES) * chars.length)
  const mixed = chars.map((c, i) => (i < revealed || c === ' ' ? c : GLYPHS[Math.floor(Math.random() * GLYPHS.length)]))
  return mixed.join('') + text.slice(MAX_CHARS)
}

/**
 * Shows the text; when `animate` is true it "decodes" it in half a second (effect for results that just arrived).
 * The real text is always available to screen readers.
 */
export default function DecodeText({ text, animate = false }) {
  const [shown, setShown] = useState(() => (animate && text && canAnimate() ? scramble(text, 0) : text))

  useEffect(() => {
    if (!animate || !text || !canAnimate()) {
      setShown(text)
      return undefined
    }
    let frame = 0
    const id = setInterval(() => {
      frame += 1
      if (frame >= FRAMES) {
        clearInterval(id)
        setShown(text)
      } else {
        setShown(scramble(text, frame))
      }
    }, 32)
    return () => clearInterval(id)
  }, [text, animate])

  return (
    <>
      <span className="sr-only">{text}</span>
      <span aria-hidden="true">{shown}</span>
    </>
  )
}
