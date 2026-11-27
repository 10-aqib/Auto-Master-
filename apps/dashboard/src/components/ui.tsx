import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

export function Card({
  title,
  children,
  actions,
}: {
  title?: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="min-w-0 rounded-xl border border-line bg-surface p-5 shadow-sm">
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          {title && <h2 className="text-base font-semibold">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

type Variant = "primary" | "secondary" | "danger";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent-solid text-white hover:opacity-90",
  secondary: "border border-line bg-surface hover:bg-background",
  danger: "border border-rose-500/40 text-rose-700 hover:bg-rose-500/10 dark:text-rose-300",
};

export function Button({
  variant = "primary",
  busy = false,
  className = "",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; busy?: boolean }) {
  return (
    <button
      {...props}
      disabled={busy || props.disabled}
      aria-busy={busy || undefined}
      className={`inline-flex min-h-10 items-center justify-center rounded-lg px-4 text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]} ${className}`}
    >
      {busy ? "Working…" : children}
    </button>
  );
}

export function Field({
  label,
  error,
  hint,
  id,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string; hint?: string; id: string }) {
  const describedBy = [error ? `${id}-error` : null, hint ? `${id}-hint` : null].filter(Boolean).join(" ");
  return (
    <div className="grid gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <input
        id={id}
        {...props}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        className="min-h-10 rounded-lg border border-line bg-background px-3 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/30 aria-invalid:border-rose-500"
      />
      {hint && (
        <p id={`${id}-hint`} className="text-xs text-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="text-xs text-rose-700 dark:text-rose-300">
          {error}
        </p>
      )}
    </div>
  );
}

export function Alert({
  tone = "error",
  children,
}: {
  tone?: "error" | "info" | "success";
  children: ReactNode;
}) {
  const tones = {
    error: "border-rose-500/30 bg-rose-500/10 text-rose-800 dark:text-rose-200",
    info: "border-accent/30 bg-accent/10",
    success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200",
  };
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`rounded-lg border px-3 py-2 text-sm ${tones[tone]}`}
    >
      {children}
    </div>
  );
}

export function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-4 py-10">
      <p className="text-xs font-semibold uppercase tracking-widest text-accent">WEBFORGE AI</p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">{title}</h1>
      {subtitle && <p className="mt-2 text-sm text-muted">{subtitle}</p>}
      <div className="mt-6 rounded-xl border border-line bg-surface p-5 shadow-sm">{children}</div>
    </main>
  );
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));
}
