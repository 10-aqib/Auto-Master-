"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Alert, Button, Card, Field, formatDate } from "@/components/ui";
import { api } from "@/lib/api-client";
import { ROLE_LABEL, type Role, type User } from "@/lib/auth-shared";

const MANAGEABLE: Record<Role, Role[]> = {
  OWNER: ["ADMIN", "REVIEWER", "READ_ONLY"],
  ADMIN: ["REVIEWER", "READ_ONLY"],
  REVIEWER: [],
  READ_ONLY: [],
};

function CreateUserForm({ actorRole, onCreated }: { actorRole: Role; onCreated: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [created, setCreated] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    setBusy(true);
    setError(null);
    setFieldErrors({});
    const r = await api<User>("/users", "POST", {
      email: String(form.get("email") ?? ""),
      display_name: String(form.get("display_name") ?? ""),
      role: String(form.get("role") ?? ""),
      initial_password: String(form.get("initial_password") ?? ""),
    });
    setBusy(false);
    if (!r.ok) {
      setError(r.error.message);
      setFieldErrors(r.error.field_errors);
      return;
    }
    formEl.reset();
    setCreated(r.data.email);
    onCreated();
  }

  return (
    <form onSubmit={onSubmit} className="grid gap-4 sm:grid-cols-2" noValidate>
      {error && (
        <div className="sm:col-span-2">
          <Alert>{error}</Alert>
        </div>
      )}
      {created && (
        <div className="sm:col-span-2">
          <Alert tone="success">
            Created {created}. Share the temporary password privately; they must change it at first sign-in.
          </Alert>
        </div>
      )}
      <Field
        id="new-email"
        name="email"
        type="email"
        label="Email"
        autoComplete="off"
        error={fieldErrors.email}
        required
      />
      <Field
        id="new-name"
        name="display_name"
        label="Display name"
        error={fieldErrors.display_name}
        required
      />
      <div className="grid gap-1.5">
        <label htmlFor="new-role" className="text-sm font-medium">
          Role
        </label>
        <select
          id="new-role"
          name="role"
          className="min-h-10 rounded-lg border border-line bg-background px-3 text-sm"
          defaultValue={MANAGEABLE[actorRole].at(-1)}
        >
          {MANAGEABLE[actorRole].map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </select>
      </div>
      <Field
        id="new-password"
        name="initial_password"
        type="password"
        label="Temporary password"
        autoComplete="new-password"
        hint="At least 12 characters."
        error={fieldErrors.initial_password}
        required
      />
      <div className="sm:col-span-2">
        <Button type="submit" busy={busy}>
          Create account
        </Button>
      </div>
    </form>
  );
}

function UserRow({ user, actor }: { user: User; actor: User }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  const manageable = user.id !== actor.id && MANAGEABLE[actor.role].includes(user.role);

  async function run(label: string, path: string, method: string, body?: unknown, success?: string) {
    setBusy(label);
    setMessage(null);
    const r = await api(path, method, body);
    setBusy(null);
    if (!r.ok) setMessage({ tone: "error", text: r.error.message });
    else {
      if (success) setMessage({ tone: "success", text: success });
      router.refresh();
    }
  }

  return (
    <li className="grid gap-3 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium">
            {user.display_name}
            {user.id === actor.id && <span className="text-muted"> (you)</span>}
          </p>
          <p className="break-all text-sm text-muted">{user.email}</p>
          <p className="mt-1 text-xs text-muted">
            {ROLE_LABEL[user.role]} · {user.is_active ? "Active" : "Deactivated"} · 2FA{" "}
            {user.mfa_enabled ? "on" : "off"}
            {user.password_change_required && " · must change password"} · last sign-in{" "}
            {formatDate(user.last_login_at)}
          </p>
        </div>
        {manageable && (
          <div className="flex flex-wrap gap-2">
            {actor.role === "OWNER" && (
              <select
                aria-label={`Role for ${user.email}`}
                className="min-h-10 rounded-lg border border-line bg-background px-2 text-sm"
                value={user.role}
                disabled={busy !== null}
                onChange={(e) =>
                  run("role", `/users/${user.id}`, "PATCH", { role: e.target.value }, "Role updated.")
                }
              >
                {MANAGEABLE.OWNER.map((r) => (
                  <option key={r} value={r}>
                    {ROLE_LABEL[r]}
                  </option>
                ))}
              </select>
            )}
            <Button
              type="button"
              variant={user.is_active ? "danger" : "secondary"}
              busy={busy === "active"}
              onClick={() => run("active", `/users/${user.id}`, "PATCH", { is_active: !user.is_active })}
            >
              {user.is_active ? "Deactivate" : "Reactivate"}
            </Button>
            <Button
              type="button"
              variant="secondary"
              busy={busy === "sessions"}
              onClick={() =>
                run("sessions", `/users/${user.id}/revoke-sessions`, "POST", undefined, "Sessions ended.")
              }
            >
              End sessions
            </Button>
            {actor.role === "OWNER" && user.mfa_enabled && (
              <Button
                type="button"
                variant="secondary"
                busy={busy === "mfa"}
                onClick={() =>
                  run("mfa", `/users/${user.id}/reset-mfa`, "POST", undefined, "Two-factor reset.")
                }
              >
                Reset 2FA
              </Button>
            )}
          </div>
        )}
      </div>
      {message && <Alert tone={message.tone}>{message.text}</Alert>}
    </li>
  );
}

export function UsersManager({ users, actor }: { users: User[]; actor: User }) {
  const router = useRouter();
  return (
    <div className="grid gap-6">
      <Card title="Add an account">
        <CreateUserForm actorRole={actor.role} onCreated={() => router.refresh()} />
      </Card>
      <Card title={`Accounts (${users.length})`}>
        <ul className="divide-y divide-line">
          {users.map((u) => (
            <UserRow key={u.id} user={u} actor={actor} />
          ))}
        </ul>
      </Card>
    </div>
  );
}
