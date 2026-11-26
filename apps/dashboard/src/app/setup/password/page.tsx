import { redirect } from "next/navigation";

import { PasswordForm } from "@/components/password-form";
import { AuthShell } from "@/components/ui";
import { currentSession } from "@/lib/api-server";
import { pathForState } from "@/lib/auth-shared";

export const metadata = { title: "Choose a new password · WEBFORGE AI" };

export default async function SetupPasswordPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.session.state !== "password_change_required")
    redirect(pathForState(session.session.state) ?? "/");
  return (
    <AuthShell title="Choose a new password" subtitle="Your account was created with a temporary password.">
      <PasswordForm doneHref="/" />
    </AuthShell>
  );
}
