import { StatusBadge } from "./StatusBadge";
import type { PersistenceStatusResponse } from "../models/liveSafetyDetail";

interface PersistenceStatusPanelProps {
  persistence: PersistenceStatusResponse;
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

export function PersistenceStatusPanel({
  persistence,
}: PersistenceStatusPanelProps) {
  return (
    <section
      className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
      aria-labelledby="persistence-status-title"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2
            id="persistence-status-title"
            className="text-xl font-semibold text-slate-950 dark:text-white"
          >
            Persistence
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-700 dark:text-slate-300">
            Backend persistence status and schema-readiness details.
          </p>
        </div>
        <StatusBadge
          label={`Schema ready: ${boolText(persistence.schema_ready)}`}
          tone="neutral"
        />
      </div>

      <dl className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <Field label="Configured" value={boolText(persistence.configured)} />
        <Field label="Reachable" value={boolText(persistence.reachable)} />
        <Field
          label="Schema ready"
          value={boolText(persistence.schema_ready)}
        />
        <Field
          label="Migration revision"
          value={persistence.migration_revision ?? "Not reported"}
        />
        <Field label="Read only" value={boolText(persistence.read_only)} />
        <Field
          label="Source of truth"
          value={boolText(persistence.source_of_truth)}
        />
      </dl>

      {persistence.migration_revision === null ? (
        <p className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
          Backend reports no migration revision.
        </p>
      ) : null}

      <p className="mt-4 text-sm text-slate-600 dark:text-slate-400">
        Updated{" "}
        <time dateTime={persistence.updated_at} className="font-medium">
          {formatTime(persistence.updated_at)}
        </time>
      </p>
    </section>
  );
}
