export type Role = 'patient' | 'staff' | 'clinician' | 'admin'

export interface User {
  id: string
  display_name: string
  role: Role
  clinic_id: string
  patient_id: string | null
}

export interface Patient {
  id: string
  display_code: string
  name: string
}

export interface GlanceItem {
  id: string
  entry_id: string
  text: string
  entity_type: string
  risk_reason: string
  risk_source: string | null
  risk_floor: number
  source_support: 'verified' | 'supported'
  provenance_id: string
  provenance_ids: string[]
  source_count: number
  multiple_sources: boolean
  unresolved: boolean
  status: string
  pinned: boolean
  accepted: boolean
  rejected: boolean
  highlighted: boolean
  score: number
  score_breakdown: { rule_score: number; learned_bonus: number; risk_floor: number }
}

export type TrustOutcome = 'verified' | 'supported' | 'review_required' | 'abstained'

export interface Glance {
  patient_id: string
  generated_at: string
  items: GlanceItem[]
  open_actions: GlanceItem[]
  policy_notice: string
}

export interface EntrySection {
  key: string
  content: string
  version: number
  visibility: string
}

export interface Comment {
  id: string
  content: string
  author_id: string
  mention_user_id: string | null
  assigned_to_id: string | null
  resolved: boolean
  created_at: string
}

export interface TimelineEntry {
  id: string
  patient_id: string
  author_role: string
  entry_type: string
  title: string
  current_version: number
  created_at: string
  sections: EntrySection[]
  comments: Comment[]
}

export interface Conflict {
  id: string
  patient_id: string
  entity_type: string
  status: string
  fact_a: { id: string; value: string; quote: string }
  fact_b: { id: string; value: string; quote: string }
}

export interface ProvenanceSource {
  id: string
  source_entry_id: string
  source_entry_title: string
  source_entry_type: string
  source_entry_created_at: string
  source_entry_version_id: string
  entry_version: number
  section_key: string
  start_offset: number
  end_offset: number
  quote: string
  original_quote: string | null
  original_start_offset: number
  original_end_offset: number
  match_method: string
  source_support: Extract<TrustOutcome, 'verified' | 'supported'>
  integrity: 'verified'
}

export interface Provenance extends ProvenanceSource {
  sources: ProvenanceSource[]
  source_count: number
  multiple_sources: boolean
}

export interface PatientFacingItem {
  id: string
  item_type: string
  content: string
  approved_at: string
}
