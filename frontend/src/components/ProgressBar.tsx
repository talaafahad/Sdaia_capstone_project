interface ProgressBarProps {
  percentage: number
  /** Optional label override — defaults to "{percentage}%" */
  label?: string
}

export default function ProgressBar({ percentage, label }: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, percentage))

  return (
    <div className="w-full">
      <div className="flex justify-between items-center mb-1.5">
        <span className="text-xs text-text-muted font-medium">Overall progress</span>
        <span className="text-xs font-semibold text-purple-light tabular-nums">
          {label ?? `${pct}%`}
        </span>
      </div>
      <div
        className="w-full h-2 rounded-full overflow-hidden"
        style={{ background: 'rgba(129,116,201,0.2)' }}
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="h-full rounded-full transition-[width] duration-500 ease-out"
          style={{
            width: `${pct}%`,
            background: 'linear-gradient(to right, #8174C9, #9D7CFF)',
          }}
        />
      </div>
    </div>
  )
}
