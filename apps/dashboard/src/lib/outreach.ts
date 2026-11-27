/** Types for compliance policies, contacts, outreach messages and replies (mirrors packages/contracts). */

export interface Policy {
  id: string;
  country_code: string;
  recipient_type: string;
  message_category: string;
  version: string;
  status: "DRAFT" | "IN_REVIEW" | "ACTIVE" | "RETIRED";
  rules: Record<string, unknown>;
  reviewer_name: string | null;
  reviewer_qualification: string | null;
  reviewed_at: string | null;
  effective_from: string | null;
  effective_to: string | null;
  source_references: string[];
}

export interface Contact {
  id: string;
  prospect_id: string | null;
  email_masked: string;
  contact_name: string | null;
  recipient_type: string;
  role_function: string | null;
  source_url: string | null;
  country_code: string | null;
  verification_state: string;
  verification_method: string | null;
  suppressed: boolean;
}

export interface Check {
  n: number;
  code: string;
  ok: boolean;
  reason: string | null;
  severity: "hold" | "ineligible";
  detail: string;
}

export interface OutreachMessage {
  id: string;
  prospect_id: string;
  email_contact_id: string | null;
  proposal_id: string | null;
  provider: string;
  provider_message_id: string | null;
  subject: string | null;
  status: string;
  error_code: string | null;
  cancelled_reason: string | null;
  attempt_count: number;
  approved_at: string | null;
  accepted_at: string | null;
  last_event_at: string | null;
  created_at: string;
  body: string | null;
  assessment: {
    decision: "ELIGIBLE" | "INELIGIBLE" | "HOLD" | "HUMAN_REVIEW";
    reason_codes: string[];
    checks: Check[];
    assessed_at: string;
    policy_version: string | null;
    legal_basis: string | null;
  } | null;
}

export interface ReplyItem {
  id: string;
  prospect_id: string | null;
  outreach_message_id: string | null;
  received_at: string;
  classification: string | null;
  subject: string | null;
  summary: string | null;
  needs_human_review: boolean;
  handled_at: string | null;
}

export interface SuppressionSummary {
  total: number;
  by_reason: Record<string, number>;
  recent: { reason: string; created_at: string; scope: string }[];
  note: string;
}

export const CHECK_LABEL: Record<string, string> = {
  country_known: "Country known",
  recipient_type_known: "Recipient type classified",
  message_category_known: "Message category identified",
  reviewed_policy: "Legally reviewed policy is active",
  policy_permits: "Policy permits this message",
  legal_basis_evidence: "Legal basis / consent evidence recorded",
  data_source_permitted: "Data source and use permitted",
  email_verified: "Email from an allowed source (not guessed)",
  not_suppressed: "Not suppressed",
  no_opt_out_or_dnc: "No opt-out, bounce, complaint or do-not-contact",
  sender_identity_and_disclosures: "Sender identity and disclosures",
  unsubscribe_live: "Unsubscribe mechanism live",
  provider_permits_traffic: "Provider permits this traffic",
  sender_domain_authenticated: "Sender domain authenticated",
  rate_and_budget: "Within rate and budget limits",
  not_paused: "No pause switch active",
  preview_valid: "Preview valid and labelled",
  message_truthful: "Message truthful and non-deceptive",
};

/** Template for a new policy's rules; every value must be confirmed by qualified counsel. */
export const RULES_TEMPLATE = {
  permitted: false,
  legal_bases: ["legitimate_interest"],
  consent_required: true,
  disclosures: ["sender_identity", "physical_address", "unsubscribe", "concept_notice"],
  unsubscribe: "visible link + RFC 8058 one-click; honour immediately",
  retention_days: 365,
  next_review: "2027-06-01",
  personal_data_reviewed: false,
};
