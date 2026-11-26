import Link from "next/link";

import { PlacesSearch } from "@/components/places-search";
import { Alert, formatDate } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import { reasonText, type Source, type Verification } from "@/lib/sources";

export const metadata = { title: "Places discovery · WEBFORGE AI" };

interface Identifier {
  id: string;
  provider: string;
  place_id: string;
  status: string;
  prospect_id: string | null;
  first_seen_at: string;
}

export default async function PlacesPage() {
  await requireActiveSession(["OWNER", "ADMIN"]);
  const [sources, identifiers, verifications] = await Promise.all([
    apiServer<Source[]>("/sources"),
    apiServer<Identifier[]>("/places/identifiers?limit=20"),
    apiServer<Verification[]>("/verification/recent?limit=10"),
  ]);
  if (!sources.ok) return <Alert>{sources.error.message}</Alert>;
  const placeSources = sources.data.filter((s) => s.key === "google_places" || s.key === "mock_places");
  const canVerify = Boolean(sources.data.find((s) => s.key === "official_website")?.usable);

  return (
    <div className="grid gap-6">
      <header>
        <p className="text-sm">
          <Link href="/sources" className="text-accent hover:underline">
            ← Sources
          </Link>
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Places discovery</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Search results are Google Maps content: they are shown here with attribution and then discarded.
          Only Place IDs are saved. A business becomes a prospect only after its own website confirms it.
        </p>
      </header>
      <PlacesSearch sources={placeSources} canVerify={canVerify} />

      <section aria-labelledby="ids" className="rounded-xl border border-line bg-surface p-5 shadow-sm">
        <h2 id="ids" className="text-base font-semibold">
          Stored Place IDs (latest 20)
        </h2>
        {identifiers.ok && identifiers.data.length ? (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[36rem] text-sm">
              <thead className="text-left text-muted">
                <tr>
                  <th scope="col" className="py-2 font-medium">
                    Place ID
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    Source
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    Status
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    First seen
                  </th>
                </tr>
              </thead>
              <tbody>
                {identifiers.data.map((i) => (
                  <tr key={i.id} className="border-t border-line">
                    <td className="py-2 font-mono text-xs">{i.place_id}</td>
                    <td className="py-2">{i.provider}</td>
                    <td className="py-2">{i.prospect_id ? "Verified prospect" : i.status.toLowerCase()}</td>
                    <td className="py-2">{formatDate(i.first_seen_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-2 text-sm text-muted">None yet.</p>
        )}
      </section>

      <section
        aria-labelledby="verifications"
        className="rounded-xl border border-line bg-surface p-5 shadow-sm"
      >
        <h2 id="verifications" className="text-base font-semibold">
          Recent website checks
        </h2>
        {verifications.ok && verifications.data.length ? (
          <ul className="mt-2 divide-y divide-line text-sm">
            {verifications.data.map((v) => (
              <li key={v.id} className="py-2">
                <span className="font-medium">{v.status}</span> ·{" "}
                <span className="break-all">{v.domain ?? v.candidate_url}</span>
                <span className="text-muted"> · {formatDate(v.checked_at)}</span>
                {v.reason_codes.length > 0 && (
                  <span className="text-muted"> · {v.reason_codes.map(reasonText).join(" ")}</span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-muted">None yet.</p>
        )}
      </section>
    </div>
  );
}
