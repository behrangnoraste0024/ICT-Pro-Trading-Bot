import { StatusBadge } from "./StatusBadge";
import type { KillSwitchControlResponse } from "../models/liveSafetyDetail";

interface KillSwitchStatusPanelProps {
  killSwitch: KillSwitchControlResponse;
}

function boolText(value: boolean): string {
  return value ? "Yes" : "No";
}

function formatNullableTime(value: string | null): string {
  if (value === null) {
    return "Not reported";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function Field({
  label,
  value,
}: {
  label: string;
  value: string | number | null;
}) {
  return (
    <div className="min-w-0 rounded-md border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <dt className="text-xs font-medium uppercase text-slate-500 dark:text-slate-400">
        {label}
      </dt>
      <dd className="mt-2 break-words text-sm font-semibold text-slate-950 dark:text-white">
        {value ?? "Not reported"}
      </dd>
    </div>
  );
}

export function KillSwitchStatusPanel({
  killSwitch,
}: KillSwitchStatusPanelProps) {
  return (
    <section
      className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
      aria-labelledby="kill-switch-status-title"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2
            id="kill-switch-status-title"
            className="text-xl font-semibold text-slate-950 dark:text-white"
          >
            Kill Switch Status
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-700 dark:text-slate-300">
            Backend read-only kill-switch status. No action controls are present.
          </p>
        </div>
        <StatusBadge label={`State: ${killSwitch.state ?? "Not reported"}`} />
      </div>

      <dl className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <Field label="Accepted" value={boolText(killSwitch.accepted)} />
        <Field label="Environment" value={killSwitch.environment} />
        <Field label="Symbol" value={killSwitch.symbol} />
        <Field label="State" value={killSwitch.state} />
        <Field label="Changed" value={boolText(killSwitch.changed)} />
        <Field label="Version" value={killSwitch.version} />
        <Field label="Blocking code" value={killSwitch.blocking_code} />
      </dl>

      {killSwitch.state === null ||
      killSwitch.version === null ||
      killSwitch.updated_at === null ||
      killSwitch.blocking_code === null ? (
        <p className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
          Backend reports one or more nullable kill-switch fields as not reported.
        </p>
      ) : null}

      <p className="mt-4 text-sm text-slate-600 dark:text-slate-400">
        Updated{" "}
        {killSwitch.updated_at === null ? (
          <span className="font-medium">Not reported</span>
        ) : (
          <time dateTime={killSwitch.updated_at} className="font-medium">
            {formatNullableTime(killSwitch.updated_at)}
          </time>
        )}
      </p>
    </section>
  );
}
