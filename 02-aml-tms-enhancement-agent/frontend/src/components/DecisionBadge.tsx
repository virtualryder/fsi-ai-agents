import type { Decision } from '@/lib/types'
import clsx from 'clsx'

const config: Record<Decision, { label: string; className: string }> = {
  SUPPRESS:     { label: 'SUPPRESS',     className: 'bg-accent-red/20 text-accent-red border-accent-red/40' },
  DOWNGRADE:    { label: 'DOWNGRADE',    className: 'bg-accent-yellow/20 text-accent-yellow border-accent-yellow/40' },
  PASS_THROUGH: { label: 'PASS THROUGH', className: 'bg-accent-green/20 text-accent-green border-accent-green/40' },
  ESCALATE:     { label: 'ESCALATE',     className: 'bg-accent-blue/20 text-accent-blue border-accent-blue/40' },
}

export default function DecisionBadge({
  decision,
  size = 'sm',
}: {
  decision: Decision
  size?: 'sm' | 'md'
}) {
  const { label, className } = config[decision] ?? config.PASS_THROUGH
  return (
    <span
      className={clsx(
        'inline-flex items-center font-mono font-semibold border rounded',
        size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-3 py-1',
        className
      )}
    >
      {label}
    </span>
  )
}
