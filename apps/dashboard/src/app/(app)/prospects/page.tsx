import Link from "next/link";

import { ProspectTable } from "@/components/prospect-table";
import { Alert } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import type { ProspectPage } from "@/lib/discovery";

export const metadata = { title: "Prospects · WEBFORGE AI" };

const STATES = ["", "VERIFIED", "QUALIFYING", "QUALIFIED", "HUMAN_REVIEW", "REJECTED", "DO_NOT_CONTACT"];
const BANDS = ["", "STRONG", "POTENTIAL", "INVESTIGATE", "MANUAL_REVIEW", "REJECTED"];

export default async function ProspectsPage({ searchParams }: PageProps<"/prospects">) {
  await requireActiveSession();
  const sp = await searchParams;
  const get = (k: string) => (typeof sp[k] === "string" ? (sp[k] as string) : "");
  const offset = Math.max(0, Number(get("offset") || 0));
  const qs = new URLSearchParams({ limit: "50", offset: String(offset) });
  for (const k of ["state", "band", "q"]) if (get(k)) qs.set(k, get(k));
  const page = await apiServer<ProspectPage>(`/prospects?${qs}`);
  const link = (o: number) => {
    const next = new URLSearchParams(qs);
    next.set("offset", String(o));
    return `/prospects?${next}`;
  };
  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">Prospects</h1>
      <form className="flex flex-wrap items-end gap-3" role="search">
        <label className="grid gap-1 text-sm">
          Search
          <input
            name="q"
            defaultValue={get("q")}
            className="min-h-10 rounded-lg border border-line bg-background px-3"
          />
        </label>
        <label className="grid gap-1 text-sm">
          State
          <select
            name="state"
            defaultValue={get("state")}
            className="min-h-10 rounded-lg border border-line bg-background px-3"
          >
            {STATES.map((s) => (
              <option key={s} value={s}>
                {s ? s.toLowerCase().replaceAll("_", " ") : "any"}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-sm">
          Band
          <select
            name="band"
            defaultValue={get("band")}
            className="min-h-10 rounded-lg border border-line bg-background px-3"
          >
            {BANDS.map((s) => (
              <option key={s} value={s}>
                {s ? s.toLowerCase().replaceAll("_", " ") : "any"}
              </option>
            ))}
          </select>
        </label>
        <button className="min-h-10 rounded-lg border border-line bg-surface px-4 text-sm font-medium">
          Filter
        </button>
      </form>
      {page.ok ? (
        <>
          <ProspectTable items={page.data.items} />
          <nav aria-label="Pagination" className="flex items-center gap-4 text-sm">
            <span className="text-muted">
              {page.data.total === 0 ? "0" : `${offset + 1}–${Math.min(offset + 50, page.data.total)}`} of{" "}
              {page.data.total}
            </span>
            {offset > 0 && (
              <Link href={link(Math.max(0, offset - 50))} className="text-accent">
                ← Previous
              </Link>
            )}
            {offset + 50 < page.data.total && (
              <Link href={link(offset + 50)} className="text-accent">
                Next →
              </Link>
            )}
          </nav>
        </>
      ) : (
        <Alert>{page.error.message}</Alert>
      )}
    </div>
  );
}
