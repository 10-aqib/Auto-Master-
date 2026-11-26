import Link from "next/link";

import { ActionButton } from "@/components/action-button";
import { Badge } from "@/components/badge";
import { Alert, formatDate } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import type { Job } from "@/lib/discovery";

export const metadata = { title: "Jobs · WEBFORGE AI" };

const STATUSES = ["", "QUEUED", "RUNNING", "RETRYING", "SUCCEEDED", "FAILED", "DEAD", "CANCELLED"];

export default async function JobsPage({ searchParams }: PageProps<"/jobs">) {
  await requireActiveSession(["OWNER", "ADMIN"]);
  const sp = await searchParams;
  const status = typeof sp.status === "string" ? sp.status : "";
  const page = await apiServer<{ items: Job[]; total: number; counts: Record<string, number> }>(
    `/jobs?limit=100${status ? `&status=${status}` : ""}`,
  );
  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">Jobs</h1>
      {page.ok && (
        <nav aria-label="Filter by status" className="flex flex-wrap gap-2 text-sm">
          {STATUSES.map((s) => (
            <Link
              key={s}
              href={s ? `/jobs?status=${s}` : "/jobs"}
              aria-current={s === status ? "page" : undefined}
              className={`rounded-full border px-3 py-1 ${s === status ? "border-accent text-accent" : "border-line text-muted"}`}
            >
              {s ? `${s.toLowerCase()} (${page.data.counts[s] ?? 0})` : "all"}
            </Link>
          ))}
        </nav>
      )}
      {page.ok ? (
        <div className="overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full min-w-[48rem] text-sm">
            <thead className="text-left text-muted">
              <tr>
                <th scope="col" className="px-4 py-3 font-medium">
                  Job
                </th>
                <th scope="col" className="px-4 py-3 font-medium">
                  Status
                </th>
                <th scope="col" className="px-4 py-3 font-medium">
                  Attempts
                </th>
                <th scope="col" className="px-4 py-3 font-medium">
                  Details
                </th>
                <th scope="col" className="px-4 py-3 font-medium">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {page.data.items.map((j) => (
                <tr key={j.id} className="border-t border-line align-top">
                  <td className="px-4 py-3">
                    <span className="font-mono text-xs">{j.job_type}</span>
                    <span className="block text-xs text-muted">
                      {formatDate(j.created_at)} · {j.queue}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <Badge value={j.status} />
                  </td>
                  <td className="px-4 py-3 tabular-nums">
                    {j.attempts}/{j.max_attempts}
                  </td>
                  <td className="px-4 py-3 text-xs text-muted">
                    {j.error_code
                      ? `${j.error_code}: ${j.error_message ?? ""}`
                      : j.result
                        ? JSON.stringify(j.result)
                        : "—"}
                    {j.correlation_id && <span className="block">request {j.correlation_id}</span>}
                  </td>
                  <td className="px-4 py-3">
                    {["FAILED", "DEAD", "CANCELLED"].includes(j.status) && (
                      <ActionButton path={`/jobs/${j.id}/retry`} label="Retry" />
                    )}
                    {["QUEUED", "RETRYING"].includes(j.status) && (
                      <ActionButton path={`/jobs/${j.id}/cancel`} label="Cancel" variant="danger" />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!page.data.items.length && <p className="p-4 text-sm text-muted">No jobs.</p>}
        </div>
      ) : (
        <Alert>{page.error.message}</Alert>
      )}
    </div>
  );
}
