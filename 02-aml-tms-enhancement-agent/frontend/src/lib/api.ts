import type {
  RawAlert, ScoredAlert, SuppressionRecord, Metrics, Thresholds, AlertTypeOverride,
} from './types'

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body?.detail ?? `${res.status} ${res.statusText}`)
  }
  return res.json()
}

// ── Alerts ─────────────────────────────────────────────────────────────────────

export async function fetchPendingAlerts(limit = 50): Promise<{ alerts: RawAlert[]; count: number }> {
  return req(`/api/alerts/pending?limit=${limit}`)
}

export async function scoreAlert(alertId: string): Promise<ScoredAlert> {
  return req(`/api/alerts/${alertId}/score`, { method: 'POST' })
}

export async function scoreAllAlerts(alertIds?: string[]): Promise<{ job_id: string; total: number; status: string }> {
  return req('/api/alerts/score-all', {
    method: 'POST',
    body: JSON.stringify({ alert_ids: alertIds ?? null }),
  })
}

export async function pollJob(jobId: string): Promise<{
  status: string
  total: number
  completed: number
  alert_ids: string[]
}> {
  return req(`/api/jobs/${jobId}`)
}

export async function fetchScoredAlerts(): Promise<{ alerts: ScoredAlert[]; count: number }> {
  return req('/api/alerts/scored')
}

export async function fetchScoredAlert(alertId: string): Promise<ScoredAlert> {
  return req(`/api/alerts/scored/${alertId}`)
}

// ── Metrics ────────────────────────────────────────────────────────────────────

export async function fetchMetrics(): Promise<Metrics> {
  return req('/api/metrics')
}

// ── Suppression ────────────────────────────────────────────────────────────────

export async function fetchSuppressionLog(days = 90): Promise<{ records: SuppressionRecord[]; count: number }> {
  return req(`/api/suppression?days=${days}`)
}

// ── Thresholds ─────────────────────────────────────────────────────────────────

export async function fetchThresholds(): Promise<{ thresholds: Thresholds; alert_type_overrides: AlertTypeOverride[] }> {
  return req('/api/thresholds')
}

export async function updateThresholds(t: Thresholds): Promise<{ thresholds: Thresholds; updated_at: string }> {
  return req('/api/thresholds', { method: 'PUT', body: JSON.stringify(t) })
}
