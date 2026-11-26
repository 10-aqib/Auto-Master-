import { MfaPanel, SessionsPanel, type SessionRow } from "@/components/account-security";
import { PasswordForm } from "@/components/password-form";
import { SignOutButton } from "@/components/sign-out-button";
import { Card, formatDate } from "@/components/ui";
import { apiServer, requireActiveSession } from "@/lib/api-server";
import { ROLE_LABEL } from "@/lib/auth-shared";

export const metadata = { title: "Account · WEBFORGE AI" };

export default async function AccountPage() {
  const { user, session } = await requireActiveSession();
  const sessions = await apiServer<SessionRow[]>("/auth/sessions");
  const mfaRequired = user.role === "OWNER" || user.role === "ADMIN";

  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">Account</h1>
      <Card title="Profile">
        <dl className="grid gap-2 text-sm sm:grid-cols-[10rem_1fr]">
          <dt className="text-muted">Name</dt>
          <dd>{user.display_name}</dd>
          <dt className="text-muted">Email</dt>
          <dd className="break-all">{user.email}</dd>
          <dt className="text-muted">Role</dt>
          <dd>{ROLE_LABEL[user.role]}</dd>
          <dt className="text-muted">Last sign-in</dt>
          <dd>{formatDate(user.last_login_at)}</dd>
        </dl>
      </Card>
      <MfaPanel
        enabled={user.mfa_enabled}
        required={mfaRequired}
        remaining={session.recovery_codes_remaining ?? null}
      />
      <Card title="Password">
        <PasswordForm />
      </Card>
      <Card title="Active sessions" actions={<SignOutButton everywhere />}>
        {sessions.ok ? (
          <SessionsPanel sessions={sessions.data} />
        ) : (
          <p className="text-sm">{sessions.error.message}</p>
        )}
      </Card>
    </div>
  );
}
