import { redirect } from "next/navigation";

import { MfaVerifyForm } from "@/components/mfa-verify-form";
import { AuthShell } from "@/components/ui";
import { currentSession } from "@/lib/api-server";
import { pathForState } from "@/lib/auth-shared";

export const metadata = { title: "Two-factor verification · WEBFORGE AI" };

export default async function MfaPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.session.state !== "mfa_pending") redirect(pathForState(session.session.state) ?? "/");
  return (
    <AuthShell title="Two-factor verification" subtitle={`Signed in as ${session.user.email}.`}>
      <MfaVerifyForm />
    </AuthShell>
  );
}
