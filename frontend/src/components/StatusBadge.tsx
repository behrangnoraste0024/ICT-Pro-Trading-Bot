interface StatusBadgeProps {
  label: string;
  tone?: "neutral" | "blocked" | "ready" | "unavailable" | "warning";
}

const toneClasses: Record<NonNullable<StatusBadgeProps["tone"]>, string> = {
  blocked: "border-amber-300 bg-amber-50 text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100",
  neutral: "border-slate-300 bg-slate-50 text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100",
  ready: "border-emerald-300 bg-emerald-50 text-emerald-950 dark:border-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-100",
  unavailable:
    "border-rose-300 bg-rose-50 text-rose-950 dark:border-rose-700 dark:bg-rose-950/40 dark:text-rose-100",
  warning: "border-sky-300 bg-sky-50 text-sky-950 dark:border-sky-700 dark:bg-sky-950/40 dark:text-sky-100",
};

export function StatusBadge({ label, tone = "neutral" }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex max-w-full items-center rounded-md border px-2.5 py-1 text-sm font-semibold leading-5 ${toneClasses[tone]}`}
    >
      <span className="break-words">{label}</span>
    </span>
  );
}
