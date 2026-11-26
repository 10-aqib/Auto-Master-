import { Badge } from "@/components/badge";
import { formatDate } from "@/components/ui";
import { PAGE_SLUGS, problems, type Validation } from "@/lib/designs";

/** Validation summary, failing checks with evidence, and the screenshot set for one render. */
export function ValidationReport({ validation: v }: { validation: Validation }) {
  const s = v.report.summary;
  const issues = problems(v);
  return (
    <div className="grid gap-3 rounded-lg border border-line p-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">Validation</span>
        <Badge
          value={v.status === "READY" ? "SUCCEEDED" : "HOLD"}
          label={v.status === "READY" ? "ready" : "needs revision"}
        />
        <span className="text-muted">
          {formatDate(v.created_at)} · {s.passed}/{s.checks} checks passed · {s.failed_critical} critical ·{" "}
          {s.failed_major} warnings · {s.unknown} unknown · {v.validator_version}
          {v.browser_version ? ` · Chromium ${v.browser_version}` : ""}
        </span>
      </div>
      {issues.length > 0 && (
        <details className="text-sm" open={v.status !== "READY"}>
          <summary className="cursor-pointer font-medium">
            {issues.length} check{issues.length === 1 ? "" : "s"} need attention
          </summary>
          <ul className="mt-2 grid gap-1">
            {issues.slice(0, 40).map((c, i) => (
              <li key={i} className="flex flex-wrap gap-2">
                <Badge value={c.severity === "critical" ? "FAILED" : "HOLD"} label={c.severity} />
                <span>
                  {c.message}
                  {c.page ? ` — ${c.page}` : ""}
                  {c.viewport ? ` (${c.viewport})` : ""}
                  {c.status === "unknown" ? " — not measurable" : ""}
                </span>
                {c.evidence != null && (
                  <code className="max-w-full overflow-x-auto break-all text-xs text-muted">
                    {JSON.stringify(c.evidence).slice(0, 240)}
                  </code>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
      {v.screenshots.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer font-medium">Screenshots ({v.screenshots.length})</summary>
          <div className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {PAGE_SLUGS.flatMap((slug) =>
              v.screenshots
                .filter((shot) => shot.slug === slug)
                .map((shot) => {
                  const src = `/api/validation-shots/${v.id}/${shot.slug}/${shot.viewport}`;
                  return (
                    <a
                      key={`${shot.slug}-${shot.viewport}`}
                      href={src}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="grid gap-1 rounded border border-line p-2 hover:bg-background"
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element -- authenticated, uncached image */}
                      <img
                        src={src}
                        alt={`${shot.slug} page at ${shot.viewport} width`}
                        loading="lazy"
                        className="h-40 w-full rounded object-cover object-top"
                      />
                      <span className="text-xs text-muted">
                        {shot.slug} · {shot.viewport} · sha256 {shot.sha256.slice(0, 12)}…
                      </span>
                    </a>
                  );
                }),
            )}
          </div>
        </details>
      )}
    </div>
  );
}
