interface BackendUnavailableStateProps {
  kind: "forbidden" | "malformed" | "unavailable";
}

const messages: Record<BackendUnavailableStateProps["kind"], string> = {
  forbidden:
    "Operator status is forbidden. The dashboard cannot establish backend authority.",
  malformed:
    "Operator status payload is malformed. The dashboard is failing closed.",
  unavailable:
    "Operator status is unavailable. The dashboard cannot infer current safety state.",
};

export function BackendUnavailableState({ kind }: BackendUnavailableStateProps) {
  return (
    <section
      className="rounded-lg border border-rose-300 bg-rose-50 p-5 text-rose-950 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-100"
      aria-live="polite"
    >
      <h2 className="text-lg font-semibold">Backend authority unavailable</h2>
      <p className="mt-2 text-sm leading-6">{messages[kind]}</p>
      <p className="mt-3 text-sm font-medium">
        Current operator state is not shown without a valid backend response.
      </p>
    </section>
  );
}
