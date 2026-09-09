import type { OperatorWarningResponse } from "../models/operatorStatus";

interface WarningListProps {
  warnings: OperatorWarningResponse[];
}

export function WarningList({ warnings }: WarningListProps) {
  if (warnings.length === 0) {
    return (
      <p className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
        No backend warnings reported.
      </p>
    );
  }

  return (
    <ul className="space-y-3" aria-label="Operator warnings">
      {warnings.map((warning) => (
        <li
          key={`${warning.source}-${warning.code}`}
          className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-100"
        >
          <p className="font-semibold break-words">{warning.message}</p>
          <p className="mt-1 break-words text-xs">
            {warning.severity} / {warning.code} / {warning.source}
          </p>
        </li>
      ))}
    </ul>
  );
}
