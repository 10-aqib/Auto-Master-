import Link from "next/link";

import { Badge } from "@/components/badge";
import { CampaignForm } from "@/components/campaign-form";
import { Alert, Card, formatDate } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import type { Campaign } from "@/lib/discovery";

export const metadata = { title: "Campaigns · WEBFORGE AI" };

export default async function CampaignsPage() {
  const { user } = await requireActiveSession();
  const [campaigns, industries] = await Promise.all([
    apiServer<Campaign[]>("/campaigns"),
    apiServer<Record<string, string>>("/industries"),
  ]);
  const canEdit = user.role === "OWNER" || user.role === "ADMIN";
  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">Campaigns</h1>
      {campaigns.ok ? (
        campaigns.data.length ? (
          <ul className="grid gap-3">
            {campaigns.data.map((c) => (
              <li
                key={c.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface px-5 py-4"
              >
                <div>
                  <Link href={`/campaigns/${c.id}`} className="font-medium text-accent hover:underline">
                    {c.name}
                  </Link>
                  <p className="text-xs text-muted">
                    {c.target_countries.join(", ")} · {c.industries.join(", ") || "any industry"} · created{" "}
                    {formatDate(c.created_at)}
                  </p>
                </div>
                <Badge value={c.status} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">No campaigns yet.</p>
        )
      ) : (
        <Alert>{campaigns.error.message}</Alert>
      )}
      {canEdit && industries.ok && (
        <Card title="New campaign">
          <CampaignForm industries={industries.data} />
        </Card>
      )}
    </div>
  );
}
