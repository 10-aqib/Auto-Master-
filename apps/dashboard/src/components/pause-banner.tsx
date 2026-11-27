import Link from "next/link";

import { formatDate } from "@/components/ui";
import { apiServer } from "@/lib/api-server";

interface Control {
  key: string;
  enabled: boolean;
  effective: boolean;
  reason: string | null;
  updated_at: string;
  updated_by_name: string | null;
  env_override: boolean;
}

/** Always-visible state of the global and email pause switches, with who changed them last. */
export async function PauseBanner() {
  const r = await apiServer<Control[]>("/controls");
  if (!r.ok) return null;
  const pick = (key: string) => r.data.find((c) => c.key === key);
  const items = [
    { label: "System", c: pick("global_pause") },
    { label: "Email", c: pick("email_pause") },
  ];
  const anyPaused = items.some((i) => !i.c || i.c.effective);
  return (
    <div
      role="status"
      aria-label="Pause switches"
      className={`border-b text-sm ${anyPaused ? "border-amber-500/40 bg-amber-500/10" : "border-emerald-500/30 bg-emerald-500/10"}`}
    >
      <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center gap-x-5 gap-y-1 px-4 py-2 sm:px-6">
        {items.map(({ label, c }) => (
          <span key={label} data-testid={`pause-${label.toLowerCase()}`}>
            <strong>
              {label}: {!c || c.effective ? "PAUSED" : "RUNNING"}
            </strong>
            {c && (
              <span className="text-muted">
                {" "}
                · {c.updated_by_name ?? "system"}, {formatDate(c.updated_at)}
                {c.env_override ? " · forced by server setting" : ""}
              </span>
            )}
          </span>
        ))}
        <Link href="/settings" className="ml-auto text-accent hover:underline">
          Pause controls
        </Link>
      </div>
    </div>
  );
}
