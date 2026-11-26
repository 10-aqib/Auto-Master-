import { redirect } from "next/navigation";

import { MfaSetup } from "@/components/mfa-setup";
import { AuthShell } from "@/components/ui";
import { currentSession } from "@/lib/api-server";
import { pathForState } from "@/lib/auth-shared";

export const metadata = { title: "Set up two-factor authentication · WEBFORGE AI" };

export default async function SetupMfaPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (session.session.state !== "mfa_enrollment_required")
    redirect(pathForState(session.session.state) ?? "/");
  return (
    <AuthShell
      title="Set up two-factor authentication"
      subtitle="Your role requires a second factor before you can use the console."
    >
      <MfaSetup />
    </AuthShell>
  );
}
