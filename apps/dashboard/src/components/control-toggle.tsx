"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Alert, Button, Field, formatDate } from "@/components/ui";
import { api } from "@/lib/api-client";
import type { Role } from "@/lib/auth-shared";
import type { Control } from "@/lib/discovery";

export function ControlToggle({ control, role }: { control: Control; role: Role }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const resuming = control.enabled;
  const allowed = resuming ? role === "OWNER" : role === "OWNER" || role === "ADMIN";

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const reason = String(new FormData(event.currentTarget).get("reason") ?? "");
    setBusy(true);
    setError(null);
    const r = await api(`/controls/${control.key}`, "PUT", { enabled: !control.enabled, reason });
    setBusy(false);
    if (!r.ok) return setError(r.error.message);
    router.refresh();
  }

  return (
    <section
      className={`rounded-xl border p-5 ${control.effective ? "border-amber-500/40 bg-amber-500/5" : "border-emerald-500/40 bg-emerald-500/5"}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">
          {control.key === "global_pause" ? "Global pause" : "Email pause"}
        </h2>
        <span className="text-sm font-semibold">{control.effective ? "PAUSED" : "RUNNING"}</span>
      </div>
      <p className="mt-1 text-sm text-muted">{control.description}</p>
      <p className="mt-1 text-xs text-muted">
        Last change {formatDate(control.updated_at)}
        {control.reason ? ` — “${control.reason}”` : ""}
      </p>
      {control.env_override && (
        <p className="mt-2 text-sm font-medium text-amber-800 dark:text-amber-300">
          Forced on by the server’s emergency setting; the switch below cannot resume it.
        </p>
      )}
      <form onSubmit={onSubmit} className="mt-3 grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end" noValidate>
        <Field id={`${control.key}-reason`} name="reason" label="Reason" required disabled={!allowed} />
        <Button
          type="submit"
          busy={busy}
          variant={resuming ? "primary" : "danger"}
          disabled={!allowed}
          title={allowed ? undefined : "Only the owner can resume."}
        >
          {resuming ? "Resume" : "Pause now"}
        </Button>
        {!allowed && <p className="text-xs text-muted sm:col-span-2">Only the owner can resume.</p>}
        {error && (
          <div className="sm:col-span-2">
            <Alert>{error}</Alert>
          </div>
        )}
      </form>
    </section>
  );
}
