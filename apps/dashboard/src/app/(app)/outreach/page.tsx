import Link from "next/link";

import { Badge } from "@/components/badge";
import { Alert, Card, formatDate } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import type { OutreachMessage } from "@/lib/outreach";

export const metadata = { title: "Outreach · WEBFORGE AI" };

const FILTERS = [
  "ALL",
  "DRAFT",
  "PENDING_REVIEW",
  "SCHEDULED",
  "ACCEPTED",
  "DELIVERED",
  "BOUNCED",
  "CANCELLED",
  "AMBIGUOUS",
];

export default async function OutreachPage({ searchParams }: PageProps<"/outreach">) {
  await requireActiveSession();
  const sp = await searchParams;
  const status = typeof sp.status === "string" && FILTERS.includes(sp.status) ? sp.status : "ALL";
  const data = await apiServer<OutreachMessage[]>("/outreach");
  if (!data.ok) return <Alert>{data.error.message}</Alert>;
  const rows = data.data.filter((m) => status === "ALL" || m.status === status);
  return (
    <div className="grid gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Outreach</h1>
        <p className="mt-1 text-sm text-muted">
          Drafts, holds, sends and provider events. One initial message per prospect.
        </p>
      </header>
      <nav aria-label="Filter by status" className="flex flex-wrap gap-1 text-sm">
        {FILTERS.map((f) => (
          <Link
            key={f}
            href={f === "ALL" ? "/outreach" : `/outreach?status=${f}`}
            aria-current={f === status ? "page" : undefined}
            className={`rounded-lg px-3 py-1.5 ${f === status ? "bg-accent text-white" : "border border-line hover:bg-background"}`}
          >
            {f.toLowerCase().replaceAll("_", " ")}
          </Link>
        ))}
      </nav>
      <Card title={`${rows.length} message${rows.length === 1 ? "" : "s"}`}>
        {rows.length ? (
          <ul className="grid gap-2 text-sm">
            {rows.map((m) => (
              <li
                key={m.id}
                className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-2 first:border-0 first:pt-0"
              >
                <Link href={`/prospects/${m.prospect_id}`} className="text-accent hover:underline">
                  {m.subject ?? "Message"}
                </Link>
                <span className="flex flex-wrap items-center gap-2 text-muted">
                  <Badge value={m.status} label={m.status.toLowerCase().replaceAll("_", " ")} />
                  {m.assessment && <span>compliance {m.assessment.decision.toLowerCase()}</span>}
                  {m.error_code && <span>{m.error_code}</span>}
                  <span>{formatDate(m.created_at)}</span>
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">No messages in this view.</p>
        )}
      </Card>
    </div>
  );
}
