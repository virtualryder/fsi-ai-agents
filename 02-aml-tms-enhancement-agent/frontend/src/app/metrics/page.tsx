'use client'

import { useState, useEffect } from 'react'
import { BarChart2, RefreshCw } from 'lucide-react'
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, ReferenceLine, CartesianGrid,
} from 'recharts'
import { fetchMetrics } from '@/lib/api'
import type { Metrics } from '@/lib/types'
import MetricCard from '@/components/MetricCard'

const DECISION_COLORS: Record<string, string> = {
  SUPPRESS:     '#f85149',
  DOWNGRADE:    '#e3b341',
  PASS_THROUGH: '#3fb950',
  ESCALATE:     '#58a6ff',
  UNKNOWN:      '#484f58',
}

function buildHistogramData(probs: number[]) {
  const bins = Array.from({ length: 10 }, (_, i) => ({
    range: `${i * 10}–${(i + 1) * 10}`,
    count: 0,
  }))
  probs.forEach(p => {
    const idx = Math.min(Math.floor(p / 10), 9)
    bins[idx].count++
  })
  return bins
}

export default function MetricsPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [loading, setLoading] = useState(false)
  const [analytistCost, setAnalystCost] = useState(80_000)
  const [dailyAlerts, setDailyAlerts] = useState(500)

  async function load() {
    setLoading(true)
    try { setMetrics(await fetchMetrics()) }
    catch { /* no scored alerts yet */ }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const pieData = Object.entries(metrics?.session_decision_distribution ?? {}).map(([name, value]) => ({
    name,
    value,
  }))

  const histData = buildHistogramData(metrics?.session_fp_probabilities ?? [])

  const alertCost = (analytistCost / 2080) * (25 / 60)
  const annualSaved = dailyAlerts * 365 * 0.9 * alertCost * 0.55

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart2 className="text-accent-blue" size={20} />
          <h1 className="text-xl font-semibold">FP Reduction Metrics</h1>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 text-sm text-fg-muted hover:text-fg"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* KPI grid */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <MetricCard label="Total Processed" value={(metrics?.total_processed ?? 0).toLocaleString()} sub="Last 30 days" />
        <MetricCard label="Suppressed" value={(metrics?.suppressed ?? 0).toLocaleString()}
          sub={metrics ? `${(metrics.suppression_rate * 100).toFixed(0)}% of total` : '—'}
          valueColor="text-accent-red" />
        <MetricCard label="Downgraded" value={(metrics?.downgraded ?? 0).toLocaleString()}
          sub="Lower priority" valueColor="text-accent-yellow" />
        <MetricCard label="Analyst Hrs Saved" value={(metrics?.analyst_hours_saved ?? 0).toFixed(1) + 'h'}
          sub="@ 25 min / alert" valueColor="text-accent-green" />
        <MetricCard label="Escalated" value={(metrics?.escalated ?? 0).toLocaleString()}
          sub="Fast-tracked" valueColor="text-accent-blue" />
      </div>

      {/* Charts */}
      {metrics && metrics.session_alert_count > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Decision distribution */}
          <div className="bg-canvas-overlay border border-border rounded-lg p-4">
            <h3 className="text-sm font-medium mb-4">Decision Distribution</h3>
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90}>
                  {pieData.map(entry => (
                    <Cell key={entry.name} fill={DECISION_COLORS[entry.name] ?? '#484f58'} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 6 }}
                  labelStyle={{ color: '#f0f6fc' }}
                  itemStyle={{ color: '#8b949e' }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex flex-wrap gap-3 justify-center mt-2">
              {pieData.map(d => (
                <div key={d.name} className="flex items-center gap-1.5 text-xs text-fg-muted">
                  <div className="w-2.5 h-2.5 rounded-sm" style={{ background: DECISION_COLORS[d.name] }} />
                  {d.name} ({d.value})
                </div>
              ))}
            </div>
          </div>

          {/* FP probability histogram */}
          <div className="bg-canvas-overlay border border-border rounded-lg p-4">
            <h3 className="text-sm font-medium mb-4">FP Probability Distribution</h3>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={histData} margin={{ top: 4, right: 8, bottom: 0, left: -10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
                <XAxis dataKey="range" tick={{ fontSize: 10, fill: '#8b949e' }} />
                <YAxis tick={{ fontSize: 10, fill: '#8b949e' }} />
                <Tooltip
                  contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 6 }}
                  labelStyle={{ color: '#f0f6fc' }}
                  itemStyle={{ color: '#8b949e' }}
                />
                <Bar dataKey="count" fill="#58a6ff" radius={[2, 2, 0, 0]} />
                <ReferenceLine x="85–90" stroke="#f85149" strokeDasharray="3 3" label={{ value: 'Suppress', fill: '#f85149', fontSize: 10 }} />
                <ReferenceLine x="60–70" stroke="#e3b341" strokeDasharray="3 3" label={{ value: 'Downgrade', fill: '#e3b341', fontSize: 10 }} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        <div className="bg-canvas-overlay border border-border rounded-lg p-8 text-center text-sm text-fg-muted">
          Score some alerts in the <strong>Live Queue</strong> tab to see charts.
        </div>
      )}

      {/* ROI calculator */}
      <div className="bg-canvas-overlay border border-border rounded-lg p-4">
        <h3 className="text-sm font-medium mb-4">ROI Estimate</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <div>
              <label className="text-xs text-fg-muted block mb-1">Analyst fully-loaded annual cost ($)</label>
              <input
                type="number"
                value={analytistCost}
                onChange={e => setAnalystCost(Number(e.target.value))}
                className="w-full bg-canvas border border-border rounded px-3 py-1.5 text-sm text-fg focus:outline-none focus:border-accent-blue"
              />
            </div>
            <div>
              <label className="text-xs text-fg-muted block mb-1">Daily alert volume (bank-wide)</label>
              <input
                type="number"
                value={dailyAlerts}
                onChange={e => setDailyAlerts(Number(e.target.value))}
                className="w-full bg-canvas border border-border rounded px-3 py-1.5 text-sm text-fg focus:outline-none focus:border-accent-blue"
              />
            </div>
          </div>
          <div className="space-y-2 text-sm">
            {[
              ['Cost per alert reviewed', `$${alertCost.toFixed(2)}`],
              ['Annual FP cost (90% baseline)', `$${(dailyAlerts * 365 * 0.9 * alertCost).toLocaleString(undefined, { maximumFractionDigits: 0 })}`],
              ['Estimated annual savings', `$${annualSaved.toLocaleString(undefined, { maximumFractionDigits: 0 })}`],
              ['Alerts removed from queue/yr', `${Math.round(dailyAlerts * 365 * 0.9 * 0.55).toLocaleString()}`],
            ].map(([label, val]) => (
              <div key={label} className="flex justify-between items-center py-1.5 border-b border-border last:border-0">
                <span className="text-fg-muted">{label}</span>
                <span className="font-mono font-medium text-accent-green">{val}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
