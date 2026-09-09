import { StatusBadge } from "./StatusBadge";
import type {
  ExecutionIntentListResponse,
  ExecutionIntentReadResponse,
} from "../models/orderVisibility";

interface ExecutionIntentsPanelProps {
  executionIntents: ExecutionIntentListResponse;
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

function IntentItem({ intent }: { intent: ExecutionIntentReadResponse }) {
  return (
    <article className="rounded-md border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h3 className="break-words text-sm font-semibold text-slate-950 dark:text-white">
            {intent.intent_type}
          </h3>
          <p className="mt-1 break-words text-xs text-slate-600 dark:text-slate-400">
            {intent.correlation_id}
          </p>
        </div>
        <StatusBadge label={`State: ${intent.state}`} tone="neutral" />
      </div>

      <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Environment" value={intent.environment} />
        <Field label="Symbol" value={intent.symbol} />
        <Field label="Quantity" value={intent.requested_quantity} />
        <Field label="Price" value={intent.requested_price} />
        <Field label="Failure code" value={intent.failure_code} />
        <Field label="Version" value={intent.version} />
      </dl>

      <p className="mt-4 text-sm text-slate-600 dark:text-slate-400">
        Updated{" "}
        <time dateTime={intent.updated_at} className="font-medium">
          {formatTime(intent.updated_at)}
        </time>
      </p>
    </article>
  );
}

export function ExecutionIntentsPanel({
  executionIntents,
}: ExecutionIntentsPanelProps) {
  return (
    <section
      className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
      aria-labelledby="execution-intents-title"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2
            id="execution-intents-title"
            className="text-xl font-semibold text-slate-950 dark:text-white"
          >
            Execution Intents
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-700 dark:text-slate-300">
            Backend read-only intent records from durable persistence.
          </p>
        </div>
        <StatusBadge label={`Count: ${executionIntents.count}`} tone="neutral" />
      </div>

      {executionIntents.items.length === 0 ? (
        <p className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
          Backend reports no recent execution intents.
        </p>
      ) : (
        <div className="mt-4 space-y-3">
          {executionIntents.items.map((intent) => (
            <IntentItem key={intent.correlation_id} intent={intent} />
          ))}
        </div>
      )}

      <p className="mt-4 text-sm text-slate-600 dark:text-slate-400">
        List updated{" "}
        <time dateTime={executionIntents.updated_at} className="font-medium">
          {formatTime(executionIntents.updated_at)}
        </time>
      </p>
    </section>
  );
}
