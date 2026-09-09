import { type FormEvent, useRef, useState } from "react";
import {
  BadRequestReadOnlyRequestError,
  ForbiddenReadOnlyRequestError,
  MalformedReadOnlyResponseError,
  NotFoundReadOnlyRequestError,
  readOnlyClient,
  UnavailableReadOnlyRequestError,
} from "../api/readOnlyClient";
import type { PairAuditResponse } from "../models/pairAudit";

const PAIR_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$/;
const DEFAULT_LIMIT = 50;
const DEFAULT_OFFSET = 0;

type PairAuditState =
  | { status: "idle" }
  | { status: "invalid" }
  | { status: "loading"; pairId: string }
  | { status: "success"; data: PairAuditResponse }
  | {
      status: "bad-request" | "forbidden" | "not-found" | "unavailable" | "malformed";
      pairId: string;
    };

type PairAuditErrorState = Extract<
  PairAuditState,
  {
    status: "bad-request" | "forbidden" | "not-found" | "unavailable" | "malformed";
  }
>;

function textOrNotReported(value: string | null) {
  return value ?? "Not reported by backend";
}

function errorMessage(state: PairAuditErrorState) {
  switch (state.status) {
    case "bad-request":
      return "The backend rejected this pair-scoped request. No event state is inferred.";
    case "forbidden":
      return "Pair-scoped event history is forbidden. No event state is inferred.";
    case "not-found":
      return "The backend did not find this protective pair. No event state is inferred.";
    case "malformed":
      return "Pair-scoped event history payload is malformed. The dashboard is failing closed.";
    case "unavailable":
      return "Pair-scoped event history is unavailable. No event state is inferred.";
  }
}

export function PairAuditPanel() {
  const [pairIdInput, setPairIdInput] = useState("");
  const [state, setState] = useState<PairAuditState>({ status: "idle" });
  const inFlightKey = useRef<string | null>(null);

  const submitPairAuditRequest = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const pairId = pairIdInput.trim();
    if (!PAIR_ID_PATTERN.test(pairId)) {
      setState({ status: "invalid" });
      return;
    }

    const requestKey = `${pairId}:${DEFAULT_LIMIT}:${DEFAULT_OFFSET}`;
    if (inFlightKey.current === requestKey) {
      return;
    }

    inFlightKey.current = requestKey;
    setState({ status: "loading", pairId });

    void readOnlyClient
      .protectivePairEvents(pairId, DEFAULT_LIMIT, DEFAULT_OFFSET)
      .then((data) => {
        setState({ status: "success", data });
      })
      .catch((error: unknown) => {
        if (error instanceof BadRequestReadOnlyRequestError) {
          setState({ status: "bad-request", pairId });
          return;
        }
        if (error instanceof ForbiddenReadOnlyRequestError) {
          setState({ status: "forbidden", pairId });
          return;
        }
        if (error instanceof NotFoundReadOnlyRequestError) {
          setState({ status: "not-found", pairId });
          return;
        }
        if (error instanceof MalformedReadOnlyResponseError) {
          setState({ status: "malformed", pairId });
          return;
        }
        if (error instanceof UnavailableReadOnlyRequestError) {
          setState({ status: "unavailable", pairId });
          return;
        }
        setState({ status: "unavailable", pairId });
      })
      .finally(() => {
        if (inFlightKey.current === requestKey) {
          inFlightKey.current = null;
        }
      });
  };

  const requestPending = state.status === "loading";

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm font-medium uppercase text-slate-500 dark:text-slate-400">
          Pair-scoped activity
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-950 dark:text-white">
          Pair-Scoped Audit Activity
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-700 dark:text-slate-300">
          Read-only backend event history for one protective pair only. Enter one
          protective pair ID to request its event timeline.
        </p>
      </header>

      <form
        className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
        onSubmit={submitPairAuditRequest}
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
          <label
            className="flex min-w-0 flex-1 flex-col gap-2 text-sm font-medium text-slate-800 dark:text-slate-200"
            htmlFor="pair-audit-pair-id"
          >
            Protective pair ID
            <input
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-950 outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-500/30 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-50"
              id="pair-audit-pair-id"
              name="pair_id"
              onChange={(event) => setPairIdInput(event.target.value)}
              type="text"
              value={pairIdInput}
            />
          </label>
          <button
            className="rounded-md bg-slate-950 px-4 py-2 text-sm font-semibold text-white outline-none hover:bg-slate-800 focus:ring-2 focus:ring-sky-500/40 disabled:cursor-not-allowed disabled:bg-slate-500 dark:bg-slate-100 dark:text-slate-950 dark:hover:bg-white"
            disabled={requestPending}
            type="submit"
          >
            {requestPending ? "Loading pair events" : "Load pair events"}
          </button>
        </div>
        <p className="mt-3 text-xs leading-5 text-slate-600 dark:text-slate-400">
          Accepted format mirrors backend validation: starts with a letter or digit,
          then letters, digits, period, underscore, colon, or hyphen up to 80
          characters.
        </p>
      </form>

      {state.status === "idle" ? (
        <section
          className="rounded-lg border border-slate-200 bg-white p-5 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300"
          aria-live="polite"
        >
          No pair-scoped event request has been submitted.
        </section>
      ) : null}

      {state.status === "invalid" ? (
        <section
          className="rounded-lg border border-amber-300 bg-amber-50 p-5 text-amber-950 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-100"
          aria-live="polite"
        >
          <h2 className="text-lg font-semibold">Invalid protective pair ID</h2>
          <p className="mt-2 text-sm leading-6">
            No request was sent. Enter one backend protective pair ID before loading
            pair-scoped events.
          </p>
        </section>
      ) : null}

      {state.status === "loading" ? (
        <section
          className="rounded-lg border border-slate-200 bg-white p-5 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300"
          aria-live="polite"
        >
          Loading pair-scoped event history for{" "}
          <span className="break-all font-mono">{state.pairId}</span>.
        </section>
      ) : null}

      {state.status === "bad-request" ||
      state.status === "forbidden" ||
      state.status === "not-found" ||
      state.status === "unavailable" ||
      state.status === "malformed" ? (
        <section
          className="rounded-lg border border-rose-300 bg-rose-50 p-5 text-rose-950 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-100"
          aria-live="polite"
        >
          <h2 className="text-lg font-semibold">Pair-scoped event view unavailable</h2>
          <p className="mt-2 break-words text-sm leading-6">
            Protective pair: <span className="font-mono">{state.pairId}</span>
          </p>
          <p className="mt-2 text-sm leading-6">{errorMessage(state)}</p>
        </section>
      ) : null}

      {state.status === "success" ? (
        <section className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-slate-950 dark:text-white">
                Pair-scoped event history
              </h2>
              <p className="mt-2 break-all text-sm text-slate-700 dark:text-slate-300">
                Protective pair:{" "}
                <span className="font-mono">{state.data.pair_id}</span>
              </p>
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              limit {state.data.limit}, offset {state.data.offset}
            </p>
          </div>

          {state.data.events.length === 0 ? (
            <p className="mt-5 rounded-md border border-slate-200 p-4 text-sm text-slate-700 dark:border-slate-800 dark:text-slate-300">
              Backend reports no pair-scoped events for this protective pair.
            </p>
          ) : (
            <div className="mt-5 grid gap-4">
              {state.data.events.map((event, index) => (
                <article
                  className="rounded-lg border border-slate-200 p-4 dark:border-slate-800"
                  key={`${event.created_at}-${event.event_kind}-${index}`}
                >
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <h3 className="break-words text-base font-semibold text-slate-950 dark:text-white">
                      {event.event_kind}
                    </h3>
                    <time
                      className="break-words font-mono text-xs text-slate-600 dark:text-slate-400"
                      dateTime={event.created_at}
                    >
                      {event.created_at}
                    </time>
                  </div>
                  <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
                    {[
                      ["Correlation ID", textOrNotReported(event.correlation_id)],
                      ["Event type", textOrNotReported(event.event_type)],
                      ["Action", textOrNotReported(event.action)],
                      ["From state", textOrNotReported(event.from_state)],
                      ["To state", textOrNotReported(event.to_state)],
                      ["Reason code", textOrNotReported(event.reason_code)],
                      ["Result", event.result],
                      ["Error code", textOrNotReported(event.error_code)],
                    ].map(([label, value]) => (
                      <div className="min-w-0" key={label}>
                        <dt className="text-xs font-medium uppercase text-slate-500 dark:text-slate-400">
                          {label}
                        </dt>
                        <dd className="mt-1 break-words font-mono text-slate-950 dark:text-slate-100">
                          {value}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </article>
              ))}
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}
