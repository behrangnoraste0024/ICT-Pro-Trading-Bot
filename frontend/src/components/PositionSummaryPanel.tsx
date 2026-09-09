import { StatusBadge } from "./StatusBadge";
import type { PositionResponse } from "../models/positionProtection";

interface PositionSummaryPanelProps {
  position: PositionResponse;
}

function Field({ label, value }: { label: string; value: string | null }) {
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

export function PositionSummaryPanel({ position }: PositionSummaryPanelProps) {
  const updatedAt = new Date(position.updated_at);
  const updatedLabel = Number.isNaN(updatedAt.getTime())
    ? position.updated_at
    : updatedAt.toLocaleString();

  return (
    <section
      className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
      aria-labelledby="position-summary-title"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2
            id="position-summary-title"
            className="text-xl font-semibold text-slate-950 dark:text-white"
          >
            BTCUSDT Position
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-700 dark:text-slate-300">
            Backend read-only position exposure from Testnet/Demo authority.
          </p>
        </div>
        <StatusBadge
          label={position.has_open_position ? "Open position reported" : "No open position reported"}
          tone={position.has_open_position ? "warning" : "neutral"}
        />
      </div>

      {!position.has_open_position ? (
        <p className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
          Backend reports no open BTCUSDT position.
        </p>
      ) : null}

      <dl className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Field label="Symbol" value={position.symbol} />
        <Field label="Position side" value={position.position_side} />
        <Field label="Direction" value={position.direction} />
        <Field label="Quantity" value={position.quantity} />
        <Field label="Entry price" value={position.entry_price} />
        <Field label="Break-even price" value={position.break_even_price} />
        <Field label="Mark price" value={position.mark_price} />
        <Field label="Notional USDT" value={position.notional_usdt} />
        <Field label="Unrealized PnL" value={position.unrealized_pnl} />
        <Field label="Liquidation price" value={position.liquidation_price} />
        <Field label="Source" value={position.source} />
      </dl>

      <p className="mt-4 text-sm text-slate-600 dark:text-slate-400">
        Updated{" "}
        <time dateTime={position.updated_at} className="font-medium">
          {updatedLabel}
        </time>
      </p>
    </section>
  );
}
