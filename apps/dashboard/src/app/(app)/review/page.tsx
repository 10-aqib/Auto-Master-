import Link from "next/link";

import { Alert, Card, formatDate } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import { QUEUE_LABEL, type ReviewQueues } from "@/lib/overview";

export const metadata = { title: "Review queues · WEBFORGE AI" };

const HELP: Record<string, string> = {
  source_and_evidence_review:
    "Verification or qualification could not decide: conflicting sources, weak evidence or failed audits.",
  compliance_holds:
    "Outreach held by a missing review, basis, disclosure or switch. Open the prospect to see each reason.",
  awaiting_send_approval: "All 17 checks passed; only the owner can approve sending.",
  content_claims: "AI briefs that kept failing schema or claim checks after bounded repair.",
  concept_revisions: "Concepts whose latest validation has critical failures.",
  proposal_checks: "Proposal PDFs that failed structure or content checks (no file kept).",
  uncertain_replies: "Replies that are commercial or unclear. Nothing is answered automatically.",
};

export default async function ReviewPage() {
  await requireActiveSession();
  const data = await apiServer<ReviewQueues>("/review-queues");
  if (!data.ok) return <Alert>{data.error.message}</Alert>;
  return (
    <div className="grid gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Review queues</h1>
        <p className="mt-1 text-sm text-muted">Everything that automation refused to decide. Oldest first.</p>
      </header>
      {Object.entries(data.data.queues).map(([key, items]) => (
        <Card key={key} title={`${QUEUE_LABEL[key] ?? key} (${items.length})`}>
          <p className="mb-3 text-sm text-muted">{HELP[key]}</p>
          {items.length ? (
            <ul className="grid gap-1 text-sm">
              {items.map((i) => (
                <li key={`${key}-${i.id}`} className="flex flex-wrap justify-between gap-2">
                  <Link href={i.href} className="text-accent hover:underline">
                    {i.title}
                  </Link>
                  {i.since && <span className="text-muted">since {formatDate(i.since)}</span>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">Nothing waiting.</p>
          )}
        </Card>
      ))}
    </div>
  );
}
