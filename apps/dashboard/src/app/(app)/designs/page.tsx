import Link from "next/link";

import { Badge } from "@/components/badge";
import { Alert, Card, formatDate } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import type { DesignProject } from "@/lib/designs";

export const metadata = { title: "Designs · WEBFORGE AI" };

export default async function DesignsPage() {
  await requireActiveSession();
  const data = await apiServer<DesignProject[]>("/designs");
  if (!data.ok) return <Alert>{data.error.message}</Alert>;
  return (
    <div className="grid gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Design projects</h1>
        <p className="mt-1 text-sm text-muted">
          Briefs, six-page concepts, validation and proposals. Most recent first.
        </p>
      </header>
      <Card title={`${data.data.length} project${data.data.length === 1 ? "" : "s"}`}>
        {data.data.length ? (
          <ul className="grid gap-2 text-sm">
            {data.data.map((d) => (
              <li
                key={d.id}
                className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-2 first:border-0 first:pt-0"
              >
                <Link href={`/designs/${d.id}`} className="font-medium text-accent hover:underline">
                  {d.business_name ?? "Design project"}
                </Link>
                <span className="flex items-center gap-2 text-muted">
                  <Badge value={d.status} />v{d.current_version} · {d.renderer_version ?? "not rendered"} ·{" "}
                  {formatDate(d.created_at)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">
            No design projects yet. Generate a brief from an audited prospect.
          </p>
        )}
      </Card>
    </div>
  );
}
