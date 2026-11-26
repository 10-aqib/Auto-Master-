import { formatMinor, type UsageSummary } from "@/lib/sources";

function Bar({ label, ratio, detail }: { label: string; ratio: number | null; detail: string }) {
  const pct = ratio === null ? 0 : Math.min(100, Math.round(ratio * 100));
  const tone =
    ratio !== null && ratio >= 1
      ? "bg-rose-500"
      : ratio !== null && ratio >= 0.8
        ? "bg-amber-500"
        : "bg-emerald-500";
  return (
    <div className="grid gap-1">
      <div className="flex justify-between text-xs text-muted">
        <span>{label}</span>
        <span className="tabular-nums">{detail}</span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-full bg-background"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
      >
        <div className={`h-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function UsageMeter({ usage }: { usage: UsageSummary }) {
  const money = (m: number) => formatMinor(m, usage.currency);
  return (
    <div className="grid gap-3">
      {usage.daily_budget_minor !== null ? (
        <>
          <Bar
            label="Spend today"
            ratio={usage.budget_ratio}
            detail={`${money(usage.today.cost_minor)} of ${money(usage.daily_budget_minor)}`}
          />
          <Bar
            label="Requests today"
            ratio={usage.cap_ratio}
            detail={`${usage.today.requests} of ${usage.daily_request_cap ?? 0}`}
          />
          <p className="text-xs text-muted">
            Month to date: {usage.month.requests} requests, {money(usage.month.cost_minor)} (estimated from
            configured prices).
          </p>
        </>
      ) : (
        <p className="text-xs text-muted">
          Free test source. {usage.today.requests} requests today, {usage.month.requests} this month.
        </p>
      )}
      {usage.exhausted ? (
        <p className="text-xs font-medium text-rose-700 dark:text-rose-300">
          Limit reached: new requests are blocked.
        </p>
      ) : usage.warning ? (
        <p className="text-xs font-medium text-amber-700 dark:text-amber-300">
          Over 80% of today&apos;s limit.
        </p>
      ) : null}
    </div>
  );
}
