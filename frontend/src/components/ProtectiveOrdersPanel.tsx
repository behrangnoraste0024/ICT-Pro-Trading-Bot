import { StatusBadge } from "./StatusBadge";
import type {
  ProtectiveOrderSummaryResponse,
  ProtectiveOrdersCurrentResponse,
} from "../models/positionProtection";

interface ProtectiveOrdersPanelProps {
  protectiveOrders: ProtectiveOrdersCurrentResponse;
}

function boolText(value: boolean): string {
  return value ? "Yes" : "No";
}

function Summary({
  label,
  summary,
}: {
  label: string;
  summary: ProtectiveOrderSummaryResponse | null;
}) {
  if (summary === null) {
    return (
      <section className="rounded-md border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950">
        <h3 className="text-sm font-semibold text-slate-950 dark:text-white">
          {label}
        </h3>
        <p className="mt-2 text-sm text-slate-700 dark:text-slate-300">
          Backend reports no {label.toLowerCase()} summary.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-md border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <h3 className="text-sm font-semibold text-slate-950 dark:text-white">
        {label}
      </h3>
      <dl className="mt-3 grid grid-cols-1 gap-2 text-sm">
        <div>
          <dt className="text-slate-500 dark:text-slate-400">Client algo ID</dt>
          <dd className="break-words font-medium text-slate-950 dark:text-white">
            {summary.client_algo_id ?? "Not reported"}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500 dark:text-slate-400">Algo ID</dt>
          <dd className="break-words font-medium text-slate-950 dark:text-white">
            {summary.algo_id ?? "Not reported"}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500 dark:text-slate-400">Status</dt>
          <dd className="break-words font-medium text-slate-950 dark:text-white">
            {summary.status ?? "Not reported"}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500 dark:text-slate-400">Trigger price</dt>
          <dd className="break-words font-medium text-slate-950 dark:text-white">
            {summary.trigger_price ?? "Not reported"}
          </dd>
        </div>
      </dl>
    </section>
  );
}

export function ProtectiveOrdersPanel({
  protectiveOrders,
}: ProtectiveOrdersPanelProps) {
  const updatedAt = new Date(protectiveOrders.updated_at);
  const updatedLabel = Number.isNaN(updatedAt.getTime())
    ? protectiveOrders.updated_at
    : updatedAt.toLocaleString();

  return (
    <section
      className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
      aria-labelledby="protective-orders-title"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2
            id="protective-orders-title"
            className="text-xl font-semibold text-slate-950 dark:text-white"
          >
            Current Protective Orders
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-700 dark:text-slate-300">
            Backend-reported current protective-order state only.
          </p>
        </div>
        <StatusBadge label={`State: ${protectiveOrders.state}`} tone="neutral" />
      </div>

      {protectiveOrders.state === "NONE" ? (
        <p className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
          Backend reports no current protective-order lifecycle.
        </p>
      ) : null}

      <dl className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="rounded-md border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <dt className="text-xs font-medium uppercase text-slate-500 dark:text-slate-400">
            Pair ID
          </dt>
          <dd className="mt-2 break-words text-sm font-semibold text-slate-950 dark:text-white">
            {protectiveOrders.pair_id ?? "Not reported"}
          </dd>
        </div>
        <div className="rounded-md border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <dt className="text-xs font-medium uppercase text-slate-500 dark:text-slate-400">
            Recovery required
          </dt>
          <dd className="mt-2 break-words text-sm font-semibold text-slate-950 dark:text-white">
            {boolText(protectiveOrders.recovery_required)}
          </dd>
        </div>
        <div className="rounded-md border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <dt className="text-xs font-medium uppercase text-slate-500 dark:text-slate-400">
            Active lock
          </dt>
          <dd className="mt-2 break-words text-sm font-semibold text-slate-950 dark:text-white">
            {boolText(protectiveOrders.active_lock)}
          </dd>
        </div>
        <div className="rounded-md border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <dt className="text-xs font-medium uppercase text-slate-500 dark:text-slate-400">
            Blocking reason
          </dt>
          <dd className="mt-2 break-words text-sm font-semibold text-slate-950 dark:text-white">
            {protectiveOrders.blocking_reason ?? "None reported"}
          </dd>
        </div>
      </dl>

      <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Summary label="Stop" summary={protectiveOrders.stop} />
        <Summary label="Take profit" summary={protectiveOrders.take_profit} />
      </div>

      <p className="mt-4 text-sm text-slate-600 dark:text-slate-400">
        Updated{" "}
        <time dateTime={protectiveOrders.updated_at} className="font-medium">
          {updatedLabel}
        </time>
      </p>
    </section>
  );
}
