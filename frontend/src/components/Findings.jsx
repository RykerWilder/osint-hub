import { memo, useMemo, useState } from 'react'
import Icon from './Icon.jsx'
import DecodeText from './DecodeText.jsx'
import { FRESH_MS, groupFindings } from '../lib/scanState.js'
import { isWebUrl, shortUrl } from '../lib/format.js'

const PAGE = 40
const FILTER_FROM = 30 // above this number of results the filter box appears
export const HIGHLIGHT_GROUP = 'Highlights'

// A result is "new" only if it arrived a few seconds ago: opening and closing panels does not replay the effect.
const isFresh = (f) => typeof f.fresh === 'number' && Date.now() - f.fresh < FRESH_MS

function ExternalLink({ url, children, className = '' }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className={`inline-flex items-center gap-1 text-link underline decoration-link/30 underline-offset-4 hover:decoration-link ${className}`}
      title={url}
    >
      {children}
      <Icon name="external" size={12} className="shrink-0" />
    </a>
  )
}

const Row = memo(function Row({ f }) {
  const link = isWebUrl(f.url)
  const fresh = isFresh(f)
  return (
    <li className={`grid grid-cols-[minmax(6.5rem,32%)_minmax(0,1fr)] gap-x-4 border-b border-line/70 py-1.5 ${fresh ? 'fresh-row' : ''}`}>
      <span className="break-words text-[13.5px] leading-snug text-ink-2" title={f.label}>
        <DecodeText text={f.label} animate={fresh} />
      </span>
      <span className="min-w-0 break-words font-mono text-[12.5px] leading-snug text-ink">
        {f.value && <DecodeText text={f.value} animate={fresh} />}
        {link && (
          <ExternalLink url={f.url} className={f.value ? 'ml-2' : ''}>
            {f.value ? <span className="sr-only">Open {shortUrl(f.url)}</span> : <span className="break-all">{shortUrl(f.url)}</span>}
          </ExternalLink>
        )}
      </span>
    </li>
  )
})

const Tile = memo(function Tile({ f }) {
  const link = isWebUrl(f.url)
  const fresh = isFresh(f)
  const isMap = link && /openstreetmap\.org|google\.[a-z.]+\/maps/.test(f.url)
  return (
    <li className={`rounded-ctl border border-line bg-surface px-3 py-2 ${fresh ? 'fresh-row' : ''}`}>
      <p className="flex items-center gap-1.5 text-[12.5px] leading-tight text-ink-3">
        {isMap && <Icon name="pin" size={12} className="text-amber" />}
        {f.label}
        {f.tool && <span className="ml-auto font-mono text-[11.5px] text-ink-3">{f.tool}</span>}
      </p>
      <p className="mt-1 break-words font-mono text-[13px] leading-snug text-ink">
        {f.value && <DecodeText text={f.value} animate={fresh} />}
        {link && (
          <ExternalLink url={f.url} className={f.value ? 'ml-2' : ''}>
            {isMap ? <span>map</span> : f.value ? <span className="sr-only">Open {shortUrl(f.url)}</span> : <span>{shortUrl(f.url)}</span>}
          </ExternalLink>
        )}
      </p>
    </li>
  )
})

/** Grid of key facts (used by the file analysis and by the overview). `items` may carry a `tool` name. */
export function HighlightGrid({ items }) {
  return (
    <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
      {items.map((f, i) => (
        <Tile key={i} f={f} />
      ))}
    </ul>
  )
}

function GroupHeading({ name, count, open, onToggle }) {
  const content = (
    <>
      {onToggle && <Icon name="chevron" size={13} className={`transition-transform ${open ? '' : '-rotate-90'}`} />}
      <span>{name}</span>
      <span className="font-normal text-ink-3">{count}</span>
      <span className="h-px flex-1 bg-line" aria-hidden="true" />
    </>
  )
  const cls = 'mb-1 flex w-full items-center gap-2 text-left text-[13.5px] font-medium text-ink'
  return onToggle ? (
    <h4>
      <button type="button" className={`${cls} hover:text-ink`} aria-expanded={open} onClick={onToggle}>
        {content}
      </button>
    </h4>
  ) : (
    <h4 className={cls}>{content}</h4>
  )
}

function Group({ name, items, showName }) {
  const [all, setAll] = useState(false)
  const [open, setOpen] = useState(true)
  const collapsible = items.length > 12
  const shown = all ? items : items.slice(0, PAGE)

  if (name === HIGHLIGHT_GROUP) {
    return (
      <div className="mt-5 first:mt-0">
        <GroupHeading name={name} count={items.length} />
        <HighlightGrid items={items} />
      </div>
    )
  }

  return (
    <div className="mt-5 first:mt-0">
      {showName && <GroupHeading name={name} count={items.length} open={open} onToggle={collapsible ? () => setOpen((v) => !v) : undefined} />}
      {open && (
        <>
          <ul>
            {shown.map((f, i) => (
              <Row key={i} f={f} />
            ))}
          </ul>
          {!all && items.length > PAGE && (
            <button type="button" className="link-btn mt-2 text-[13px]" onClick={() => setAll(true)}>
              Show {items.length - PAGE} more
            </button>
          )}
        </>
      )}
    </div>
  )
}

export default function Findings({ findings }) {
  const [query, setQuery] = useState('')
  const q = query.trim().toLowerCase()
  const visible = useMemo(
    () => (q ? findings.filter((f) => `${f.group || ''} ${f.label} ${f.value || ''} ${f.url || ''}`.toLowerCase().includes(q)) : findings),
    [findings, q],
  )
  const groups = groupFindings(visible)
  const filterable = findings.length > FILTER_FROM

  return (
    <div>
      {filterable && (
        <label className="mb-4 flex items-center gap-2 rounded-ctl border border-line-strong bg-base px-3 py-1.5 focus-within:border-signal">
          <Icon name="search" size={14} className="text-ink-3" />
          <span className="sr-only">Filter results</span>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`Filter ${findings.length} results`}
            autoComplete="off"
            spellCheck={false}
            className="w-full bg-transparent font-mono text-[12.5px] focus:outline-none"
          />
          {q && <span className="shrink-0 font-mono text-[12px] text-ink-3">{visible.length}</span>}
        </label>
      )}
      {groups.map((g) => (
        <Group key={g.name} name={g.name} items={g.items} showName={groups.length > 1 || g.name !== 'Results'} />
      ))}
      {q && visible.length === 0 && <p className="text-sm text-ink-3">No result matches the filter.</p>}
    </div>
  )
}
