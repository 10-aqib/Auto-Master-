"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Alert, Button, Field } from "@/components/ui";
import { api } from "@/lib/api-client";
import { pathForState, safeNext, type AuthResponse } from "@/lib/auth-shared";

export function LoginForm({ next }: { next?: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    const result = await api<AuthResponse>("/auth/login", "POST", {
      email: String(form.get("email") ?? ""),
      password: String(form.get("password") ?? ""),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    router.replace(pathForState(result.data.session.state) ?? safeNext(next));
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="grid gap-4" noValidate>
      {error && <Alert>{error}</Alert>}
      <Field id="email" name="email" type="email" label="Email" autoComplete="username" required autoFocus />
      <Field
        id="password"
        name="password"
        type="password"
        label="Password"
        autoComplete="current-password"
        required
      />
      <Button type="submit" busy={busy}>
        Sign in
      </Button>
    </form>
  );
}
