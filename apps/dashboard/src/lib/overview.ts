/** Types for overview analytics, review queues and operations (mirrors packages/contracts). */

export interface Budget {
  key: string;
  label: string;
  used: number;
  limit: number;
  unit: string;
  ratio: number | null;
  status: "ok" | "warning" | "stopped";
  note?: string;
}

export interface Overview {
  funnel: { stage: string; reached: number; current: number }[];
  holds_and_exits: Record<string, number>;
  messages: Record<string, number>;
  replies: Record<string, number>;
  outcomes: {
    sent: number;
    delivered: number;
    bounced: number;
    complained: number;
    replied: number;
    opted_out: number;
    interested: number;
    converted: number;
  };
  hold_reasons: { reason: string; count: number }[];
  by_campaign: { campaign_id: string; name: string; status: string; prospects: number }[];
  by_country: { country: string; prospects: number }[];
  spend_this_month: { provider: string; cost_cents: number; calls: number }[];
  budgets: Budget[];
  tracking_note: string;
}

export interface QueueItem {
  id: string;
  title: string;
  since: string;
  href: string;
}

export interface ReviewQueues {
  counts: Record<string, number>;
  queues: Record<string, QueueItem[]>;
}

export interface Operations {
  workers: { worker: string; queues: string[]; at: string }[] | null;
  worker_note: string;
  queues: { queue: string; status: string; count: number; oldest_age_seconds: number }[];
  dead_letter: number;
  failures_24h: { job_type: string; error_code: string | null; count: number }[];
  provider_errors_24h: { provider: string; count: number }[];
  budgets: Budget[];
  pauses: {
    key: string;
    enabled: boolean;
    effective: boolean;
    reason: string | null;
    updated_at: string;
    updated_by_user_id: string | null;
  }[];
  backups: { status: string; at: string | null; detail: string };
}

export const QUEUE_LABEL: Record<string, string> = {
  source_and_evidence_review: "Source conflicts and weak evidence",
  compliance_holds: "Compliance holds",
  awaiting_send_approval: "Messages awaiting your approval",
  content_claims: "Briefs with content-claim issues",
  concept_revisions: "Concepts needing revision",
  proposal_checks: "Proposals that failed checks",
  uncertain_replies: "Replies needing a decision",
};

export function formatAge(seconds: number): string {
  if (seconds < 90) return `${seconds}s`;
  if (seconds < 5400) return `${Math.round(seconds / 60)}m`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86400)}d`;
}
