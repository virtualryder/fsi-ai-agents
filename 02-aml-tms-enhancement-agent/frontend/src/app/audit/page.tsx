'use client'

import { useState, useEffect } from 'react'
import { ClipboardList, ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react'
import { fetchSuppressionLog } from '@/lib/api'
import type { SuppressionRecord } from '@/lib/types'

function ReviewStatusBadge({ status }: { status: string }) {
  const cfg: Record<string, string> = {
    PENDING:  'bg-accent-yellow/20 text-accent-yellow border-accent-yellow/40',
    APPROVED: 'bg-accent-green/20 text-accent-green border-accent-green/40',
    REVERSED: 'bg-accent-red/20 text-accent-red border-accent-red/40',
  }
  return (
    <span className={`text-xs font-medium px-2 py-0.5 border rounded ${cfg[status] ?? cfg.PENDING}`}>
      {status}
    </span>
  )
}

export default function AuditPage() {
  const [records, setRecords] = useState<SuppressionRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const toggle = (id: string) =>
    setExpanded(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s })

  useEffect(() => {
    fetchSuppressionLog(90)
      .then(res => setRecords(res.records))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const pending = records.filter(r => r.review_status === 'PENDING')

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <ClipboardList className="text-accent-blue" size={20} />
          <h1 className="text-xl font-semibold">Suppression Audit Trail</h1>
        </div>
        <p className="text-sm text-fg-muted">
          All alert suppression decisions are recorded here. Suppressions must be reviewed
          within <strong>90 days</strong> per SR 11-7 model monitoring requirements.
        </p>
      </div>

      {pending.length > 0 && (
        <div className="flex items-start gap-3 bg-accent-yellow/10 border border-accent-yellow/30 rounded-lg px-4 py-3">
          <AlertTriangle className="text-accent-yellow mt-0.5 flex-shrink-0" size={16} />
          <p className="text-sm text-accent-yellow">
            <strong>{pending.length}</strong> suppression{pending.length !== 1 ? 's' : ''} pending BSA Officer review.
          </p>
        </div>
      )}

      {loading ? (
        <div className="text-sm text-fg-muted">Loading suppression records…</div>
      ) : records.length === 0 ? (
        <div className="bg-canvas-overlay border border-border rounded-lg p-8 text-center text-sm text-fg-muted">
          No suppression records in the last 90 days.
          Score some alerts in the <strong>Live Queue</strong> to generate records.
        </div>
      ) : (
        <div className="space-y-2">
          {[...records].reverse().map(record => {
            const isExpanded = expanded.has(record.suppression_id)
            return (
              <div key={record.suppression_id} className="bg-canvas-overlay border border-border rounded-lg overflow-hidden">
                {/* Header row */}
                <button
                  onClick={() => toggle(record.suppression_id)}
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-canvas-subtle transition-colors text-left"
                >
                  {isExpanded ? <ChevronDown size={14} className="text-fg-muted" /> : <ChevronRight size={14} className="text-fg-muted" />}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-xs text-fg">{record.suppression_id}</span>
                      <span className="text-xs text-fg-muted">→ Alert: {record.alert_id}</span>
                      <ReviewStatusBadge status={record.review_status} />
                    </div>
                    <p className="text-xs text-fg-muted mt-0.5">
                      FP: {record.fp_probability.toFixed(0)}% · Confidence: {(record.confidence * 100).toFixed(0)}% ·
                      Review due: <span className={record.review_status === 'PENDING' ? 'text-accent-yellow' : 'text-fg-muted'}>
                        {record.mandatory_review_date}
                      </span>
                    </p>
                  </div>
                </button>

                {/* Expanded detail */}
                {isExpanded && (
                  <div className="border-t border-border bg-canvas px-4 py-4 space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      {/* Justification */}
                      <div className="md:col-span-2 space-y-3">
                        <div>
                          <p className="text-xs font-medium text-fg-muted mb-1">Suppression Justification</p>
                          <p className="text-sm text-fg leading-relaxed">
                            {record.justification_narrative || record.primary_reason}
                          </p>
                        </div>
                        {record.suppression_factors.length > 0 && (
                          <div>
                            <p className="text-xs font-medium text-fg-muted mb-1">Key Suppression Factors</p>
                            <ul className="space-y-0.5">
                              {record.suppression_factors.map((f, i) => (
                                <li key={i} className="text-xs text-fg-muted">• {f}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {record.pass_through_factors.length > 0 && (
                          <div>
                            <p className="text-xs font-medium text-fg-muted mb-1">Factors Considered & Outweighed</p>
                            <ul className="space-y-0.5">
                              {record.pass_through_factors.map((f, i) => (
                                <li key={i} className="text-xs text-fg-muted">• {f}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>

                      {/* Sidebar */}
                      <div className="space-y-3">
                        <div className="bg-canvas-overlay border border-border rounded-lg p-3 space-y-2">
                          {[
                            ['Alert ID', record.alert_id],
                            ['Customer', record.customer_id],
                            ['Alert Type', record.alert_type],
                            ['FP Probability', `${record.fp_probability.toFixed(0)}%`],
                            ['Confidence', `${(record.confidence * 100).toFixed(0)}%`],
                            ['Suppressed', record.suppressed_at.slice(0, 10)],
                            ['Review Due', record.mandatory_review_date],
                          ].map(([label, val]) => (
                            <div key={label} className="flex justify-between text-xs">
                              <span className="text-fg-muted">{label}</span>
                              <span className="text-fg font-mono">{val}</span>
                            </div>
                          ))}
                        </div>

                        {/* BSA Officer actions */}
                        <div className="space-y-2">
                          <p className="text-xs text-fg-muted">BSA Officer Actions</p>
                          <div className="flex gap-2">
                            <button className="flex-1 text-xs py-1.5 bg-accent-green/20 text-accent-green border border-accent-green/40 rounded hover:bg-accent-green/30 transition-colors">
                              ✓ Approve
                            </button>
                            <button className="flex-1 text-xs py-1.5 bg-accent-red/20 text-accent-red border border-accent-red/40 rounded hover:bg-accent-red/30 transition-colors">
                              ✗ Reverse
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
