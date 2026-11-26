/** Types for campaigns, prospects, jobs and controls (mirrors packages/contracts/openapi.json). */

export type CampaignStatus = "DRAFT" | "ACTIVE" | "PAUSED" | "COMPLETED" | "ARCHIVED";

export interface Campaign {
  id: string;
  name: string;
  description: string | null;
  status: CampaignStatus;
  target_countries: string[];
  target_regions: string[];
  industries: string[];
  filters: { queries?: string[]; source_key?: string; region_code?: string | null };
  candidate_cap: number;
  daily_budget_minor: number;
  monthly_budget_minor: number;
  sending_mode: string;
  created_at: string;
  updated_at: string;
}

export interface CampaignDetail {
  campaign: Campaign;
  readiness: { code: string; ok: boolean; message: string }[];
  stats: { candidates: number; prospects: number; jobs: Record<string, number> };
}

export interface Prospect {
  id: string;
  business_name: string;
  verified_domain: string | null;
  branch_key: string;
  website_url: string | null;
  industry: string | null;
  country_code: string | null;
  state: string;
  qualification_score: number | null;
  qualification_band: string | null;
  do_not_contact: boolean;
  first_seen_at: string;
  last_verified_at: string | null;
  state_changed_at: string;
}

export interface ProspectPage {
  items: Prospect[];
  total: number;
  offset: number;
  limit: number;
}

export interface Component {
  weight: number;
  score: number | null;
  reason: string;
  evidence: Record<string, unknown>;
}

export interface Qualification {
  id: string;
  rubric_version: string;
  outcome: string;
  score: number | null;
  evidence_coverage: number;
  components: Record<string, Component>;
  reason_codes: string[];
  campaign_id: string | null;
  created_at: string;
}

export interface ProspectDetail {
  prospect: Prospect;
  facts: {
    fact_field: string;
    safe_value: string | null;
    source_type: string;
    source_name: string;
    source_url: string | null;
    retrieved_at: string;
    confidence: number;
    verification_method: string;
    terms_version: string | null;
  }[];
  verifications: {
    id: string;
    status: string;
    domain: string | null;
    final_url: string | null;
    reason_codes: string[];
    confidence: number | null;
    checked_at: string;
    origin: string;
  }[];
  place_ids: { provider: string; place_id: string; status: string }[];
  campaigns: { id: string; name: string; added_at: string }[];
  qualifications: Qualification[];
  merges: { from: string; into: string; reason: string; merged_at: string }[];
}

export interface Job {
  id: string;
  job_type: string;
  queue: string;
  status: string;
  attempts: number;
  max_attempts: number;
  entity_type: string | null;
  entity_id: string | null;
  available_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_code: string | null;
  error_message: string | null;
  correlation_id: string | null;
  result: Record<string, unknown> | null;
  created_at: string;
}

export interface Control {
  key: string;
  enabled: boolean;
  effective: boolean;
  description: string;
  reason: string | null;
  updated_at: string;
  updated_by_user_id: string | null;
  env_override: boolean;
}

export const COMPONENT_LABEL: Record<string, string> = {
  website_presence: "Website presence",
  mobile_experience: "Mobile experience",
  visual_hierarchy: "Visual hierarchy",
  navigation_clarity: "Navigation clarity",
  conversion_path: "Conversion path",
  business_fit: "Business fit",
  source_quality: "Source quality",
};

export function stateLabel(state: string): string {
  return state.toLowerCase().replaceAll("_", " ");
}
