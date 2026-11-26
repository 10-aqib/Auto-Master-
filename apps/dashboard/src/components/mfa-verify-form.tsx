"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Alert, Button, Field } from "@/components/ui";
import { api } from "@/lib/api-client";
import { pathForState, type AuthResponse } from "@/lib/auth-shared";

export function MfaVerifyForm() {
  const router = useRouter();
  const [method, setMethod] = useState<"totp" | "recovery">("totp");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = String(new FormData(event.currentTarget).get("code") ?? "");
    setBusy(true);
    setError(null);
    const result = await api<AuthResponse>("/auth/mfa/verify", "POST", { code, method });
    setBusy(false);
    if (!result.ok) {
      if (result.status === 401 && result.error.code !== "invalid_mfa_code") {
        router.replace("/login");
        return;
      }
      setError(result.error.message);
      return;
    }
    router.replace(pathForState(result.data.session.state) ?? "/");
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="grid gap-4" noValidate>
      {error && <Alert>{error}</Alert>}
      {method === "totp" ? (
        <Field
          key="totp"
          id="code"
          name="code"
          label="6-digit code from your authenticator app"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]{6}"
          maxLength={6}
          required
          autoFocus
        />
      ) : (
        <Field
          key="recovery"
          id="code"
          name="code"
          label="Recovery code"
          autoComplete="off"
          placeholder="xxxxx-xxxxx"
          required
          autoFocus
        />
      )}
      <Button type="submit" busy={busy}>
        Verify
      </Button>
      <button
        type="button"
        className="text-sm text-accent underline-offset-4 hover:underline"
        onClick={() => setMethod(method === "totp" ? "recovery" : "totp")}
      >
        {method === "totp" ? "Use a recovery code instead" : "Use an authenticator code instead"}
      </button>
    </form>
  );
}
