import Link from "next/link";

import { Badge } from "@/components/badge";
import { Alert, Card, formatDate } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import { CATEGORY_LABEL, type Audit, type AuditFinding } from "@/lib/discovery";

export const metadata = { title: "Audit · WEBFORGE AI" };

const SEVERITY_TONE: Record<string, string> = { HIGH: "FAILED", MEDIUM: "HOLD", LOW: "DRAFT", INFO: "DRAFT" };

export default async function AuditPage({ params }: PageProps<"/audits/[id]">) {
  const { id } = await params;
  await requireActiveSession();
  const res = await apiServer<{ audit: Audit; findings: AuditFinding[] }>(`/audits/${id}`);
  if (!res.ok) return <Alert>{res.error.message}</Alert>;
  const { audit: a, findings } = res.data;
  const cats = a.scores.categories ?? {};
  return (
    <div className="grid gap-6">
      <header>
        <p className="text-sm">
          <Link href={`/prospects/${a.prospect_id}`} className="text-accent hover:underline">
            ← Prospect
          </Link>
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Website audit</h1>
        <p className="mt-1 break-all text-sm text-muted">
          {a.url} · {formatDate(a.finished_at ?? a.started_at)} · {a.audit_version} · browser{" "}
          {a.browser_version ?? "—"} · {a.scores.pages_checked ?? 0} page(s)
        </p>
      </header>
      <div className="flex flex-wrap items-center gap-3">
        <Badge value={a.status} />
        {a.scores.overall != null && (
          <span className="text-sm">Overall {a.scores.overall}/100 (tested categories only)</span>
        )}
      </div>
      {a.error_summary && <Alert>{a.error_summary}</Alert>}
      {Object.keys(cats).length > 0 && (
        <Card title="Categories">
          <ul className="grid gap-2 text-sm sm:grid-cols-2">
            {Object.entries(cats).map(([k, c]) => (
              <li key={k} className="flex justify-between gap-3 border-b border-line py-1">
                <span>
                  {CATEGORY_LABEL[k] ?? k} <span className="text-muted">(weight {c.weight})</span>
                </span>
                <span className="tabular-nums">{c.score === null ? "not tested" : `${c.score}/100`}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Card title={`Findings (${findings.length})`}>
        {findings.length ? (
          <ul className="grid gap-4">
            {findings.map((f) => (
              <li key={f.id} className="grid gap-1 text-sm">
                <p className="flex flex-wrap items-center gap-2">
                  <Badge value={SEVERITY_TONE[f.severity] ?? "DRAFT"} label={f.severity.toLowerCase()} />
                  <span className="font-mono text-xs text-muted">{f.code}</span>
                  <span className="text-xs text-muted">
                    {f.viewport} · confidence {f.confidence?.toFixed(2)}
                  </span>
                </p>
                <p>{f.description}</p>
                {f.reproduction_steps && (
                  <p className="text-xs text-muted">
                    How to see it: {f.reproduction_steps.replaceAll("\n", " → ")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">No findings.</p>
        )}
      </Card>
      {a.scores.strengths?.length || a.scores.caveats?.length ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Strengths">
            <ul className="list-disc pl-5 text-sm">
              {a.scores.strengths?.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </Card>
          <Card title="Caveats">
            <ul className="list-disc pl-5 text-sm">
              {a.scores.caveats?.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </Card>
        </div>
      ) : null}
      {(a.desktop_screenshot_key || a.mobile_screenshot_key) && (
        <Card title="Screenshots (as captured)">
          <div className="grid gap-4 sm:grid-cols-[3fr_1fr]">
            {a.desktop_screenshot_key && (
              // eslint-disable-next-line @next/next/no-img-element -- private, session-authenticated image
              <img
                src={`/api/screenshots/${a.id}/desktop`}
                alt="Desktop screenshot of the current website"
                className="w-full rounded-lg border border-line"
              />
            )}
            {a.mobile_screenshot_key && (
              // eslint-disable-next-line @next/next/no-img-element -- private, session-authenticated image
              <img
                src={`/api/screenshots/${a.id}/mobile`}
                alt="Mobile screenshot of the current website"
                className="w-full rounded-lg border border-line"
              />
            )}
          </div>
        </Card>
      )}
    </div>
  );
}
