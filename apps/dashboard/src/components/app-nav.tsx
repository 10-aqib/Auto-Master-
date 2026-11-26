"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { ROLE_LABEL, type Role } from "@/lib/auth-shared";

const LINKS: { href: string; label: string; roles?: Role[] }[] = [
  { href: "/", label: "Status" },
  { href: "/users", label: "Users", roles: ["OWNER", "ADMIN"] },
  { href: "/activity", label: "Activity", roles: ["OWNER", "ADMIN"] },
  { href: "/account", label: "Account" },
];

export function AppNav({ role, name }: { role: Role; name: string }) {
  const pathname = usePathname();
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <nav aria-label="Main" className="flex flex-wrap gap-1">
        {LINKS.filter((l) => !l.roles || l.roles.includes(role)).map((l) => {
          const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
          return (
            <Link
              key={l.href}
              href={l.href}
              aria-current={active ? "page" : undefined}
              className={`rounded-lg px-3 py-2 text-sm font-medium ${active ? "bg-accent/10 text-accent" : "text-muted hover:text-foreground"}`}
            >
              {l.label}
            </Link>
          );
        })}
      </nav>
      <p className="text-sm text-muted">
        {name} · {ROLE_LABEL[role]}
      </p>
    </div>
  );
}
