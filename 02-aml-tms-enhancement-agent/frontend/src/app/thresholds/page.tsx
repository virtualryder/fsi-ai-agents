'use client'

import { useState, useEffect } from 'react'
import { Settings, Save, AlertTriangle } from 'lucide-react'
import { fetchThresholds, updateThresholds } from '@/lib/api'
import type { Thresholds, AlertTypeOverride } from '@/lib/types'

function BandDiagram({ suppress, downgrade, escalate }: {
  suppress: number; downgrade: number; escalate: number
}) {
  const bands = [
    { lo: 0,          hi: escalate,  label: 'ESCALATE',     color: '#58a6ff' },
    { lo: escalate,   hi: downgrade, label: 'PASS THROUGH', color: '#3fb950' },
    { lo: downgrade,  hi: suppress,  label: 'DOWNGRADE',    color: '#e3b341' },
    { lo: suppress,   hi: 100,       label: 'SUPPRESS',     color: '#f85149' },
  ]

  return (
    <div className="space-y-2">
      <p className="text-xs text-fg-muted mb-3">Decision bands (FP probability %)</p>
      <div className="relative h-12 bg-canvas-subtle rounded-lg overflow-hidden flex">
        {bands.map(b => (
          <div
            key={b.label}
            className="relative flex items-center justify-center text-xs font-medium overflow-hidden"
            style={{
              width: `${b.hi - b.lo}%`,
              background: `${b.color}22`,
              borderRight: '1px solid #21262d',
            }}
          >
            <span style={{ color: b.color }} className="truncate px-1">{b.label}</span>
          </div>
        ))}
      </div>
      <div className="relative h-4">
        {[escalate, downgrade, suppress].map((val, i) => (
          <div
            key={i}
            className="absolute text-xs text-fg-muted"
            style={{ left: `${val}%`, transform: 'translateX(-50%)' }}
          >
            {val}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function ThresholdsPage() {
  const [thresholds, setThresholds] = useState<Thresholds>({ suppress: 85, downgrade: 60, escalate: 15 })
  const [overrides, setOverrides] = useState<AlertTypeOverride[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Preview state (before saving)
  const [preview, setPreview] = useState<Thresholds>({ suppress: 85, downgrade: 60, escalate: 15 })

  useEffect(() => {
    fetchThresholds()
      .then(res => {
        setThresholds(res.thresholds)
        setPreview(res.thresholds)
        setOverrides(res.alert_type_overrides)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const validationError =
    preview.suppress <= preview.downgrade ? 'Suppress must be greater than Downgrade' :
    preview.downgrade <= preview.escalate ? 'Downgrade must be greater than Escalate' :
    null

  async function save() {
    if (validationError) return
    setSaving(true)
    setError(null)
    try {
      const res = await updateThresholds(preview)
      setThresholds(res.thresholds)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <Settings className="text-accent-blue" size={20} />
          <h1 className="text-xl font-semibold">Threshold Configuration</h1>
        </div>
        <p className="text-sm text-fg-muted">
          Govern when alerts are suppressed, downgraded, or escalated.
          Changes must be reviewed and approved by the CAMLO per <strong>SR 11-7</strong>.
        </p>
      </div>

      <div className="flex items-start gap-2 bg-accent-yellow/10 border border-accent-yellow/30 rounded-lg px-4 py-3">
        <AlertTriangle className="text-accent-yellow flex-shrink-0 mt-0.5" size={15} />
        <p className="text-xs text-accent-yellow">
          BSA Officer role required to modify scoring thresholds. All changes are logged in the audit trail.
        </p>
      </div>

      {loading ? (
        <p className="text-sm text-fg-muted">Loading thresholds…</p>
      ) : (
        <>
          {/* Sliders */}
          <div className="bg-canvas-overlay border border-border rounded-lg p-5 space-y-6">
            <h2 className="text-sm font-medium">Global Thresholds</h2>

            {[
              {
                key: 'suppress' as const,
                label: 'SUPPRESS threshold',
                description: 'FP probability ≥ this → alert suppressed (removed from analyst queue)',
                color: '#f85149',
                min: 70, max: 99,
              },
              {
                key: 'downgrade' as const,
                label: 'DOWNGRADE threshold',
                description: 'FP probability ≥ this → alert queued at lower priority',
                color: '#e3b341',
                min: 40, max: preview.suppress - 1,
              },
              {
                key: 'escalate' as const,
                label: 'ESCALATE threshold',
                description: 'FP probability ≤ this → alert fast-tracked to senior analyst / FCU',
                color: '#58a6ff',
                min: 5, max: 30,
              },
            ].map(({ key, label, description, color, min, max }) => (
              <div key={key}>
                <div className="flex justify-between items-baseline mb-1">
                  <label className="text-sm font-medium" style={{ color }}>{label}</label>
                  <span className="font-mono text-lg font-bold" style={{ color }}>{preview[key]}%</span>
                </div>
                <p className="text-xs text-fg-muted mb-2">{description}</p>
                <input
                  type="range"
                  min={min}
                  max={max}
                  value={preview[key]}
                  onChange={e => setPreview(p => ({ ...p, [key]: Number(e.target.value) }))}
                  className="w-full accent-current"
                  style={{ accentColor: color }}
                />
              </div>
            ))}

            {validationError && (
              <p className="text-xs text-accent-red">{validationError}</p>
            )}

            {/* Band diagram */}
            <BandDiagram suppress={preview.suppress} downgrade={preview.downgrade} escalate={preview.escalate} />

            {error && <p className="text-xs text-accent-red">{error}</p>}

            <button
              onClick={save}
              disabled={saving || !!validationError}
              className="flex items-center gap-2 px-4 py-2 bg-accent-blue text-canvas font-medium rounded-lg text-sm hover:bg-accent-blue/90 disabled:opacity-40 transition-colors"
            >
              <Save size={14} />
              {saving ? 'Saving…' : saved ? '✓ Saved' : 'Save Threshold Changes'}
            </button>
          </div>

          {/* Alert-type overrides table */}
          <div className="bg-canvas-overlay border border-border rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-border">
              <h2 className="text-sm font-medium">Alert-Type Override Thresholds</h2>
              <p className="text-xs text-fg-muted mt-0.5">
                These override global thresholds for specific alert types.
                Defined in <code className="text-accent-purple">scoring/threshold_manager.py</code>.
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border text-fg-muted">
                    <th className="text-left px-4 py-2 font-medium">Alert Type</th>
                    <th className="text-right px-4 py-2 font-medium text-accent-red">Suppress ≥</th>
                    <th className="text-right px-4 py-2 font-medium text-accent-yellow">Downgrade ≥</th>
                    <th className="text-right px-4 py-2 font-medium text-accent-blue">Escalate ≤</th>
                    <th className="text-left px-4 py-2 font-medium">Note</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {overrides.map(o => (
                    <tr key={o.alert_type} className="hover:bg-canvas-subtle transition-colors">
                      <td className="px-4 py-2.5 font-mono text-fg">{o.alert_type}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-accent-red">
                        {o.suppress >= 999 ? '—' : o.suppress}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-accent-yellow">
                        {o.downgrade >= 999 ? '—' : o.downgrade}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-accent-blue">{o.escalate}</td>
                      <td className="px-4 py-2.5 text-fg-muted">
                        {o.suppress >= 999 ? 'Never suppress' : ''}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
