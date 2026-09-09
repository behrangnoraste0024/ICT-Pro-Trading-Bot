import type { RecoveryStatusResponse } from "../models/recoveryStatus";
import { StatusBadge } from "./StatusBadge";

function boolText(value: boolean) {
  return value ? "Yes" : "No";
}

function nullableText(value: string | null) {
  return value ?? "Backend did not provide this value.";
}

function RecoveryDetail({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950">
      <dt className="text-xs font-medium uppercase text-slate-500 dark:text-slate-400">
        {label}
      </dt>
      <dd className="mt-2 break-words text-sm font-semibold text-slate-950 dark:text-white">
        {value}
      </dd>
    </div>
  );
}

export function RecoveryStatusPanel({
  recoveryStatus,
}: {
  recoveryStatus: RecoveryStatusResponse;
}) {
  return (
    <section
      className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900"
      aria-labelledby="recovery-status-title"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2
            id="recovery-status-title"
            className="text-lg font-semibold text-slate-950 dark:text-white"
          >
            Recovery Status
          </h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            Backend-authoritative recovery requirement detail only.
          </p>
        </div>
        <StatusBadge
          label={recoveryStatus.required ? "Recovery required" : "No recovery required"}
          tone={recoveryStatus.required ? "unavailable" : "neutral"}
        />
      </div>

      {!recoveryStatus.required ? (
        <p className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm font-medium text-emerald-950 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-100">
          Backend reports no recovery requirement.
        </p>
      ) : null}

      <dl className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-2">
        <RecoveryDetail
          label="Recovery required"
          value={boolText(recoveryStatus.required)}
        />
        <RecoveryDetail
          label="Active lock"
          value={boolText(recoveryStatus.active_lock)}
        />
        <RecoveryDetail label="Reason" value={nullableText(recoveryStatus.reason)} />
        <RecoveryDetail label="Pair ID" value={nullableText(recoveryStatus.pair_id)} />
        <RecoveryDetail label="Phase" value={nullableText(recoveryStatus.phase)} />
        <div className="min-w-0 rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950">
          <dt className="text-xs font-medium uppercase text-slate-500 dark:text-slate-400">
            Updated
          </dt>
          <dd className="mt-2 break-words text-sm font-semibold text-slate-950 dark:text-white">
            <time dateTime={recoveryStatus.updated_at}>{recoveryStatus.updated_at}</time>
          </dd>
        </div>
      </dl>
    </section>
  );
}
