/** Mark: a terminal prompt (chevron and cursor) inside a square frame. */
export default function Logo({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <rect x="2.5" y="2.5" width="27" height="27" rx="3" stroke="var(--color-line-strong)" strokeWidth="1.5" />
      <path d="M9.5 11l6 5-6 5" stroke="var(--color-signal)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M18 22h5" stroke="var(--color-ink)" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  )
}
