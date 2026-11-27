import { Badge } from "@/components/badge";
import { Alert, Card, formatDate } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import { formatAge, type Operations } from "@/lib/overview";

export const metadata = { title: "Operations · WEBFORGE AI" };

export default async function OperationsPage() {
  await requireActiveSession(["OWNER", "ADMIN"]);
  const data = await apiServer<Operations>("/operations");
  if (!data.ok) return <Alert>{data.error.message}</Alert>;
  const o = data.data;
  return (
    <div className="grid gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Operations</h1>
        <p className="mt-1 text-sm text-muted">
          Workers, queues, failures, provider errors, quotas, pauses and backups.
        </p>
      </header>

      <Card title="Workers">
        {o.workers === null ? (
          <Alert>Worker heartbeats are unavailable (Redis unreachable).</Alert>
        ) : o.workers.length === 0 ? (
          <Alert>No worker has reported in the last 60 seconds. Jobs will not run.</Alert>
        ) : (
          <ul className="grid gap-1 text-sm">
            {o.workers.map((w) => (
              <li key={w.worker} className="flex flex-wrap justify-between gap-2">
                <span className="font-mono">{w.worker}</span>
                <span className="text-muted">
                  {w.queues.join(", ")} · seen {formatDate(w.at)}
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-xs text-muted">{o.worker_note}</p>
      </Card>

      <Card title={`Queues · dead letters ${o.dead_letter}`}>
        {o.queues.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[28rem] text-sm">
              <thead className="text-left text-muted">
                <tr>
                  <th scope="col" className="py-1 font-medium">
                    Queue
                  </th>
                  <th scope="col" className="py-1 font-medium">
                    Status
                  </th>
                  <th scope="col" className="py-1 text-right font-medium">
                    Jobs
                  </th>
                  <th scope="col" className="py-1 text-right font-medium">
                    Oldest
                  </th>
                </tr>
              </thead>
              <tbody>
                {o.queues.map((q) => (
                  <tr key={`${q.queue}-${q.status}`} className="border-t border-line">
                    <td className="py-1">{q.queue}</td>
                    <td className="py-1">
                      <Badge value={q.status} />
                    </td>
                    <td className="py-1 text-right tabular-nums">{q.count}</td>
                    <td className="py-1 text-right tabular-nums">{formatAge(q.oldest_age_seconds)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-muted">All queues are empty.</p>
        )}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Failures (24 h)">
          {o.failures_24h.length ? (
            <ul className="grid gap-1 text-sm">
              {o.failures_24h.map((f, i) => (
                <li key={i} className="flex justify-between gap-2">
                  <span>
                    {f.job_type} · {f.error_code ?? "unknown"}
                  </span>
                  <span className="tabular-nums">{f.count}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">No failed jobs.</p>
          )}
        </Card>
        <Card title="Provider errors (24 h)">
          {o.provider_errors_24h.length ? (
            <ul className="grid gap-1 text-sm">
              {o.provider_errors_24h.map((p) => (
                <li key={p.provider} className="flex justify-between gap-2">
                  <span>{p.provider}</span>
                  <span className="tabular-nums">{p.count}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">No provider errors.</p>
          )}
        </Card>
        <Card title="Quotas today">
          <ul className="grid gap-1 text-sm">
            {o.budgets.map((b) => (
              <li key={b.key} className="flex justify-between gap-2">
                <span>{b.label}</span>
                <span>
                  {b.used}/{b.limit}{" "}
                  <Badge
                    value={b.status === "ok" ? "SUCCEEDED" : b.status === "warning" ? "HOLD" : "FAILED"}
                    label={b.status}
                  />
                </span>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Pause switches and backups">
          <ul className="grid gap-1 text-sm">
            {o.pauses.map((p) => (
              <li key={p.key} className="flex justify-between gap-2">
                <span>{p.key}</span>
                <span className="text-muted">
                  {p.effective ? "paused" : "running"} · {formatDate(p.updated_at)}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-sm">
            Backups:{" "}
            <Badge value={o.backups.status === "unknown" ? "HOLD" : "SUCCEEDED"} label={o.backups.status} />{" "}
            <span className="text-muted">{o.backups.detail}</span>
          </p>
        </Card>
      </div>
    </div>
  );
}
