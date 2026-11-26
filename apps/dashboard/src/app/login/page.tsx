import { redirect } from "next/navigation";

import { LoginForm } from "@/components/login-form";
import { AuthShell } from "@/components/ui";
import { currentSession } from "@/lib/api-server";
import { pathForState, safeNext } from "@/lib/auth-shared";

export const metadata = { title: "Sign in · WEBFORGE AI" };

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const { next } = await searchParams;
  const nextPath = safeNext(typeof next === "string" ? next : undefined);
  const session = await currentSession();
  if (session) redirect(pathForState(session.session.state) ?? nextPath);
  return (
    <AuthShell title="Sign in" subtitle="Owner operations console.">
      <LoginForm next={nextPath} />
    </AuthShell>
  );
}
