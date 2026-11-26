/** Types for design projects and AI briefs (mirrors packages/contracts/openapi.json). */

export type BriefStatus = "DRAFT" | "APPROVED" | "REJECTED" | "NEEDS_REVIEW";
export type ContentKind = "verified_fact" | "proposed_copy" | "assumption";

export interface DesignProject {
  id: string;
  prospect_id: string;
  audit_id: string | null;
  status: string;
  brief_schema_version: string | null;
  prompt_version: string | null;
  model: string | null;
  current_version: number;
  created_at: string;
}

export interface BriefSection {
  block: string;
  content_kind: ContentKind;
  heading: string;
  body: string;
  items: { title: string; text: string }[];
  cta_label: string;
  fact_ids: string[];
}

export interface BriefPage {
  slug: string;
  title: string;
  goal: string;
  sections: BriefSection[];
}

export interface BriefContent {
  schema_version: string;
  business_summary: string;
  facts_used: string[];
  assumptions: { statement: string; needs_owner_review: boolean }[];
  audience_hypotheses: string[];
  design_direction: { positioning: string; tone: string; visual_principles: string[] };
  palette: Record<string, string>;
  typography: { heading: string; body: string };
  trust_page_label: string;
  pages: BriefPage[];
  image_briefs: { page: string; description: string; alt_text: string }[];
  accessibility: string[];
}

export interface Brief {
  id: string;
  design_project_id: string;
  version: number;
  status: BriefStatus;
  brief: BriefContent | null;
  schema_version: string;
  prompt_version: string;
  model: string;
  facts_snapshot: {
    facts: { id: string; field: string; value: string; source: string | null }[];
    audit_findings: { code: string; title: string }[];
  };
  validation_issues: { code: string; location: string; detail: string }[];
  attempts: number;
  input_tokens: number;
  output_tokens: number;
  cost_milliminor: number;
  review_notes: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface ValidationCheck {
  code: string;
  status: "pass" | "fail" | "unknown";
  severity: "critical" | "major" | "minor";
  message: string;
  page: string | null;
  viewport: string | null;
  evidence: unknown;
}

export interface Validation {
  id: string;
  render_id: string;
  status: "READY" | "NEEDS_REVISION";
  validator_version: string;
  browser_version: string | null;
  site_sha256: string;
  report: {
    status: string;
    summary: {
      checks: number;
      passed: number;
      failed_critical: number;
      failed_major: number;
      failed_minor: number;
      unknown: number;
    };
    repairable: string[];
    checks: ValidationCheck[];
  };
  screenshots: { slug: string; viewport: string; key: string; sha256: string; bytes: number }[];
  created_at: string;
}

export interface DesignDetail {
  project: DesignProject;
  briefs: Brief[];
  renders: Render[];
  validations: Validation[];
}

const SEVERITY_ORDER = { critical: 0, major: 1, minor: 2 } as const;

/** Failed and unknown checks, most severe first. */
export function problems(v: Validation): ValidationCheck[] {
  return v.report.checks
    .filter((c) => c.status !== "pass")
    .sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);
}

export const KIND_LABEL: Record<ContentKind, string> = {
  verified_fact: "Verified fact",
  proposed_copy: "Proposed copy",
  assumption: "Assumption (confirm)",
};

/** Cost in US dollars from thousandths of a cent. */
export function formatCost(milliminor: number): string {
  return "$" + (milliminor / 100_000).toFixed(4);
}

export const PAGE_SLUGS = ["home", "services", "about", "trust", "inquiry", "contact"] as const;
export const VIEWPORTS = ["desktop", "tablet", "mobile"] as const;

/**
 * Same policy as next.config.ts. The sandbox keeps the dashboard origin only so in-frame links carry the
 * session cookie; scripts, forms, popups and top navigation stay blocked (and the CSP allows no script).
 */
export const CONCEPT_CSP = [
  "sandbox allow-same-origin",
  "default-src 'none'",
  "style-src 'unsafe-inline'",
  "img-src data:",
  "form-action 'none'",
  "base-uri 'none'",
  "frame-ancestors 'self'",
].join("; ");

export interface RenderPage {
  slug: string;
  title: string;
  key: string;
  sha256: string;
  bytes: number;
}

export interface Render {
  id: string;
  design_project_id: string;
  brief_id: string;
  version: number;
  renderer_version: string;
  status: "RENDERED" | "APPROVED" | "REJECTED" | "FAILED";
  is_active: boolean;
  variant: string;
  manifest: {
    safe_mode?: boolean;
    repair_of?: string | null;
    pages: RenderPage[];
    assets: { id: string; key: string; license: string; sha256: string }[];
    brief_version: number;
    site_sha256: string;
  };
  scan_issues: { code: string; detail: string; page?: string }[];
  review_notes: string | null;
  reviewed_at: string | null;
  created_at: string;
}
