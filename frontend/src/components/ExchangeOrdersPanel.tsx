import { StatusBadge } from "./StatusBadge";
import type {
  ExchangeOrderIdentityListResponse,
  ExchangeOrderIdentityReadResponse,
} from "../models/orderVisibility";

interface ExchangeOrdersPanelProps {
  exchangeOrders: ExchangeOrderIdentityListResponse;
}

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function Field({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium uppercase text-slate-500 dark:text-slate-400">
        {label}
      </dt>
      <dd className="mt-1 break-words text-sm font-semibold text-slate-950 dark:text-white">
        {value ?? "Not reported"}
      </dd>
    </div>
  );
}

function OrderItem({ order }: { order: ExchangeOrderIdentityReadResponse }) {
  return (
    <article className="rounded-md border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h3 className="break-words text-sm font-semibold text-slate-950 dark:text-white">
            {order.leg_type}
          </h3>
          <p className="mt-1 break-words text-xs text-slate-600 dark:text-slate-400">
            {order.client_algo_id}
          </p>
        </div>
        <StatusBadge label={`Status: ${order.status}`} tone="neutral" />
      </div>

      <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Pair ID" value={order.pair_id} />
        <Field label="Correlation ID" value={order.correlation_id} />
        <Field label="Exchange algo ID" value={order.exchange_algo_id} />
        <Field label="Exchange order ID" value={order.exchange_order_id} />
        <Field label="Trigger price" value={order.trigger_price} />
        <Field label="Version" value={order.version} />
      </dl>

      <p className="mt-4 text-sm text-slate-600 dark:text-slate-400">
        Updated{" "}
        <time dateTime={order.updated_at} className="font-medium">
          {formatTime(order.updated_at)}
        </time>
      </p>
    </article>
  );
}

export function ExchangeOrdersPanel({
  exchangeOrders,
}: ExchangeOrdersPanelProps) {
  return (
    <section
      className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
      aria-labelledby="exchange-orders-title"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2
            id="exchange-orders-title"
            className="text-xl font-semibold text-slate-950 dark:text-white"
          >
            Exchange Order Identities
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-700 dark:text-slate-300">
            Backend read-only exchange-order identity and status records.
          </p>
        </div>
        <StatusBadge label={`Count: ${exchangeOrders.count}`} tone="neutral" />
      </div>

      {exchangeOrders.items.length === 0 ? (
        <p className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
          Backend reports no recent exchange-order identities.
        </p>
      ) : (
        <div className="mt-4 space-y-3">
          {exchangeOrders.items.map((order) => (
            <OrderItem key={`${order.pair_id}-${order.leg_type}`} order={order} />
          ))}
        </div>
      )}

      <p className="mt-4 text-sm text-slate-600 dark:text-slate-400">
        List updated{" "}
        <time dateTime={exchangeOrders.updated_at} className="font-medium">
          {formatTime(exchangeOrders.updated_at)}
        </time>
      </p>
    </section>
  );
}
