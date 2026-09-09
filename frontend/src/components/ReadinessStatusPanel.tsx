import { StatusBadge } from "./StatusBadge";
import type { LiveReadinessResponse } from "../models/liveSafetyDetail";

interface ReadinessStatusPanelProps {
  readiness: LiveReadinessResponse;
}

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function Field({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="min-w-0 rounded-md border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <dt className="text-xs font-medium uppercase text-slate-500 dark:text-slate-400">
        {label}
      </dt>
      <dd className="mt-2 break-words text-sm font-semibold text-slate-950 dark:text-white">
        {value}
      </dd>
    </div>
  );
}

export function ReadinessStatusPanel({
  readiness,
}: ReadinessStatusPanelProps) {
  return (
    <section
      className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
      aria-labelledby="readiness-status-title"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2
            id="readiness-status-title"
            className="text-xl font-semibold text-slate-950 dark:text-white"
          >
            Readiness
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-700 dark:text-slate-300">
            Backend readiness report values and blocking reasons.
          </p>
        </div>
        <StatusBadge label={`Status: ${readiness.status}`} tone="neutral" />
      </div>

      <dl className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <Field label="Symbol" value={readiness.symbol} />
        <Field label="Checks passed" value={readiness.checks_passed} />
        <Field label="Checks warning" value={readiness.checks_warning} />
        <Field label="Checks failed" value={readiness.checks_failed} />
        <Field label="Validation gate" value={readiness.validation_gate} />
      </dl>

      <section className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950">
        <h3 className="text-sm font-semibold text-slate-950 dark:text-white">
          Blocking reasons
        </h3>
        {readiness.blocking_reasons.length === 0 ? (
          <p className="mt-2 text-sm text-slate-700 dark:text-slate-300">
            Backend reports no readiness blocking reasons.
          </p>
        ) : (
          <ul className="mt-2 list-disc space-y-2 pl-5 text-sm text-slate-700 dark:text-slate-300">
            {readiness.blocking_reasons.map((reason) => (
              <li key={reason} className="break-words">
                {reason}
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="mt-4 text-sm text-slate-600 dark:text-slate-400">
        Updated{" "}
        <time dateTime={readiness.updated_at} className="font-medium">
          {formatTime(readiness.updated_at)}
        </time>
      </p>
    </section>
  );
}
