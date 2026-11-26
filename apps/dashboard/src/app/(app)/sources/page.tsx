import Link from "next/link";

import { OwnerVerifyForm } from "@/components/owner-verify-form";
import { SourceCard } from "@/components/source-card";
import { Alert, Card } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import type { Source } from "@/lib/sources";

export const metadata = { title: "Sources · WEBFORGE AI" };

export default async function SourcesPage() {
  const { user } = await requireActiveSession(["OWNER", "ADMIN"]);
  const sources = await apiServer<Source[]>("/sources");
  const website = sources.ok ? sources.data.find((s) => s.key === "official_website") : undefined;
  return (
    <div className="grid gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Data sources</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted">
            Every source starts disabled. The owner records a terms review before enabling it. Only the fields
            listed under “May be stored” are ever saved; everything else is shown once and discarded.
          </p>
        </div>
        <Link
          href="/sources/places"
          className="rounded-lg border border-line bg-surface px-4 py-2 text-sm font-medium hover:bg-background"
        >
          Places discovery →
        </Link>
      </header>
      {sources.ok ? (
        <div className="grid gap-6 lg:grid-cols-2">
          {sources.data.map((s) => (
            <SourceCard key={s.key} source={s} role={user.role} />
          ))}
        </div>
      ) : (
        <Alert>{sources.error.message}</Alert>
      )}
      <Card title="Check a website you already know">
        <OwnerVerifyForm enabled={Boolean(website?.usable)} />
      </Card>
    </div>
  );
}
