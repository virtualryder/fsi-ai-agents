import clsx from 'clsx'

export default function MetricCard({
  label,
  value,
  sub,
  valueColor,
}: {
  label: string
  value: string | number
  sub?: string
  valueColor?: string
}) {
  return (
    <div className="bg-canvas-overlay border border-border rounded-lg p-4">
      <p className="text-xs uppercase tracking-wider text-fg-muted mb-1">{label}</p>
      <p className={clsx('text-2xl font-bold', valueColor ?? 'text-fg')}>{value}</p>
      {sub && <p className="text-xs text-fg-subtle mt-0.5">{sub}</p>}
    </div>
  )
}
