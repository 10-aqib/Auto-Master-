/** Types for /api/v1/sources, /usage and /places (mirrors packages/contracts/openapi.json). */

export interface UsageWindow {
  requests: number;
  cost_minor: number;
}

export interface UsageSummary {
  provider: string;
  currency: string;
  today: UsageWindow;
  month: UsageWindow;
  daily_budget_minor: number | null;
  daily_request_cap: number | null;
  budget_ratio: number | null;
  cap_ratio: number | null;
  warning: boolean;
  exhausted: boolean;
}

export interface Source {
  key: string;
  display_name: string;
  source_type: string;
  status: "ENABLED" | "DISABLED";
  description: string;
  persistable_fields: string[];
  cache_rules: Record<string, number>;
  attribution_required: boolean;
  attribution_text: string | null;
  policy_urls: string[];
  terms_url: string | null;
  terms_version: string | null;
  terms_reviewed_at: string | null;
  review_notes: string | null;
  status_changed_at: string | null;
  status_reason: string | null;
  usable: boolean;
  blockers: string[];
  usage: UsageSummary | null;
}

export interface PlaceResult {
  place_id: string;
  identifier_id: string;
  display_name: string | null;
  formatted_address: string | null;
  business_status: string | null;
  google_maps_uri: string | null;
}

export interface SearchResponse {
  source_key: string;
  transient: true;
  attribution: { text: string; required: boolean; is_mock: boolean };
  sku: string;
  stored_place_ids: number;
  new_place_ids: number;
  places: PlaceResult[];
}

export interface Verification {
  id: string;
  status: "VERIFIED" | "HOLD" | "REJECTED";
  method: string;
  reason_codes: string[];
  confidence: number | null;
  candidate_url: string;
  final_url: string | null;
  domain: string | null;
  candidate_origin: string;
  evidence: Record<string, unknown>;
  checked_at: string;
  prospect_id: string | null;
  place_identifier_id: string | null;
}

export interface VerifyResponse {
  verification: Verification;
  prospect_id: string | null;
  place_obsolete: boolean;
}

export function formatMinor(minor: number, currency: string): string {
  return new Intl.NumberFormat("en", { style: "currency", currency }).format(minor / 100);
}

/** Human explanations for verification reason codes. */
export const REASON_TEXT: Record<string, string> = {
  no_website_listed: "No website is listed for this place.",
  robots_disallowed: "The site's robots.txt asks automated visitors not to read it.",
  robots_unavailable: "robots.txt could not be read, so the site was not checked.",
  redirected_off_site: "The website redirects to a different site.",
  parked_domain: "The domain looks parked or for sale.",
  structured_data_points_elsewhere: "The site's structured data names a different website.",
  no_expected_name: "No business name to compare with.",
  no_name_signals: "The page has no title or business name to compare.",
  weak_name_match: "The site's name only partly matches.",
  name_mismatch: "The site's name does not match.",
  not_html: "The address is not a web page.",
  place_id_obsolete: "Google no longer recognises this Place ID.",
  blocked_blocked_address: "Blocked: the address points to a private or internal network.",
};

export function reasonText(code: string): string {
  if (REASON_TEXT[code]) return REASON_TEXT[code];
  if (code.startsWith("unreachable_")) return "The website could not be reached.";
  if (code.startsWith("http_")) return `The website answered with HTTP ${code.slice(5)}.`;
  if (code.startsWith("blocked_")) return "Blocked for safety reasons.";
  return code;
}
