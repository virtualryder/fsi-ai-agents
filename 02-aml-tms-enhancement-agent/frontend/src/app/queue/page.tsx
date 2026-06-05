'use client'

import { useState } from 'react'
import { Zap, RefreshCw, ChevronDown, ChevronRight } from 'lucide-react'
import { fetchPendingAlerts, scoreAlert, scoreAllAlerts, pollJob, fetchScoredAlerts } from '@/lib/api'
import type { RawAlert, ScoredAlert } from '@/lib/types'
import DecisionBadge from '@/components/DecisionBadge'

export default function QueuePage() {
  const [pending, setPending] = useState<RawAlert[]>([])
  const [scored, setScored] = useState<ScoredAlert[]>([])
  const [loading, setLoading] = useState(false)
  const [scoring, setScoring] = useState<Set<string>>(new Set())
  const [jobProgress, setJobProgress] = useState<{ completed: number; total: number } | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)

  const toggle = (id: string) =>
    setExpanded(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s })

  async function loadPending() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetchPendingAlerts()
      setPending(res.alerts)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function scoreSingle(alertId: string) {
    setScoring(prev => new Set(prev).add(alertId))
    setError(null)
    try {
      const result = await scoreAlert(alertId)
      setScored(prev => {
        const filtered = prev.filter(a => a.alert_id !== alertId)
        return [result, ...filtered]
      })
    } catch (e: any) {
      setError(`Failed to score ${alertId}: ${e.message}`)
    } finally {
      setScoring(prev => { const s = new Set(prev); s.delete(alertId); return s })
    }
  }

  async function scoreAll() {
    setError(null)
    try {
      const job = await scoreAllAlerts()
      setJobProgress({ completed: 0, total: job.total })

      // Poll until done
      const poll = async () => {
        const status = await pollJob(job.job_id)
        setJobProgress({ completed: status.completed, total: status.total })
        if (status.status !== 'COMPLETE') {
          setTimeout(poll, 1500)
        } else {
          const res = await fetchScoredAlerts()
          setScored(res.alerts)
          setJobProgress(null)
        }
      }
      setTimeout(poll, 1500)
    } catch (e: any) {
      setError(e.message)
    }
  }

  const scoredIds = new Set(scored.map(a => a.alert_id))

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 mb-1">
          <Zap className="text-accent-blue" size={20} />
          <h1 className="text-xl font-semibold">Live Alert Scoring Queue</h1>
        </div>
        <p className="text-sm text-fg-muted">
          Process pending TMS alerts through the AI false positive scoring pipeline.
          Surviving alerts are forwarded to the Financial Crime Investigation Agent.
        </p>
      </div>

      {error && (
        <div className="bg-accent-red/10 border border-accent-red/30 rounded-lg px-4 py-3 text-sm text-accent-red">
          {error}
        </div>
      )}

      {/* Controls */}
      <div className="flex gap-3">
        <button
          onClick={loadPending}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-canvas-overlay border border-border rounded-lg text-sm hover:bg-canvas-subtle disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Load Pending TMS Alerts
        </button>

        <button
          onClick={scoreAll}
          disabled={pending.length === 0 || jobProgress !== null}
          className="flex items-center gap-2 px-4 py-2 bg-accent-blue text-canvas font-medium rounded-lg text-sm hover:bg-accent-blue/90 disabled:opacity-40 transition-colors"
        >
          <Zap size={14} />
          Score All ({pending.length})
        </button>
      </div>

      {/* Job progress */}
      {jobProgress && (
        <div className="bg-canvas-overlay border border-border rounded-lg p-4">
          <div className="flex justify-between text-sm mb-2">
            <span className="text-fg-muted">Scoring alerts…</span>
            <span className="font-mono text-fg">{jobProgress.completed} / {jobProgress.total}</span>
          </div>
          <div className="h-1.5 bg-canvas-subtle rounded-full overflow-hidden">
            <div
              className="h-full bg-accent-blue transition-all duration-300"
              style={{ width: `${(jobProgress.completed / jobProgress.total) * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* Pending alerts */}
      {pending.length > 0 && (
        <section>
          <h2 className="text-sm font-medium text-fg-muted uppercase tracking-wider mb-3">
            Pending — {pending.length} alerts awaiting scoring
          </h2>
          <div className="space-y-2">
            {pending.map(alert => {
              const isExpanded = expanded.has(alert.alert_id)
              const isScoring = scoring.has(alert.alert_id)
              const isScored = scoredIds.has(alert.alert_id)

              return (
                <div
                  key={alert.alert_id}
                  className="bg-canvas-overlay border border-border rounded-lg overflow-hidden"
                >
                  <div className="flex items-center gap-3 px-4 py-3">
                    <button onClick={() => toggle(alert.alert_id)} className="text-fg-muted hover:text-fg">
                      {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-sm text-fg">{alert.alert_id}</span>
                        <span className="text-xs px-2 py-0.5 bg-canvas-subtle border border-border rounded text-fg-muted">
                          {alert.alert_type}
                        </span>
                        <span className="text-xs px-2 py-0.5 bg-canvas-subtle border border-border rounded text-fg-muted">
                          {alert.tms_vendor.toUpperCase()}
                        </span>
                      </div>
                      <p className="text-xs text-fg-muted mt-0.5">
                        ${alert.amount.toLocaleString()} · {alert.severity} · {alert.alert_date}
                      </p>
                    </div>
                    {isScored ? (
                      <span className="text-xs text-accent-green">✓ Scored</span>
                    ) : (
                      <button
                        onClick={() => scoreSingle(alert.alert_id)}
                        disabled={isScoring}
                        className="text-xs px-3 py-1.5 bg-canvas-subtle border border-border rounded hover:bg-border disabled:opacity-50 transition-colors"
                      >
                        {isScoring ? 'Scoring…' : 'Score'}
                      </button>
                    )}
                  </div>

                  {isExpanded && (
                    <div className="border-t border-border px-4 py-3 bg-canvas">
                      <pre className="text-xs text-fg-muted font-mono whitespace-pre-wrap">
                        {JSON.stringify({ ...alert, raw_data: alert.raw_data }, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* Scored results */}
      {scored.length > 0 && (
        <section>
          <h2 className="text-sm font-medium text-fg-muted uppercase tracking-wider mb-3">
            Results — {scored.length} alerts scored
          </h2>
          <div className="space-y-2">
            {scored.map(result => {
              const routing = result.routing ?? {}
              const decision = routing.decision ?? 'PASS_THROUGH'
              const fp = routing.fp_probability ?? 0
              const isExpanded = expanded.has(`result-${result.alert_id}`)

              const borderColor: Record<string, string> = {
                SUPPRESS: 'border-l-accent-red',
                DOWNGRADE: 'border-l-accent-yellow',
                PASS_THROUGH: 'border-l-accent-green',
                ESCALATE: 'border-l-accent-blue',
              }

              return (
                <div
                  key={result.alert_id}
                  className={`bg-canvas-overlay border border-border border-l-4 ${borderColor[decision] ?? ''} rounded-lg overflow-hidden`}
                >
                  <div className="flex items-center gap-3 px-4 py-3">
                    <button onClick={() => toggle(`result-${result.alert_id}`)} className="text-fg-muted hover:text-fg">
                      {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-sm text-fg">{result.alert_id}</span>
                        <DecisionBadge decision={decision} />
                      </div>
                      <p className="text-xs text-fg-muted mt-0.5 truncate">
                        FP: {fp.toFixed(0)}% · {result.queue_action} · {result.processing_time_ms ?? '?'}ms
                      </p>
                      <p className="text-xs text-fg-subtle truncate">{routing.primary_reason}</p>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="border-t border-border px-4 py-3 bg-canvas space-y-3">
                      <div>
                        <p className="text-xs font-medium text-fg-muted mb-1">Suppression factors</p>
                        {(routing.suppression_factors ?? []).map((f: string, i: number) => (
                          <p key={i} className="text-xs text-fg-muted">• {f}</p>
                        ))}
                      </div>
                      {(routing.pass_through_factors ?? []).length > 0 && (
                        <div>
                          <p className="text-xs font-medium text-fg-muted mb-1">Pass-through factors</p>
                          {routing.pass_through_factors.map((f: string, i: number) => (
                            <p key={i} className="text-xs text-fg-muted">• {f}</p>
                          ))}
                        </div>
                      )}
                      {result.suppression_review_date && (
                        <p className="text-xs text-accent-yellow">
                          90-day review due: {result.suppression_review_date}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      )}

      {pending.length === 0 && scored.length === 0 && (
        <div className="text-center py-16 text-fg-muted text-sm">
          Click <strong>Load Pending TMS Alerts</strong> to begin.
        </div>
      )}
    </div>
  )
}
