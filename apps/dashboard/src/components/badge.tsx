const TONES: Record<string, string> = {
  good: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 ring-emerald-500/30",
  warn: "bg-amber-500/15 text-amber-800 dark:text-amber-300 ring-amber-500/30",
  bad: "bg-rose-500/15 text-rose-700 dark:text-rose-300 ring-rose-500/30",
  neutral: "bg-background text-muted ring-line",
};

const BY_VALUE: Record<string, keyof typeof TONES> = {
  ACTIVE: "good",
  SUCCEEDED: "good",
  STRONG: "good",
  POTENTIAL: "good",
  QUALIFIED: "good",
  VERIFIED: "good",
  PAUSED: "warn",
  RETRYING: "warn",
  QUEUED: "warn",
  RUNNING: "warn",
  INVESTIGATE: "warn",
  HOLD: "warn",
  MANUAL_REVIEW: "warn",
  HUMAN_REVIEW: "warn",
  QUALIFYING: "warn",
  DRAFT: "neutral",
  APPROVED: "good",
  NEEDS_REVIEW: "warn",
  FAILED: "bad",
  DEAD: "bad",
  REJECTED: "bad",
  DO_NOT_CONTACT: "bad",
  CANCELLED: "neutral",
};

export function Badge({ value, label }: { value: string; label?: string }) {
  const tone = TONES[BY_VALUE[value] ?? "neutral"];
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${tone}`}
    >
      {label ?? value.toLowerCase().replaceAll("_", " ")}
    </span>
  );
}
