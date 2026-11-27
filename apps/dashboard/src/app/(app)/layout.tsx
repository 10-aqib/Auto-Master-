import { AppNav } from "@/components/app-nav";
import { PauseBanner } from "@/components/pause-banner";
import { SignOutButton } from "@/components/sign-out-button";
import { requireActiveSession } from "@/lib/api-server";

export default async function AppLayout({ children }: LayoutProps<"/">) {
  const { user } = await requireActiveSession();
  return (
    <div className="flex flex-1 flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:rounded focus:bg-accent focus:px-3 focus:py-2 focus:text-white"
      >
        Skip to content
      </a>
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <p className="text-xs font-semibold uppercase tracking-widest text-accent">WEBFORGE AI</p>
          <SignOutButton />
        </div>
        <div className="mx-auto w-full max-w-5xl px-4 pb-2 sm:px-6">
          <AppNav role={user.role} name={user.display_name} />
        </div>
        <PauseBanner />
      </header>
      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6">
        {children}
      </main>
    </div>
  );
}
