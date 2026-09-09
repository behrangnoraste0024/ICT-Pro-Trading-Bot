import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import {
  ForbiddenReadOnlyRequestError,
  MalformedReadOnlyResponseError,
  readOnlyClient,
  UnavailableReadOnlyRequestError,
} from "./api/readOnlyClient";
import { BackendUnavailableState } from "./components/BackendUnavailableState";
import { LiveSafetyDetailPanel } from "./components/LiveSafetyDetailPanel";
import { OperatorOverviewPanel } from "./components/OperatorOverviewPanel";
import { OrdersVisibilityPanel } from "./components/OrdersVisibilityPanel";
import { PairAuditPanel } from "./components/PairAuditPanel";
import { PositionProtectionPanel } from "./components/PositionProtectionPanel";
import { RefreshButton } from "./components/RefreshButton";
import { RecoveryStatusPanel } from "./components/RecoveryStatusPanel";
import type {
  KillSwitchControlResponse,
  LiveReadinessResponse,
  LiveSafetyStatusResponse,
  PersistenceStatusResponse,
} from "./models/liveSafetyDetail";
import type { OperatorStatusResponse } from "./models/operatorStatus";
import type {
  ExchangeOrderIdentityListResponse,
  ExecutionIntentListResponse,
} from "./models/orderVisibility";
import type {
  PositionResponse,
  ProtectiveOrdersCurrentResponse,
} from "./models/positionProtection";
import type { RecoveryStatusResponse } from "./models/recoveryStatus";

type ReadOnlyErrorKind = "forbidden" | "malformed" | "unavailable";

function errorKindFrom(error: unknown): ReadOnlyErrorKind {
  if (error instanceof ForbiddenReadOnlyRequestError) {
    return "forbidden";
  }
  if (error instanceof MalformedReadOnlyResponseError) {
    return "malformed";
  }
  if (error instanceof UnavailableReadOnlyRequestError) {
    return "unavailable";
  }
  return "unavailable";
}

type PositionProtectionData = {
  position: PositionResponse;
  protectiveOrders: ProtectiveOrdersCurrentResponse;
};

type OrdersVisibilityData = {
  executionIntents: ExecutionIntentListResponse;
  exchangeOrders: ExchangeOrderIdentityListResponse;
};

type LiveSafetyDetailData = {
  safetyStatus: LiveSafetyStatusResponse;
  readiness: LiveReadinessResponse;
  persistence: PersistenceStatusResponse;
  killSwitch: KillSwitchControlResponse;
};

function RecoveryUnavailableState({ kind }: { kind: ReadOnlyErrorKind }) {
  const message = {
    forbidden:
      "Recovery status detail is forbidden. The dashboard is failing closed.",
    malformed:
      "Recovery status payload is malformed. The dashboard is failing closed.",
    unavailable:
      "Recovery status detail is unavailable. Current recovery state is not inferred.",
  }[kind];

  return (
    <section
      className="rounded-lg border border-rose-300 bg-rose-50 p-5 text-rose-950 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-100"
      aria-live="polite"
    >
      <h2 className="text-lg font-semibold">Recovery view unavailable</h2>
      <p className="mt-2 text-sm leading-6">{message}</p>
    </section>
  );
}

function RecoveryRoute() {
  const [data, setData] = useState<RecoveryStatusResponse | null>(null);
  const [errorKind, setErrorKind] = useState<ReadOnlyErrorKind | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshInProgress, setRefreshInProgress] = useState(false);
  const requestInProgress = useRef(false);
  const abortController = useRef<AbortController | null>(null);

  useEffect(() => {
    if (requestInProgress.current) {
      return undefined;
    }

    requestInProgress.current = true;
    const controller = new AbortController();
    abortController.current = controller;
    let ignoreResult = false;

    void readOnlyClient
      .recoveryStatus(controller.signal)
      .then((recoveryStatus) => {
        if (ignoreResult) {
          return;
        }
        setData(recoveryStatus);
        setErrorKind(null);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        if (ignoreResult) {
          return;
        }
        setData(null);
        setErrorKind(errorKindFrom(error));
      })
      .finally(() => {
        if (ignoreResult) {
          return;
        }
        if (abortController.current === controller) {
          abortController.current = null;
        }
        requestInProgress.current = false;
        setLoading(false);
      });

    return () => {
      ignoreResult = true;
      abortController.current?.abort();
    };
  }, []);

  const refreshStatus = useCallback(() => {
    if (requestInProgress.current) {
      return;
    }

    requestInProgress.current = true;
    abortController.current?.abort();

    const controller = new AbortController();
    abortController.current = controller;
    setErrorKind(null);
    setRefreshInProgress(true);

    void readOnlyClient
      .recoveryStatus(controller.signal)
      .then((recoveryStatus) => {
        setData(recoveryStatus);
        setErrorKind(null);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setData(null);
        setErrorKind(errorKindFrom(error));
      })
      .finally(() => {
        if (abortController.current === controller) {
          abortController.current = null;
        }
        requestInProgress.current = false;
        setRefreshInProgress(false);
      });
  }, []);

  const isPending = loading || refreshInProgress;

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium uppercase text-slate-500 dark:text-slate-400">
            Read-only recovery
          </p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-950 dark:text-white">
            Recovery Detail
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-700 dark:text-slate-300">
            Backend-authoritative recovery requirement detail. Production disabled.
          </p>
        </div>
        <RefreshButton disabled={isPending} onRefresh={refreshStatus} />
      </header>

      {loading ? (
        <p
          className="rounded-lg border border-slate-200 bg-white p-5 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300"
          aria-live="polite"
        >
          Loading recovery status from backend authority.
        </p>
      ) : null}

      {refreshInProgress ? (
        <p className="text-sm text-slate-600 dark:text-slate-400" aria-live="polite">
          Refreshing recovery status.
        </p>
      ) : null}

      {errorKind ? <RecoveryUnavailableState kind={errorKind} /> : null}
      {!loading && !errorKind && data ? (
        <RecoveryStatusPanel recoveryStatus={data} />
      ) : null}
    </div>
  );
}

function DashboardRoute() {
  const [data, setData] = useState<OperatorStatusResponse | null>(null);
  const [errorKind, setErrorKind] = useState<ReadOnlyErrorKind | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshInProgress, setRefreshInProgress] = useState(false);
  const requestInProgress = useRef(false);
  const abortController = useRef<AbortController | null>(null);

  useEffect(() => {
    if (requestInProgress.current) {
      return undefined;
    }

    requestInProgress.current = true;
    const controller = new AbortController();
    abortController.current = controller;
    let ignoreResult = false;

    void readOnlyClient
      .operatorStatus(controller.signal)
      .then((status) => {
        if (ignoreResult) {
          return;
        }
        setData(status);
        setErrorKind(null);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        if (ignoreResult) {
          return;
        }
        setData(null);
        setErrorKind(errorKindFrom(error));
      })
      .finally(() => {
        if (ignoreResult) {
          return;
        }
        if (abortController.current === controller) {
          abortController.current = null;
        }
        requestInProgress.current = false;
        setLoading(false);
      });

    return () => {
      ignoreResult = true;
      abortController.current?.abort();
    };
  }, []);

  const refreshStatus = useCallback(() => {
    if (requestInProgress.current) {
      return;
    }

    requestInProgress.current = true;
    abortController.current?.abort();

    const controller = new AbortController();
    abortController.current = controller;
    setErrorKind(null);
    setRefreshInProgress(true);

    void readOnlyClient
      .operatorStatus(controller.signal)
      .then((status) => {
        setData(status);
        setErrorKind(null);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setData(null);
        setErrorKind(errorKindFrom(error));
      })
      .finally(() => {
        if (abortController.current === controller) {
          abortController.current = null;
        }
        requestInProgress.current = false;
        setRefreshInProgress(false);
      });
  }, []);

  const isPending = loading || refreshInProgress;

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium uppercase text-slate-500 dark:text-slate-400">
            Read-only dashboard
          </p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-950 dark:text-white">
            Operator Overview
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-700 dark:text-slate-300">
            Same-origin backend authority only. Binance Futures Testnet/Demo,
            BTCUSDT, Production disabled.
          </p>
        </div>
        <RefreshButton
          disabled={isPending}
          onRefresh={refreshStatus}
        />
      </header>

      {loading ? (
        <p
          className="rounded-lg border border-slate-200 bg-white p-5 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300"
          aria-live="polite"
        >
          Loading operator status from backend authority.
        </p>
      ) : null}

      {refreshInProgress ? (
        <p className="text-sm text-slate-600 dark:text-slate-400" aria-live="polite">
          Refreshing operator status.
        </p>
      ) : null}

      {errorKind ? <BackendUnavailableState kind={errorKind} /> : null}
      {!loading && !errorKind && data ? (
        <OperatorOverviewPanel status={data} />
      ) : null}
    </div>
  );
}

function PositionsUnavailableState({ kind }: { kind: ReadOnlyErrorKind }) {
  const message = {
    forbidden:
      "Position or protective-order status is forbidden. The dashboard is failing closed.",
    malformed:
      "Position or protective-order payload is malformed. The dashboard is failing closed.",
    unavailable:
      "Position or protective-order status is unavailable. Current exposure is not inferred.",
  }[kind];

  return (
    <section
      className="rounded-lg border border-rose-300 bg-rose-50 p-5 text-rose-950 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-100"
      aria-live="polite"
    >
      <h2 className="text-lg font-semibold">Position view unavailable</h2>
      <p className="mt-2 text-sm leading-6">{message}</p>
    </section>
  );
}

function PositionsRoute() {
  const [data, setData] = useState<PositionProtectionData | null>(null);
  const [errorKind, setErrorKind] = useState<ReadOnlyErrorKind | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshInProgress, setRefreshInProgress] = useState(false);
  const requestInProgress = useRef(false);
  const abortController = useRef<AbortController | null>(null);

  useEffect(() => {
    if (requestInProgress.current) {
      return undefined;
    }

    requestInProgress.current = true;
    const controller = new AbortController();
    abortController.current = controller;
    let ignoreResult = false;

    void Promise.all([
      readOnlyClient.position(controller.signal),
      readOnlyClient.protectiveOrders(controller.signal),
    ])
      .then(([position, protectiveOrders]) => {
        if (ignoreResult) {
          return;
        }
        setData({ position, protectiveOrders });
        setErrorKind(null);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        if (ignoreResult) {
          return;
        }
        setData(null);
        setErrorKind(errorKindFrom(error));
      })
      .finally(() => {
        if (ignoreResult) {
          return;
        }
        if (abortController.current === controller) {
          abortController.current = null;
        }
        requestInProgress.current = false;
        setLoading(false);
      });

    return () => {
      ignoreResult = true;
      abortController.current?.abort();
    };
  }, []);

  const refreshStatus = useCallback(() => {
    if (requestInProgress.current) {
      return;
    }

    requestInProgress.current = true;
    abortController.current?.abort();

    const controller = new AbortController();
    abortController.current = controller;
    setErrorKind(null);
    setRefreshInProgress(true);

    void Promise.all([
      readOnlyClient.position(controller.signal),
      readOnlyClient.protectiveOrders(controller.signal),
    ])
      .then(([position, protectiveOrders]) => {
        setData({ position, protectiveOrders });
        setErrorKind(null);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setData(null);
        setErrorKind(errorKindFrom(error));
      })
      .finally(() => {
        if (abortController.current === controller) {
          abortController.current = null;
        }
        requestInProgress.current = false;
        setRefreshInProgress(false);
      });
  }, []);

  const isPending = loading || refreshInProgress;

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium uppercase text-slate-500 dark:text-slate-400">
            Read-only exposure
          </p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-950 dark:text-white">
            Positions and Protective Orders
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-700 dark:text-slate-300">
            Backend-authoritative BTCUSDT exposure and current protective-order
            state. Production disabled.
          </p>
        </div>
        <RefreshButton
          disabled={isPending}
          onRefresh={refreshStatus}
        />
      </header>

      {loading ? (
        <p
          className="rounded-lg border border-slate-200 bg-white p-5 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300"
          aria-live="polite"
        >
          Loading BTCUSDT position and protective-order state from backend authority.
        </p>
      ) : null}

      {refreshInProgress ? (
        <p className="text-sm text-slate-600 dark:text-slate-400" aria-live="polite">
          Refreshing position and protective-order state.
        </p>
      ) : null}

      {errorKind ? <PositionsUnavailableState kind={errorKind} /> : null}
      {!loading && !errorKind && data ? (
        <PositionProtectionPanel
          position={data.position}
          protectiveOrders={data.protectiveOrders}
        />
      ) : null}
    </div>
  );
}

function OrdersUnavailableState({ kind }: { kind: ReadOnlyErrorKind }) {
  const message = {
    forbidden:
      "Execution-intent or exchange-order visibility is forbidden. The dashboard is failing closed.",
    malformed:
      "Execution-intent or exchange-order payload is malformed. The dashboard is failing closed.",
    unavailable:
      "Execution-intent or exchange-order visibility is unavailable. Current order state is not inferred.",
  }[kind];

  return (
    <section
      className="rounded-lg border border-rose-300 bg-rose-50 p-5 text-rose-950 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-100"
      aria-live="polite"
    >
      <h2 className="text-lg font-semibold">Orders view unavailable</h2>
      <p className="mt-2 text-sm leading-6">{message}</p>
    </section>
  );
}

function OrdersRoute() {
  const [data, setData] = useState<OrdersVisibilityData | null>(null);
  const [errorKind, setErrorKind] = useState<ReadOnlyErrorKind | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshInProgress, setRefreshInProgress] = useState(false);
  const requestInProgress = useRef(false);
  const abortController = useRef<AbortController | null>(null);

  useEffect(() => {
    if (requestInProgress.current) {
      return undefined;
    }

    requestInProgress.current = true;
    const controller = new AbortController();
    abortController.current = controller;
    let ignoreResult = false;

    void Promise.all([
      readOnlyClient.executionIntents(controller.signal),
      readOnlyClient.exchangeOrders(controller.signal),
    ])
      .then(([executionIntents, exchangeOrders]) => {
        if (ignoreResult) {
          return;
        }
        setData({ executionIntents, exchangeOrders });
        setErrorKind(null);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        if (ignoreResult) {
          return;
        }
        setData(null);
        setErrorKind(errorKindFrom(error));
      })
      .finally(() => {
        if (ignoreResult) {
          return;
        }
        if (abortController.current === controller) {
          abortController.current = null;
        }
        requestInProgress.current = false;
        setLoading(false);
      });

    return () => {
      ignoreResult = true;
      abortController.current?.abort();
    };
  }, []);

  const refreshStatus = useCallback(() => {
    if (requestInProgress.current) {
      return;
    }

    requestInProgress.current = true;
    abortController.current?.abort();

    const controller = new AbortController();
    abortController.current = controller;
    setErrorKind(null);
    setRefreshInProgress(true);

    void Promise.all([
      readOnlyClient.executionIntents(controller.signal),
      readOnlyClient.exchangeOrders(controller.signal),
    ])
      .then(([executionIntents, exchangeOrders]) => {
        setData({ executionIntents, exchangeOrders });
        setErrorKind(null);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setData(null);
        setErrorKind(errorKindFrom(error));
      })
      .finally(() => {
        if (abortController.current === controller) {
          abortController.current = null;
        }
        requestInProgress.current = false;
        setRefreshInProgress(false);
      });
  }, []);

  const isPending = loading || refreshInProgress;

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium uppercase text-slate-500 dark:text-slate-400">
            Read-only orders
          </p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-950 dark:text-white">
            Orders and Execution Intents
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-700 dark:text-slate-300">
            Backend-authoritative execution-intent and exchange-order identity
            records. Production disabled.
          </p>
        </div>
        <RefreshButton disabled={isPending} onRefresh={refreshStatus} />
      </header>

      {loading ? (
        <p
          className="rounded-lg border border-slate-200 bg-white p-5 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300"
          aria-live="polite"
        >
          Loading execution intents and exchange orders from backend authority.
        </p>
      ) : null}

      {refreshInProgress ? (
        <p className="text-sm text-slate-600 dark:text-slate-400" aria-live="polite">
          Refreshing execution intents and exchange orders.
        </p>
      ) : null}

      {errorKind ? <OrdersUnavailableState kind={errorKind} /> : null}
      {!loading && !errorKind && data ? (
        <OrdersVisibilityPanel
          executionIntents={data.executionIntents}
          exchangeOrders={data.exchangeOrders}
        />
      ) : null}
    </div>
  );
}

function LiveSafetyUnavailableState({ kind }: { kind: ReadOnlyErrorKind }) {
  const message = {
    forbidden:
      "Live-safety detail is forbidden. The dashboard is failing closed.",
    malformed:
      "Live-safety detail payload is malformed. The dashboard is failing closed.",
    unavailable:
      "Live-safety detail is unavailable. Current safety detail is not inferred.",
  }[kind];

  return (
    <section
      className="rounded-lg border border-rose-300 bg-rose-50 p-5 text-rose-950 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-100"
      aria-live="polite"
    >
      <h2 className="text-lg font-semibold">Live-safety view unavailable</h2>
      <p className="mt-2 text-sm leading-6">{message}</p>
    </section>
  );
}

function LiveSafetyRoute() {
  const [data, setData] = useState<LiveSafetyDetailData | null>(null);
  const [errorKind, setErrorKind] = useState<ReadOnlyErrorKind | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshInProgress, setRefreshInProgress] = useState(false);
  const requestInProgress = useRef(false);
  const abortController = useRef<AbortController | null>(null);

  useEffect(() => {
    if (requestInProgress.current) {
      return undefined;
    }

    requestInProgress.current = true;
    const controller = new AbortController();
    abortController.current = controller;
    let ignoreResult = false;

    void Promise.all([
      readOnlyClient.liveSafetyStatus(controller.signal),
      readOnlyClient.liveReadiness(controller.signal),
      readOnlyClient.persistenceStatus(controller.signal),
      readOnlyClient.killSwitchStatus(controller.signal),
    ])
      .then(([safetyStatus, readiness, persistence, killSwitch]) => {
        if (ignoreResult) {
          return;
        }
        setData({ safetyStatus, readiness, persistence, killSwitch });
        setErrorKind(null);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        if (ignoreResult) {
          return;
        }
        setData(null);
        setErrorKind(errorKindFrom(error));
      })
      .finally(() => {
        if (ignoreResult) {
          return;
        }
        if (abortController.current === controller) {
          abortController.current = null;
        }
        requestInProgress.current = false;
        setLoading(false);
      });

    return () => {
      ignoreResult = true;
      abortController.current?.abort();
    };
  }, []);

  const refreshStatus = useCallback(() => {
    if (requestInProgress.current) {
      return;
    }

    requestInProgress.current = true;
    abortController.current?.abort();

    const controller = new AbortController();
    abortController.current = controller;
    setErrorKind(null);
    setRefreshInProgress(true);

    void Promise.all([
      readOnlyClient.liveSafetyStatus(controller.signal),
      readOnlyClient.liveReadiness(controller.signal),
      readOnlyClient.persistenceStatus(controller.signal),
      readOnlyClient.killSwitchStatus(controller.signal),
    ])
      .then(([safetyStatus, readiness, persistence, killSwitch]) => {
        setData({ safetyStatus, readiness, persistence, killSwitch });
        setErrorKind(null);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setData(null);
        setErrorKind(errorKindFrom(error));
      })
      .finally(() => {
        if (abortController.current === controller) {
          abortController.current = null;
        }
        requestInProgress.current = false;
        setRefreshInProgress(false);
      });
  }, []);

  const isPending = loading || refreshInProgress;

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium uppercase text-slate-500 dark:text-slate-400">
            Read-only live safety
          </p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-950 dark:text-white">
            Live-Safety Detail
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-700 dark:text-slate-300">
            Backend-authoritative safety, readiness, persistence, and
            kill-switch status detail. Production disabled.
          </p>
        </div>
        <RefreshButton disabled={isPending} onRefresh={refreshStatus} />
      </header>

      {loading ? (
        <p
          className="rounded-lg border border-slate-200 bg-white p-5 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300"
          aria-live="polite"
        >
          Loading live-safety detail from backend authority.
        </p>
      ) : null}

      {refreshInProgress ? (
        <p className="text-sm text-slate-600 dark:text-slate-400" aria-live="polite">
          Refreshing live-safety detail.
        </p>
      ) : null}

      {errorKind ? <LiveSafetyUnavailableState kind={errorKind} /> : null}
      {!loading && !errorKind && data ? (
        <LiveSafetyDetailPanel
          safetyStatus={data.safetyStatus}
          readiness={data.readiness}
          persistence={data.persistence}
          killSwitch={data.killSwitch}
        />
      ) : null}
    </div>
  );
}

export default function App() {
  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8 text-slate-950 dark:bg-slate-950 dark:text-slate-50 sm:px-6 lg:px-8">
      <div className="mx-auto w-full max-w-6xl">
        <Routes>
          <Route path="/dashboard" element={<DashboardRoute />} />
          <Route path="/positions" element={<PositionsRoute />} />
          <Route path="/orders" element={<OrdersRoute />} />
          <Route path="/live-safety" element={<LiveSafetyRoute />} />
          <Route path="/recovery" element={<RecoveryRoute />} />
          <Route path="/pair-audit" element={<PairAuditPanel />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </div>
    </main>
  );
}
