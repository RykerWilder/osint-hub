import Icon from './Icon.jsx'
import Logo from './Logo.jsx'
import HistoryMenu from './HistoryMenu.jsx'

export default function TopBar({ name, activeId, ...history }) {
  return (
    <header className="shrink-0 border-b border-line bg-base">
      <div className="mx-auto flex h-12 w-full max-w-[1320px] items-center justify-between gap-3 px-4 sm:px-6">
        <h1 className="m-0">
          <a href="#/" className="flex items-center gap-2.5" title="Back to the start">
            <Logo />
            <span className="whitespace-nowrap font-mono text-[15px] font-semibold tracking-tight">{name || 'osint-hub'}</span>
          </a>
        </h1>
        <div className="flex items-center gap-2">
          {activeId && (
            <a href="#/" className="btn" aria-label="New search">
              <Icon name="search" size={14} />
              <span className="hidden sm:inline">New search</span>
            </a>
          )}
          <HistoryMenu activeId={activeId} {...history} />
        </div>
      </div>
    </header>
  )
}
