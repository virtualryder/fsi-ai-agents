'use client'

import type { Decision } from '@/lib/types'

const decisionColor: Record<Decision, string> = {
  SUPPRESS:     '#f85149',
  DOWNGRADE:    '#e3b341',
  PASS_THROUGH: '#3fb950',
  ESCALATE:     '#58a6ff',
}

function fpColor(fp: number): string {
  if (fp >= 85) return '#f85149'
  if (fp >= 60) return '#e3b341'
  if (fp <= 15) return '#58a6ff'
  return '#3fb950'
}

/**
 * SVG semicircle gauge — arc goes left → top → right.
 *
 * Math:
 *   Center (cx=100, cy=100), radius=80
 *   Track: M 20,100  A 80,80 0 0 0 180,100  (counterclockwise = via top in SVG)
 *   For value V (0–100):
 *     angle = π – V * π/100   (standard polar, from left to right via top)
 *     x = cx + r·cos(angle)
 *     y = cy – r·sin(angle)   (minus because SVG y-axis is inverted)
 */
export default function ScoreGauge({ value, decision }: { value: number; decision?: Decision }) {
  const cx = 100, cy = 100, r = 80

  const angleRad = Math.PI - (value / 100) * Math.PI
  const vx = cx + r * Math.cos(angleRad)
  const vy = cy - r * Math.sin(angleRad)

  // Track: full semicircle via top
  const track = `M ${cx - r} ${cy} A ${r} ${r} 0 0 0 ${cx + r} ${cy}`

  // Value arc: start at left, end at computed point, counterclockwise (sweep=0)
  const largeArc = value > 50 ? 1 : 0
  const valueArc = `M ${cx - r} ${cy} A ${r} ${r} 0 ${largeArc} 0 ${vx.toFixed(2)} ${vy.toFixed(2)}`

  const color = decision ? decisionColor[decision] : fpColor(value)

  return (
    <svg viewBox="0 0 200 115" className="w-full max-w-xs mx-auto">
      {/* Track */}
      <path d={track} fill="none" stroke="#30363d" strokeWidth="14" strokeLinecap="round" />
      {/* Value arc */}
      <path d={valueArc} fill="none" stroke={color} strokeWidth="14" strokeLinecap="round" />
      {/* Needle dot */}
      <circle cx={vx} cy={vy} r="5" fill={color} />
      {/* Value text */}
      <text x={cx} y={cy + 8} textAnchor="middle" fontSize="26" fontWeight="700" fill="#f0f6fc">
        {value.toFixed(0)}%
      </text>
      <text x={cx} y={cy + 26} textAnchor="middle" fontSize="11" fill="#8b949e">
        FP Probability
      </text>
      {/* Scale labels */}
      <text x={cx - r - 4} y={cy + 14} textAnchor="end" fontSize="10" fill="#6e7681">0</text>
      <text x={cx + r + 4} y={cy + 14} textAnchor="start" fontSize="10" fill="#6e7681">100</text>
    </svg>
  )
}
