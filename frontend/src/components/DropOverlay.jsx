import Icon from './Icon.jsx'

/** Full-page overlay shown while a file is dragged over the window. It does not catch the mouse: the page itself handles the drop. */
export default function DropOverlay({ maxMb }) {
  return (
    <div className="pointer-events-none fixed inset-0 z-50 bg-base/85 p-4 backdrop-blur-sm sm:p-8" role="status">
      <div className="flex h-full flex-col items-center justify-center rounded-ctl border-2 border-dashed border-signal bg-surface/70 px-6 text-center">
        <Icon name="upload" size={34} className="text-signal" />
        <p className="mt-4 font-mono text-[22px] font-medium">Drop the file to analyse it</p>
        <p className="mt-1 text-[14px] text-ink-2">All of its metadata is extracted. Maximum {maxMb} MB.</p>
      </div>
    </div>
  )
}
