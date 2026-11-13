import { useEffect, useMemo, useRef, useState } from 'react'
import Icon from './Icon.jsx'
import { TYPE_ICON, detectType } from '../lib/types.js'
import { fmtBytes } from '../lib/format.js'

const PREVIEWABLE = /^image\/(jpeg|png|gif|webp|bmp|avif)$/

function TypePills({ types, value, onChange }) {
  return (
    <div role="radiogroup" aria-label="Data type" className="flex flex-wrap gap-2">
      {types.map((t) => (
        <button key={t.id} type="button" role="radio" aria-checked={t.id === value} className="chip" onClick={() => onChange(t.id)}>
          <Icon name={TYPE_ICON[t.id]} size={15} className="shrink-0" />
          {t.label}
        </button>
      ))}
    </div>
  )
}

/** Prompt for text types: the tag on the left names the type, then the value. */
function PromptLine({ tag, typeInfo, value, onChange, inputRef }) {
  return (
    <div className="prompt">
      {tag}
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={typeInfo.placeholder}
        aria-label={`Value to search (${typeInfo.label})`}
        aria-keyshortcuts="/"
        autoComplete="off"
        autoCapitalize="off"
        spellCheck={false}
      />
      {!value && (
        <kbd aria-hidden="true" className="mr-3 hidden self-center rounded-[2px] border border-line-strong px-1.5 font-mono text-[12px] leading-5 text-ink-3 sm:block">
          /
        </kbd>
      )}
    </div>
  )
}

/** Same line for files: choose one here or drop it anywhere on the page. */
function FileLine({ tag, file, onFile, disabled }) {
  const inputRef = useRef(null)
  const [over, setOver] = useState(false)
  const [preview, setPreview] = useState(null)

  useEffect(() => {
    if (!file || !PREVIEWABLE.test(file.type)) {
      setPreview(null)
      return undefined
    }
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const pick = (list) => {
    const f = list?.[0]
    if (f) onFile(f)
  }

  return (
    <div
      className="prompt"
      style={over ? { borderColor: 'var(--color-signal)' } : undefined}
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        e.stopPropagation() // otherwise the page-wide listener would handle it too
        setOver(false)
        pick(e.dataTransfer.files)
      }}
    >
      {tag}
      <input ref={inputRef} type="file" className="sr-only" tabIndex={-1} aria-hidden="true" disabled={disabled} onChange={(e) => pick(e.target.files)} />
      {file ? (
        <div className="flex min-w-0 flex-1 items-center gap-3 px-3 py-2">
          {preview ? (
            <img src={preview} alt="Preview of the chosen file" className="size-8 shrink-0 rounded-[2px] border border-line-strong object-cover" />
          ) : (
            <span className="flex size-8 shrink-0 items-center justify-center rounded-[2px] border border-line-strong text-ink-2">
              <Icon name="file" size={16} />
            </span>
          )}
          <span className="min-w-0 flex-1 leading-tight">
            <span className="block truncate font-mono text-[14px]" title={file.name}>
              {file.name}
            </span>
            <span className="block font-mono text-[12px] text-ink-3">
              {fmtBytes(file.size)}
              {file.type ? `, ${file.type}` : ''}
            </span>
          </span>
          <span className="flex shrink-0 gap-3 text-[13px]">
            <button type="button" className="link-btn" onClick={() => inputRef.current?.click()} disabled={disabled}>
              Change
            </button>
            <button type="button" className="link-btn" onClick={() => onFile(null)} disabled={disabled}>
              Remove
            </button>
          </span>
        </div>
      ) : (
        <button type="button" onClick={() => inputRef.current?.click()} disabled={disabled} className="flex min-w-0 flex-1 items-center gap-3 px-4 text-left text-ink-2 hover:text-ink">
          <Icon name="upload" size={17} className="shrink-0" />
          <span className="truncate font-mono text-[14.5px]">Drop a file here or click to choose one</span>
        </button>
      )}
    </div>
  )
}

function OptionField({ toolId, option, value, onChange }) {
  const id = `opt-${toolId}-${option.key}`
  const field = 'w-full rounded-ctl border border-line-strong bg-base px-2 py-1.5 text-[13px] focus:border-signal focus:outline-none'
  return (
    <div className="mt-2">
      <label htmlFor={id} className="mb-1 block text-xs text-ink-2">
        {option.label}
      </label>
      {option.type === 'select' ? (
        <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className={field}>
          {option.choices.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      ) : (
        <input id={id} type="text" value={value} maxLength={40} onChange={(e) => onChange(e.target.value)} className={`${field} font-mono`} />
      )}
      {option.help && <p className="mt-1 text-xs text-ink-3">{option.help}</p>}
    </div>
  )
}

/** Tools for the chosen type: one toggle each, plus the options of the tools that have them. */
function ToolChips({ tools, selected, onToggle, options, onOption, showPeek, floating }) {
  const [optionsOpen, setOptionsOpen] = useState(false)
  const box = useRef(null)

  // A floating panel closes with Escape or a click outside it
  useEffect(() => {
    if (!optionsOpen || !floating) return undefined
    const onDown = (e) => {
      if (box.current && !box.current.contains(e.target)) setOptionsOpen(false)
    }
    const onKey = (e) => e.key === 'Escape' && setOptionsOpen(false)
    document.addEventListener('mousedown', onDown)
    window.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [optionsOpen, floating])
  const [peek, setPeek] = useState(null)
  const withOptions = tools.filter((t) => t.available && t.options.length > 0)
  const missing = tools.filter((t) => !t.available)
  const peeked = tools.find((t) => t.id === peek)

  return (
    <div ref={box} className="relative">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Tools">
        <span className="mr-1 text-[13px] text-ink-3">Tools</span>
        {tools.map((t) => (
          <button
            key={t.id}
            type="button"
            role="switch"
            aria-checked={t.available && selected[t.id] !== false}
            disabled={!t.available}
            className="chip"
            title={t.available ? t.description : t.unavailable_reason}
            onClick={() => onToggle(t.id)}
            onMouseEnter={() => setPeek(t.id)}
            onMouseLeave={() => setPeek(null)}
            onFocus={() => setPeek(t.id)}
            onBlur={() => setPeek(null)}
          >
            <span className="chip-box" aria-hidden="true">
              <Icon name="check" size={11} strokeWidth={3.4} />
            </span>
            {t.name}
          </button>
        ))}
        {withOptions.length > 0 && (
          <button type="button" className="chip" aria-expanded={optionsOpen} onClick={() => setOptionsOpen((v) => !v)}>
            <Icon name="sliders" size={14} />
            Options
          </button>
        )}
      </div>

      {showPeek && <p className="mt-2 min-h-5 text-[13px] text-ink-3">{peeked ? (peeked.available ? peeked.description : peeked.unavailable_reason) : ''}</p>}

      {missing.map((t) => (
        <p key={t.id} className="mt-2 flex items-start gap-2 text-[13px] text-amber">
          <Icon name="alert" size={14} className="mt-0.5 shrink-0" />
          {t.name} is not installed. Check the backend build log.
        </p>
      ))}

      {optionsOpen && (
        <div
          className={
            floating
              ? 'absolute inset-x-0 top-full z-30 mt-2 grid animate-pop gap-x-8 rounded-ctl border border-line-strong bg-surface p-4 shadow-[0_12px_32px_rgba(0,0,0,0.5)] sm:grid-cols-2'
              : 'mt-3 grid animate-pop gap-x-8 sm:grid-cols-2'
          }
        >
          {withOptions.map((t) => (
            <fieldset key={t.id} className="min-w-0 border-t border-line pt-2">
              <legend className="pr-2 text-[13px] font-medium">{t.name}</legend>
              {t.options.map((o) => (
                <OptionField key={o.key} toolId={t.id} option={o} value={options[t.id]?.[o.key] ?? o.default} onChange={(v) => onOption(t.id, o.key, v)} />
              ))}
            </fieldset>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * The only place where a search is started. With no search open it is the whole page (`hero`):
 * a large prompt in the middle. With a search open it docks to the top and gets out of the way.
 */
export default function CommandBar({ meta, draft, setDraft, busy, progress, error, onSubmit, hasScan }) {
  const hero = !hasScan
  const [selected, setSelected] = useState({}) // toolId -> bool (all tools are on by default)
  const [options, setOptions] = useState({}) // toolId -> { key: value }
  const promptRef = useRef(null)

  // "/" jumps to the prompt from anywhere on the page, like in most developer tools
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return
      const el = document.activeElement
      if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return
      if (!promptRef.current) return
      e.preventDefault()
      promptRef.current.focus()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const detected = draft.type === 'file' ? null : detectType(draft.value)
  const type = draft.manual || !detected ? draft.type : detected
  const isFile = type === 'file'
  const typeInfo = meta.types.find((t) => t.id === type) || meta.types[0]
  const tools = useMemo(() => meta.tools.filter((t) => t.accepts.includes(type)), [meta.tools, type])
  const active = tools.filter((t) => t.available && selected[t.id] !== false)
  const hasInput = isFile ? !!draft.file : !!draft.value.trim()
  const canSubmit = hasInput && active.length > 0 && !busy
  const maxMb = meta.limits?.max_upload_mb ?? 100

  const pickType = (id) => setDraft((d) => ({ ...d, type: id, manual: true }))
  const setValue = (value) =>
    setDraft((d) => {
      const manual = value.trim() ? d.manual : false // clearing the field goes back to automatic detection
      return { ...d, value, manual, type: manual ? d.type : detectType(value) || d.type }
    })

  const submit = (e) => {
    e.preventDefault()
    if (!canSubmit) return
    const opts = {}
    for (const t of active) if (options[t.id]) opts[t.id] = options[t.id]
    const base = { type, tools: active.map((t) => t.id), options: opts }
    onSubmit(isFile ? { ...base, file: draft.file } : { ...base, target: draft.value.trim() })
  }

  const pct = progress != null ? Math.round(progress * 100) : null
  let hint = null
  if (isFile) hint = `Photos, PDFs, Office documents, audio, video. Maximum ${maxMb} MB. The file is analysed on the server and then deleted: it is not kept.`
  else if (draft.value.trim() && !draft.manual && detected) hint = `Detected as ${typeInfo.label.toLowerCase()}. Change the type if that is wrong.`
  else if (type === 'phone') hint = 'Best with the international prefix, for example +1.'
  else if (hero) hint = 'The type is detected as you type.'

  // Hero: the type is named by the tag and picked with the chips above. Docked: the tag itself is the selector.
  const tag = hero ? (
    <span className="prompt-tag" aria-hidden="true">
      {typeInfo.label.toLowerCase()}
      <Icon name="chevronRight" size={14} strokeWidth={2.4} />
    </span>
  ) : (
    <label className="prompt-tag relative cursor-pointer">
      <Icon name={TYPE_ICON[type]} size={15} className="shrink-0" />
      {typeInfo.label.toLowerCase()}
      <Icon name="chevron" size={13} className="shrink-0" />
      <select aria-label="Data type" value={type} onChange={(e) => pickType(e.target.value)} className="absolute inset-0 h-full w-full cursor-pointer opacity-0">
        {meta.types.map((t) => (
          <option key={t.id} value={t.id}>
            {t.label}
          </option>
        ))}
      </select>
    </label>
  )

  return (
    <form
      onSubmit={submit}
      noValidate
      className={hero ? 'cmd-hero mx-auto w-full max-w-[760px] px-4 pb-16 pt-[clamp(2rem,18vh,11rem)] sm:px-6' : 'cmd-docked mx-auto w-full max-w-[1320px] px-4 py-3 sm:px-6'}
    >
      {hero && (
        <>
          <h2 className="text-[28px] font-semibold leading-tight tracking-tight sm:text-[32px]">Search public sources</h2>
          <p className="mt-2 max-w-[58ch] text-[15px] text-ink-2">
            Enter a username, email, phone number, domain or IP, or drop a file. The right tools start together and results appear as they arrive.
          </p>
          <div className="mt-6">
            <TypePills types={meta.types} value={type} onChange={pickType} />
          </div>
        </>
      )}

      <div className={`${hero ? 'mt-3' : ''} flex flex-col gap-2 sm:flex-row`}>
        {isFile ? (
          <FileLine tag={tag} file={draft.file} onFile={(f) => setDraft((d) => ({ ...d, file: f, type: 'file', manual: true }))} disabled={busy} />
        ) : (
          <PromptLine tag={tag} typeInfo={typeInfo} value={draft.value} onChange={setValue} inputRef={promptRef} />
        )}
        <button type="submit" className="btn-run" disabled={!canSubmit}>
          {busy ? (
            isFile && pct != null ? (
              `Uploading ${pct}%`
            ) : (
              'Starting…'
            )
          ) : (
            <>
              <Icon name="enter" size={17} strokeWidth={2.2} />
              {active.length === 0 ? 'No tool selected' : active.length === 1 ? 'Run 1 tool' : `Run ${active.length} tools`}
            </>
          )}
          {busy && isFile && pct != null && (
            <span className="absolute inset-x-0 bottom-0 h-[3px] bg-black/20" aria-hidden="true">
              <span className="block h-full bg-[#04140c]/70 transition-[width]" style={{ width: `${pct}%` }} />
            </span>
          )}
        </button>
      </div>

      {hint && <p className="mt-2 text-[13px] text-ink-3">{hint}</p>}
      {error && (
        <p role="alert" className="mt-2 flex items-start gap-2 text-[13.5px] text-bad">
          <Icon name="alert" size={15} className="mt-0.5 shrink-0" />
          {error}
        </p>
      )}

      <div className={hero ? 'mt-6' : 'mt-3'}>
        <ToolChips
          tools={tools}
          selected={selected}
          onToggle={(id) => setSelected((s) => ({ ...s, [id]: s[id] === false }))}
          options={options}
          onOption={(id, k, v) => setOptions((o) => ({ ...o, [id]: { ...o[id], [k]: v } }))}
          showPeek={hero}
          floating={!hero}
        />
      </div>
    </form>
  )
}
