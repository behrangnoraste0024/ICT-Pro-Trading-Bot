import { StatusBadge } from "./StatusBadge";
import type { LiveSafetyStatusResponse } from "../models/liveSafetyDetail";

interface SafetyStatusPanelProps {
  safetyStatus: LiveSafetyStatusResponse;
}

function boolText(value: boolean): string {
  return value ? "Yes" : "No";
}

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function Field({ label, value }: { label: string; value: string }) {
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

export function SafetyStatusPanel({ safetyStatus }: SafetyStatusPanelProps) {
  return (
    <section
      className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
      aria-labelledby="safety-status-title"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2
            id="safety-status-title"
            className="text-xl font-semibold text-slate-950 dark:text-white"
          >
            Safety Status
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-700 dark:text-slate-300">
            Backend read-only live-safety values from control-plane authority.
          </p>
        </div>
        <StatusBadge label={safetyStatus.environment} tone="neutral" />
      </div>

      <dl className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <Field
          label="Live trading enabled"
          value={boolText(safetyStatus.live_trading_enabled)}
        />
        <Field
          label="Automatic execution enabled"
          value={boolText(safetyStatus.automatic_execution_enabled)}
        />
        <Field
          label="Kill switch engaged"
          value={boolText(safetyStatus.kill_switch_engaged)}
        />
        <Field
          label="Credentials configured"
          value={boolText(safetyStatus.credentials_configured)}
        />
        <Field label="Active lock" value={boolText(safetyStatus.active_lock)} />
        <Field
          label="Recovery required"
          value={boolText(safetyStatus.recovery_required)}
        />
        <Field
          label="Production endpoint allowed"
          value={boolText(safetyStatus.production_endpoint_allowed)}
        />
      </dl>

      <p className="mt-4 text-sm text-slate-600 dark:text-slate-400">
        Updated{" "}
        <time dateTime={safetyStatus.updated_at} className="font-medium">
          {formatTime(safetyStatus.updated_at)}
        </time>
      </p>
    </section>
  );
}
