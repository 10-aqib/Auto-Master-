"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { MfaSetup } from "@/components/mfa-setup";
import { RecoveryCodes } from "@/components/recovery-codes";
import { Alert, Button, Card, Field, formatDate } from "@/components/ui";
import { api } from "@/lib/api-client";

export interface SessionRow {
  id: string;
  created_at: string;
  last_seen_at: string;
  user_agent: string | null;
  current: boolean;
}

export function MfaPanel({
  enabled,
  required,
  remaining,
}: {
  enabled: boolean;
  required: boolean;
  remaining: number | null;
}) {
  const router = useRouter();
  const [codes, setCodes] = useState<string[] | null>(null);
  const [mode, setMode] = useState<"idle" | "regen" | "disable">("idle");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!enabled) {
    return (
      <Card title="Two-factor authentication">
        <MfaSetup doneHref="/account" />
      </Card>
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    if (mode === "regen") {
      const r = await api<{ recovery_codes: string[] }>("/auth/mfa/recovery-codes", "POST", {
        code: String(form.get("code") ?? ""),
      });
      setBusy(false);
      if (r.ok) {
        setCodes(r.data.recovery_codes);
        setMode("idle");
      } else setError(r.error.message);
    } else {
      const r = await api("/auth/mfa/disable", "POST", {
        password: String(form.get("password") ?? ""),
        code: String(form.get("code") ?? ""),
      });
      setBusy(false);
      if (r.ok) router.refresh();
      else setError(r.error.message);
    }
  }

  return (
    <Card title="Two-factor authentication">
      <div className="grid gap-4">
        <Alert tone="success">
          On. {remaining !== null && `${remaining} of 10 recovery codes left.`}
          {required && " Required for your role."}
        </Alert>
        {codes && <RecoveryCodes codes={codes} />}
        {mode === "idle" ? (
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" onClick={() => setMode("regen")}>
              New recovery codes
            </Button>
            {!required && (
              <Button type="button" variant="danger" onClick={() => setMode("disable")}>
                Turn off
              </Button>
            )}
          </div>
        ) : (
          <form onSubmit={submit} className="grid gap-3" noValidate>
            {error && <Alert>{error}</Alert>}
            {mode === "disable" && (
              <Field
                id="mfa-password"
                name="password"
                type="password"
                label="Password"
                autoComplete="current-password"
                required
              />
            )}
            <Field
              id="mfa-code"
              name="code"
              label="Authenticator code"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              required
            />
            <div className="flex flex-wrap gap-2">
              <Button type="submit" busy={busy} variant={mode === "disable" ? "danger" : "primary"}>
                {mode === "disable" ? "Turn off two-factor" : "Generate new codes"}
              </Button>
              <Button type="button" variant="secondary" onClick={() => setMode("idle")}>
                Cancel
              </Button>
            </div>
          </form>
        )}
      </div>
    </Card>
  );
}

export function SessionsPanel({ sessions }: { sessions: SessionRow[] }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="grid gap-3">
      {error && <Alert>{error}</Alert>}
      <ul className="divide-y divide-line">
        {sessions.map((s) => (
          <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{s.user_agent ?? "Unknown device"}</p>
              <p className="text-xs text-muted">
                Signed in {formatDate(s.created_at)} · last active {formatDate(s.last_seen_at)}
                {s.current && " · this device"}
              </p>
            </div>
            {!s.current && (
              <Button
                type="button"
                variant="secondary"
                onClick={async () => {
                  const r = await api(`/auth/sessions/${s.id}`, "DELETE");
                  if (r.ok) router.refresh();
                  else setError(r.error.message);
                }}
              >
                Sign out
              </Button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
