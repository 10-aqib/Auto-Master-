import { AppNav } from "@/components/app-nav";
import { SignOutButton } from "@/components/sign-out-button";
import { requireActiveSession } from "@/lib/api-server";

export default async function AppLayout({ children }: LayoutProps<"/">) {
  const { user } = await requireActiveSession();
  return (
    <div className="flex flex-1 flex-col">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <p className="text-xs font-semibold uppercase tracking-widest text-accent">WEBFORGE AI</p>
          <SignOutButton />
        </div>
        <div className="mx-auto w-full max-w-5xl px-4 pb-2 sm:px-6">
          <AppNav role={user.role} name={user.display_name} />
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6">{children}</main>
    </div>
  );
}
