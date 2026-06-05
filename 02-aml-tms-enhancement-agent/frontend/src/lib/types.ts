// TypeScript types mirroring the Python TypedDicts in agent/state.py

export type RiskTier = 'LOW' | 'MEDIUM' | 'HIGH' | 'VERY_HIGH'
export type Decision = 'SUPPRESS' | 'DOWNGRADE' | 'PASS_THROUGH' | 'ESCALATE'
export type Priority = 'HIGH' | 'MEDIUM' | 'LOW' | 'NONE'
export type QueueAction = 'suppressed' | 'downgraded' | 'queued' | 'escalated' | 'error'

export interface RawAlert {
  alert_id: string
  customer_id: string
  alert_type: string
  triggered_rule: string
  severity: string
  amount: number
  currency: string
  alert_date: string
  transaction_ids: string[]
  tms_vendor: string
  raw_data: Record<string, unknown>
}

export interface RoutingDecision {
  decision: Decision
  fp_probability: number      // 0–100
  confidence: number          // 0–1
  primary_reason: string
  suppression_factors: string[]
  pass_through_factors: string[]
  recommended_priority: Priority
  regulatory_override: boolean
  regulatory_override_reason: string
}

export interface AuditEntry {
  timestamp: string
  actor: string
  action: string
  details: Record<string, unknown>
  data_sources: string[]
  ai_model_used: string | null
}

export interface ScoreBreakdown {
  rule_based_score: number
  rule_based_weight: number
  rule_based_contribution: number
  llm_score: number
  llm_weight: number
  llm_contribution: number
  historical_score: number
  historical_weight: number
  historical_contribution: number
  composite_fp_score: number
}

export interface ScoredAlert {
  alert_id: string
  customer_id: string
  raw_alert: RawAlert
  routing: RoutingDecision
  queue_action: QueueAction
  composite_fp_score: number
  score_breakdown: ScoreBreakdown
  rule_based_fp_score: number
  rule_based_factors: string[]
  llm_fp_probability: number
  llm_analysis_narrative: string
  suppression_id: string | null
  suppression_timestamp: string | null
  suppression_justification: string | null
  suppression_review_date: string | null
  audit_trail: AuditEntry[]
  scoring_notes: string[]
  ingested_at: string
  scored_at: string | null
  processing_time_ms: number | null
  errors: string[]
  fallback_to_manual: boolean
}

export interface SuppressionRecord {
  suppression_id: string
  alert_id: string
  customer_id: string
  alert_type: string
  fp_probability: number
  confidence: number
  primary_reason: string
  suppression_factors: string[]
  pass_through_factors: string[]
  justification_narrative: string
  score_breakdown: ScoreBreakdown
  suppressed_at: string
  mandatory_review_date: string
  review_status: 'PENDING' | 'APPROVED' | 'REVERSED'
  reviewed_by: string | null
  review_outcome: string | null
}

export interface Thresholds {
  suppress: number
  downgrade: number
  escalate: number
}

export interface AlertTypeOverride {
  alert_type: string
  suppress: number
  downgrade: number
  escalate: number
}

export interface Metrics {
  total_processed: number
  suppressed: number
  downgraded: number
  passed_through: number
  escalated: number
  suppression_rate: number
  avg_fp_probability: number
  analyst_hours_saved: number
  pending_90day_review: number
  session_decision_distribution: Record<string, number>
  session_fp_probabilities: number[]
  session_alert_count: number
}
