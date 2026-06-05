'use client'

import { useState, useEffect } from 'react'
import { Search } from 'lucide-react'
import { fetchScoredAlerts } from '@/lib/api'
import type { ScoredAlert } from '@/lib/types'
import DecisionBadge from '@/components/DecisionBadge'
import ScoreGauge from '@/components/ScoreGauge'

function ScoreBar({ label, score, contribution, color }: {
  label: string; score: number; contribution: number; color: string
}) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-fg-muted">
        <span>{label}</span>
        <span className="font-mono">{score.toFixed(0)} → <span style={{ color }}>{contribution.toFixed(1)}</span></span>
      </div>
      <div className="h-1.5 bg-canvas-subtle rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${contribution}%`, background: color }} />
      </div>
    </div>
  )
}

export default function DetailPage() {
  const [alerts, setAlerts] = useState<ScoredAlert[]>([])
  const [selected, setSelected] = useState<string>('')
  const [showAudit, setShowAudit] = useState(false)

  useEffect(() => {
    fetchScoredAlerts()
      .then(res => {
        setAlerts(res.alerts)
        if (res.alerts.length > 0) setSelected(res.alerts[0].alert_id)
      })
      .catch(() => {})
  }, [])

  const result = alerts.find(a => a.alert_id === selected)
  const routing = result?.routing

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center gap-2">
        <Search className="text-accent-blue" size={20} />
        <h1 className="text-xl font-semibold">Alert Scoring Detail</h1>
      </div>

      {alerts.length === 0 ? (
        <div className="bg-canvas-overlay border border-border rounded-lg p-8 text-center text-sm text-fg-muted">
          No scored alerts yet. Use the <strong>Live Queue</strong> tab to score alerts.
        </div>
      ) : (
        <>
          {/* Alert selector */}
          <select
            value={selected}
            onChange={e => setSelected(e.target.value)}
            className="bg-canvas-overlay border border-border rounded-lg px-3 py-2 text-sm text-fg focus:outline-none focus:border-accent-blue"
          >
            {alerts.map(a => (
              <option key={a.alert_id} value={a.alert_id}>
                {a.alert_id} — {a.queue_action?.toUpperCase()} (FP: {routing?.fp_probability?.toFixed(0) ?? '?'}%)
              </option>
            ))}
          </select>

          {result && routing && (
            <>
              {/* Decision header */}
              <div className="flex items-center gap-3">
                <DecisionBadge decision={routing.decision} size="md" />
                <p className="text-sm text-fg-muted">{routing.primary_reason}</p>
              </div>

              {/* Main grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Gauge */}
                <div className="bg-canvas-overlay border border-border rounded-lg p-6 flex flex-col items-center justify-center">
                  <ScoreGauge value={routing.fp_probability} decision={routing.decision} />
                  <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
                    {[
                      ['Decision', routing.decision],
                      ['Confidence', `${(routing.confidence * 100).toFixed(0)}%`],
                      ['Priority', routing.recommended_priority],
                      ['Action', result.queue_action],
                    ].map(([label, val]) => (
                      <div key={label} className="flex justify-between gap-2">
                        <span className="text-fg-muted">{label}</span>
                        <span className="text-fg font-mono">{val}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Score breakdown */}
                <div className="bg-canvas-overlay border border-border rounded-lg p-5">
                  <h3 className="text-sm font-medium mb-4">Score Component Breakdown</h3>
                  {result.score_breakdown ? (
                    <div className="space-y-4">
                      <ScoreBar
                        label="Rule-Based (30% weight)"
                        score={result.score_breakdown.rule_based_score}
                        contribution={result.score_breakdown.rule_based_contribution}
                        color="#58a6ff"
                      />
                      <ScoreBar
                        label="LLM Analysis (50% weight)"
                        score={result.score_breakdown.llm_score}
                        contribution={result.score_breakdown.llm_contribution}
                        color="#3fb950"
                      />
                      <ScoreBar
                        label="Historical Patterns (20% weight)"
                        score={result.score_breakdown.historical_score}
                        contribution={result.score_breakdown.historical_contribution}
                        color="#e3b341"
                      />
                      <div className="pt-2 border-t border-border flex justify-between text-sm">
                        <span className="text-fg-muted font-medium">Composite FP Score</span>
                        <span className="font-mono font-bold text-fg">
                          {result.score_breakdown.composite_fp_score.toFixed(1)} / 100
                        </span>
                      </div>
                    </div>
                  ) : (
                    <p className="text-xs text-fg-muted">Score breakdown not available.</p>
                  )}
                </div>
              </div>

              {/* Factors */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-canvas-overlay border border-border rounded-lg p-4">
                  <h3 className="text-sm font-medium mb-3 text-accent-red">
                    Suppression Factors
                    <span className="text-xs text-fg-muted font-normal ml-2">evidence for FP</span>
                  </h3>
                  {routing.suppression_factors.length > 0 ? (
                    <ul className="space-y-1.5">
                      {routing.suppression_factors.map((f, i) => (
                        <li key={i} className="flex gap-2 text-xs text-fg-muted">
                          <span className="text-accent-red flex-shrink-0">•</span>{f}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-fg-subtle">None</p>
                  )}
                </div>

                <div className="bg-canvas-overlay border border-border rounded-lg p-4">
                  <h3 className="text-sm font-medium mb-3 text-accent-green">
                    Pass-Through Factors
                    <span className="text-xs text-fg-muted font-normal ml-2">evidence against suppression</span>
                  </h3>
                  {routing.pass_through_factors.length > 0 ? (
                    <ul className="space-y-1.5">
                      {routing.pass_through_factors.map((f, i) => (
                        <li key={i} className="flex gap-2 text-xs text-fg-muted">
                          <span className="text-accent-green flex-shrink-0">•</span>{f}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-fg-subtle">None</p>
                  )}
                </div>
              </div>

              {/* LLM narrative */}
              {result.llm_analysis_narrative && (
                <div className="bg-canvas-overlay border border-border rounded-lg p-4">
                  <h3 className="text-sm font-medium mb-2">LLM Analysis Narrative</h3>
                  <p className="text-sm text-fg-muted leading-relaxed">{result.llm_analysis_narrative}</p>
                </div>
              )}

              {/* Suppression justification */}
              {result.suppression_justification && (
                <div className="bg-accent-yellow/10 border border-accent-yellow/30 rounded-lg p-4">
                  <h3 className="text-sm font-medium mb-2 text-accent-yellow">
                    Regulatory Suppression Justification
                    <span className="text-xs font-normal ml-2 text-fg-muted">(stored in audit log)</span>
                  </h3>
                  <p className="text-sm text-fg-muted leading-relaxed">{result.suppression_justification}</p>
                  <p className="text-xs text-accent-yellow mt-2">90-day review due: {result.suppression_review_date}</p>
                </div>
              )}

              {/* Rule-based factors */}
              {(result.rule_based_factors ?? []).length > 0 && (
                <div className="bg-canvas-overlay border border-border rounded-lg p-4">
                  <h3 className="text-sm font-medium mb-2">Rule-Based Pre-Filter Signals</h3>
                  <ul className="space-y-1">
                    {result.rule_based_factors.map((f, i) => (
                      <li key={i} className="text-xs text-fg-muted">• {f}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Audit trail */}
              <div className="bg-canvas-overlay border border-border rounded-lg overflow-hidden">
                <button
                  onClick={() => setShowAudit(v => !v)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-canvas-subtle transition-colors text-sm font-medium"
                >
                  Scoring Audit Trail ({(result.audit_trail ?? []).length} entries)
                  <span className="text-fg-muted text-xs">{showAudit ? '▲ hide' : '▼ show'}</span>
                </button>
                {showAudit && (
                  <div className="border-t border-border divide-y divide-border">
                    {(result.audit_trail ?? []).map((entry, i) => (
                      <div key={i} className="px-4 py-2.5">
                        <div className="flex items-center gap-3 text-xs">
                          <span className="text-fg-subtle font-mono">{entry.timestamp.slice(11, 19)}</span>
                          <span className="font-medium text-fg">{entry.action}</span>
                          {entry.ai_model_used && (
                            <span className="text-accent-purple text-xs">{entry.ai_model_used}</span>
                          )}
                        </div>
                        <div className="text-xs text-fg-muted mt-0.5 pl-16 font-mono">
                          {JSON.stringify(entry.details).slice(0, 120)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
