import type { OperatorStatusResponse } from "../models/operatorStatus";
import { StatusBadge } from "./StatusBadge";
import { WarningList } from "./WarningList";

interface OperatorOverviewPanelProps {
  status: OperatorStatusResponse;
}

function boolText(value: boolean): string {
  return value ? "Yes" : "No";
}

function statusTone(
  value: string | null,
): "neutral" | "blocked" | "ready" | "unavailable" | "warning" {
  if (value === "READY" || value === "PASS" || value === "RELEASED") {
    return "ready";
  }
  if (value === "UNAVAILABLE" || value === null) {
    return "unavailable";
  }
  if (value === "WARNING") {
    return "warning";
  }
  if (value === "BLOCKED" || value === "FAIL" || value === "ENGAGED") {
    return "blocked";
  }
  return "neutral";
}

function DetailItem({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "neutral" | "blocked" | "ready" | "unavailable" | "warning";
}) {
  return (
    <div className="min-w-0 rounded-md border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <dt className="text-xs font-medium uppercase text-slate-500 dark:text-slate-400">
        {label}
      </dt>
      <dd className="mt-2">
        <StatusBadge label={value} tone={tone} />
      </dd>
    </div>
  );
}

export function OperatorOverviewPanel({ status }: OperatorOverviewPanelProps) {
  const updatedAtDate = new Date(status.updated_at);
  const updatedAtLabel = Number.isNaN(updatedAtDate.getTime())
    ? status.updated_at
    : updatedAtDate.toLocaleString();

  return (
    <section className="space-y-6" aria-labelledby="operator-overview-title">
      <div className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <h2
              id="operator-overview-title"
              className="text-xl font-semibold text-slate-950 dark:text-white"
            >
              Operator Overview
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-700 dark:text-slate-300">
              Backend-reported read-only state for Binance Futures Testnet/Demo
              BTCUSDT. Production is disabled.
            </p>
          </div>
          <StatusBadge
            label={`Overall: ${status.overall_status}`}
            tone={statusTone(status.overall_status)}
          />
        </div>
        <p className="mt-4 text-sm text-slate-600 dark:text-slate-400">
          Updated{" "}
          <time dateTime={status.updated_at} className="font-medium">
            {updatedAtLabel}
          </time>
        </p>
      </div>

      <dl className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        <DetailItem label="Environment" value={status.environment} />
        <DetailItem label="Symbol" value={status.symbol} />
        <DetailItem
          label="Kill-switch state"
          value={status.kill_switch_state ?? "Unavailable"}
          tone={statusTone(status.kill_switch_state)}
        />
        <DetailItem
          label="Kill-switch available"
          value={boolText(status.kill_switch_available)}
        />
        <DetailItem
          label="Recovery required"
          value={boolText(status.recovery_required)}
          tone={status.recovery_required ? "blocked" : "neutral"}
        />
        <DetailItem
          label="Recovery available"
          value={boolText(status.recovery_available)}
        />
        <DetailItem
          label="Persistence configured"
          value={boolText(status.persistence_configured)}
        />
        <DetailItem
          label="Persistence reachable"
          value={boolText(status.persistence_reachable)}
        />
        <DetailItem
          label="Persistence schema ready"
          value={boolText(status.persistence_schema_ready)}
        />
        <DetailItem
          label="Readiness"
          value={status.readiness_status}
          tone={statusTone(status.readiness_status)}
        />
        <DetailItem
          label="Validation gate"
          value={status.validation_gate}
          tone={statusTone(status.validation_gate)}
        />
        <DetailItem
          label="Active lock"
          value={boolText(status.active_lock)}
          tone={status.active_lock ? "blocked" : "neutral"}
        />
      </dl>

      <section
        className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
        aria-labelledby="operator-warnings-title"
      >
        <h3
          id="operator-warnings-title"
          className="text-lg font-semibold text-slate-950 dark:text-white"
        >
          Deterministic Warnings
        </h3>
        <div className="mt-3">
          <WarningList warnings={status.warnings} />
        </div>
      </section>
    </section>
  );
}
