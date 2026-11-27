import Link from "next/link";

import { ActionButton } from "@/components/action-button";
import { Badge } from "@/components/badge";
import { Alert, Card, formatDate } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import type { ReplyItem } from "@/lib/outreach";

export const metadata = { title: "Replies · WEBFORGE AI" };

const TONE: Record<string, string> = {
  INTERESTED: "SUCCEEDED",
  QUESTION: "QUEUED",
  NOT_INTERESTED: "CANCELLED",
  OPT_OUT: "FAILED",
  AUTO_REPLY: "CANCELLED",
  UNCERTAIN: "HOLD",
};

export default async function RepliesPage() {
  const { user } = await requireActiveSession();
  const replies = await apiServer<ReplyItem[]>("/replies");
  const canAct = user.role === "OWNER" || user.role === "ADMIN";
  if (!replies.ok) return <Alert>{replies.error.message}</Alert>;
  const open = replies.data.filter((r) => r.needs_human_review && !r.handled_at);

  return (
    <div className="grid gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Replies</h1>
        <p className="mt-1 text-sm text-muted">
          Classified by fixed rules. Opt-outs are honoured automatically and always win; anything commercial
          or unclear waits for you. Nothing is answered automatically.
        </p>
      </header>
      <Card title={`Needs your attention (${open.length})`}>
        {replies.data.length === 0 ? (
          <p className="text-sm text-muted">No replies yet.</p>
        ) : (
          <ul className="grid gap-3 text-sm">
            {replies.data.map((r) => (
              <li key={r.id} className="grid gap-1 border-t border-line pt-3 first:border-0 first:pt-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge
                    value={TONE[r.classification ?? "UNCERTAIN"] ?? "HOLD"}
                    label={(r.classification ?? "uncertain").toLowerCase().replaceAll("_", " ")}
                  />
                  {r.needs_human_review && !r.handled_at && <Badge value="HOLD" label="needs review" />}
                  {r.handled_at && <Badge value="SUCCEEDED" label={`handled ${formatDate(r.handled_at)}`} />}
                  <span className="text-muted">{formatDate(r.received_at)}</span>
                  {r.prospect_id && (
                    <Link href={`/prospects/${r.prospect_id}`} className="text-accent hover:underline">
                      Prospect
                    </Link>
                  )}
                </div>
                {r.subject && <p className="font-medium">{r.subject}</p>}
                {r.summary && <p className="whitespace-pre-wrap text-muted">{r.summary}</p>}
                {canAct && r.needs_human_review && !r.handled_at && (
                  <div>
                    <ActionButton path={`/replies/${r.id}/handled`} label="Mark handled" />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
