import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import App from "./App";
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

const endpoint = "/api/v1/live/operator/status";
const intentsEndpoint = "/api/v1/live/execution-intents";
const exchangeOrdersEndpoint = "/api/v1/live/exchange-orders";
const safetyEndpoint = "/api/v1/live/safety/status";
const readinessEndpoint = "/api/v1/live/readiness";
const persistenceEndpoint = "/api/v1/live/persistence/status";
const killSwitchEndpoint = "/api/v1/live/kill-switch/status";
const recoveryEndpoint = "/api/v1/live/recovery/status";
const positionEndpoint = "/api/v1/live/positions/BTCUSDT";
const protectiveEndpoint = "/api/v1/live/protective-orders/current";
const pairAuditEndpoint =
  "/api/v1/live/protective-pairs/pair-001/events?limit=50&offset=0";
const encodedPairAuditEndpoint =
  "/api/v1/live/protective-pairs/pair%3A001/events?limit=50&offset=0";

function operatorStatus(
  overrides: Partial<OperatorStatusResponse> = {},
): OperatorStatusResponse {
  return {
    environment: "BINANCE_FUTURES_TESTNET",
    symbol: "BTCUSDT",
    overall_status: "BLOCKED",
    kill_switch_state: "RELEASED",
    kill_switch_available: true,
    recovery_required: true,
    recovery_available: true,
    persistence_configured: true,
    persistence_reachable: true,
    persistence_schema_ready: true,
    readiness_status: "WARNING",
    validation_gate: "WARNING",
    active_lock: false,
    warnings: [
      {
        code: "RECOVERY_REQUIRED",
        severity: "BLOCKING",
        message: "Protective recovery is required.",
        source: "recovery",
      },
    ],
    updated_at: "2026-08-14T12:00:00+00:00",
    ...overrides,
  };
}

function position(overrides: Partial<PositionResponse> = {}): PositionResponse {
  return {
    symbol: "BTCUSDT",
    position_side: "BOTH",
    direction: "LONG",
    quantity: "0.010",
    entry_price: "64000.5",
    break_even_price: "64010.5",
    mark_price: "64100.25",
    notional_usdt: "641.0025",
    unrealized_pnl: "1.25",
    liquidation_price: "50000",
    has_open_position: true,
    source: "binance_futures_testnet_read_only",
    updated_at: "2026-08-14T12:00:00+00:00",
    ...overrides,
  };
}

function protectiveOrders(
  overrides: Partial<ProtectiveOrdersCurrentResponse> = {},
): ProtectiveOrdersCurrentResponse {
  return {
    state: "ACTIVE",
    pair_id: "pair-001",
    recovery_required: false,
    blocking_reason: null,
    active_lock: false,
    stop: {
      client_algo_id: "stop-001",
      algo_id: "9001",
      status: "NEW",
      trigger_price: "62000",
    },
    take_profit: {
      client_algo_id: "take-profit-001",
      algo_id: "9002",
      status: "NEW",
      trigger_price: "67000",
    },
    updated_at: "2026-08-14T12:00:01+00:00",
    ...overrides,
  };
}

function executionIntents(
  overrides: Partial<ExecutionIntentListResponse> = {},
): ExecutionIntentListResponse {
  return {
    items: [
      {
        correlation_id: "11111111-1111-4111-8111-111111111111",
        environment: "BINANCE_FUTURES_TESTNET",
        symbol: "BTCUSDT",
        intent_type: "PROTECTIVE_ENTRY",
        state: "ACKNOWLEDGED",
        requested_quantity: "0.010",
        requested_price: "64000",
        failure_code: null,
        version: 3,
        created_at: "2026-08-14T11:59:00+00:00",
        updated_at: "2026-08-14T12:00:00+00:00",
      },
    ],
    limit: 50,
    offset: 0,
    count: 1,
    updated_at: "2026-08-14T12:00:01+00:00",
    ...overrides,
  };
}

function exchangeOrders(
  overrides: Partial<ExchangeOrderIdentityListResponse> = {},
): ExchangeOrderIdentityListResponse {
  return {
    items: [
      {
        leg_type: "STOP",
        client_algo_id: "stop-001",
        exchange_algo_id: "9001",
        exchange_order_id: "8001",
        status: "NEW",
        trigger_price: "62000",
        version: 4,
        created_at: "2026-08-14T11:59:30+00:00",
        updated_at: "2026-08-14T12:00:02+00:00",
        pair_id: "pair-001",
        correlation_id: "11111111-1111-4111-8111-111111111111",
      },
    ],
    limit: 50,
    offset: 0,
    count: 1,
    updated_at: "2026-08-14T12:00:03+00:00",
    ...overrides,
  };
}

function safetyStatus(
  overrides: Partial<LiveSafetyStatusResponse> = {},
): LiveSafetyStatusResponse {
  return {
    environment: "BINANCE_FUTURES_TESTNET",
    live_trading_enabled: false,
    automatic_execution_enabled: false,
    kill_switch_engaged: true,
    credentials_configured: false,
    active_lock: false,
    recovery_required: true,
    production_endpoint_allowed: false,
    updated_at: "2026-08-14T12:00:04+00:00",
    ...overrides,
  };
}

function readiness(
  overrides: Partial<LiveReadinessResponse> = {},
): LiveReadinessResponse {
  return {
    status: "WARNING",
    symbol: "BTCUSDT",
    checks_passed: 9,
    checks_warning: 1,
    checks_failed: 0,
    validation_gate: "PASS",
    blocking_reasons: ["Official BTC validation gate warning."],
    updated_at: "2026-08-14T12:00:05+00:00",
    ...overrides,
  };
}

function persistence(
  overrides: Partial<PersistenceStatusResponse> = {},
): PersistenceStatusResponse {
  return {
    configured: true,
    reachable: true,
    schema_ready: true,
    migration_revision: "rev-001",
    read_only: true,
    source_of_truth: true,
    updated_at: "2026-08-14T12:00:06+00:00",
    ...overrides,
  };
}

function killSwitch(
  overrides: Partial<KillSwitchControlResponse> = {},
): KillSwitchControlResponse {
  return {
    accepted: true,
    environment: "BINANCE_FUTURES_TESTNET",
    symbol: "BTCUSDT",
    state: "ENGAGED",
    changed: false,
    version: 7,
    updated_at: "2026-08-14T12:00:07+00:00",
    blocking_code: null,
    ...overrides,
  };
}

function recoveryStatus(
  overrides: Partial<RecoveryStatusResponse> = {},
): RecoveryStatusResponse {
  return {
    required: true,
    reason: "PROTECTIVE_RECOVERY_REQUIRED",
    pair_id: "pair-001",
    phase: "RECOVERY_REQUIRED",
    active_lock: true,
    updated_at: "2026-08-14T12:00:08+00:00",
    ...overrides,
  };
}

function pairAuditResponse(overrides: Record<string, unknown> = {}) {
  return {
    pair_id: "pair-001",
    events: [
      {
        event_kind: "RECOVERY_EVENT",
        correlation_id: "11111111-1111-4111-8111-111111111111",
        event_type: "PAIR_RECOVERY_STARTED",
        action: null,
        from_state: "ACTIVE",
        to_state: "RECOVERY_REQUIRED",
        reason_code: "EXCHANGE_ORDER_MISSING",
        result: "RECORDED",
        error_code: null,
        created_at: "2026-08-14T12:01:00+00:00",
      },
      {
        event_kind: "AUDIT_EVENT",
        correlation_id: null,
        event_type: null,
        action: "PAIR_RECOVERY_VIEWED",
        from_state: null,
        to_state: null,
        reason_code: null,
        result: "SUCCESS",
        error_code: "NOT_APPLICABLE",
        created_at: "2026-08-14T12:02:00+00:00",
      },
    ],
    limit: 50,
    offset: 0,
    ...overrides,
  };
}

function jsonResponse(payload: unknown, init: ResponseInit = {}) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      headers: { "Content-Type": "application/json" },
      status: 200,
      ...init,
    }),
  );
}

function deferredResponse() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((innerResolve) => {
    resolve = innerResolve;
  });
  return { promise, resolve };
}

function mockFetch(
  implementation: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>,
) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(implementation as typeof fetch);
}

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <App />
    </MemoryRouter>,
  );
}

function renderPositions() {
  return render(
    <MemoryRouter initialEntries={["/positions"]}>
      <App />
    </MemoryRouter>,
  );
}

function renderOrders() {
  return render(
    <MemoryRouter initialEntries={["/orders"]}>
      <App />
    </MemoryRouter>,
  );
}

function renderLiveSafety() {
  return render(
    <MemoryRouter initialEntries={["/live-safety"]}>
      <App />
    </MemoryRouter>,
  );
}

function renderRecovery() {
  return render(
    <MemoryRouter initialEntries={["/recovery"]}>
      <App />
    </MemoryRouter>,
  );
}

function renderPairAudit() {
  return render(
    <MemoryRouter initialEntries={["/pair-audit"]}>
      <App />
    </MemoryRouter>,
  );
}

function mockPairAuditFetch({
  payload = pairAuditResponse(),
  init,
  reject = false,
}: {
  payload?: unknown;
  init?: ResponseInit;
  reject?: boolean;
} = {}) {
  return mockFetch((input) => {
    const url = String(input);
    if (url === pairAuditEndpoint || url === encodedPairAuditEndpoint) {
      if (reject) {
        return Promise.reject(new TypeError("pair audit unavailable"));
      }
      return jsonResponse(payload, init);
    }
    return jsonResponse(operatorStatus());
  });
}

function mockRecoveryFetch({
  payload = recoveryStatus(),
  init,
  reject = false,
}: {
  payload?: unknown;
  init?: ResponseInit;
  reject?: boolean;
} = {}) {
  return mockFetch((input) => {
    const url = String(input);
    if (url === recoveryEndpoint) {
      if (reject) {
        return Promise.reject(new TypeError("recovery unavailable"));
      }
      return jsonResponse(payload, init);
    }
    return jsonResponse(operatorStatus());
  });
}

function mockPositionProtectionFetch({
  positionPayload = position(),
  protectivePayload = protectiveOrders(),
  positionInit,
  protectiveInit,
  rejectPosition = false,
  rejectProtective = false,
}: {
  positionPayload?: unknown;
  protectivePayload?: unknown;
  positionInit?: ResponseInit;
  protectiveInit?: ResponseInit;
  rejectPosition?: boolean;
  rejectProtective?: boolean;
} = {}) {
  return mockFetch((input) => {
    const url = String(input);
    if (url === positionEndpoint) {
      if (rejectPosition) {
        return Promise.reject(new TypeError("position unavailable"));
      }
      return jsonResponse(positionPayload, positionInit);
    }
    if (url === protectiveEndpoint) {
      if (rejectProtective) {
        return Promise.reject(new TypeError("protective unavailable"));
      }
      return jsonResponse(protectivePayload, protectiveInit);
    }
    return jsonResponse(operatorStatus());
  });
}

function mockOrdersFetch({
  intentsPayload = executionIntents(),
  exchangeOrdersPayload = exchangeOrders(),
  intentsInit,
  exchangeOrdersInit,
  rejectIntents = false,
  rejectExchangeOrders = false,
}: {
  intentsPayload?: unknown;
  exchangeOrdersPayload?: unknown;
  intentsInit?: ResponseInit;
  exchangeOrdersInit?: ResponseInit;
  rejectIntents?: boolean;
  rejectExchangeOrders?: boolean;
} = {}) {
  return mockFetch((input) => {
    const url = String(input);
    if (url === intentsEndpoint) {
      if (rejectIntents) {
        return Promise.reject(new TypeError("intents unavailable"));
      }
      return jsonResponse(intentsPayload, intentsInit);
    }
    if (url === exchangeOrdersEndpoint) {
      if (rejectExchangeOrders) {
        return Promise.reject(new TypeError("exchange orders unavailable"));
      }
      return jsonResponse(exchangeOrdersPayload, exchangeOrdersInit);
    }
    return jsonResponse(operatorStatus());
  });
}

function mockLiveSafetyFetch({
  safetyPayload = safetyStatus(),
  readinessPayload = readiness(),
  persistencePayload = persistence(),
  killSwitchPayload = killSwitch(),
  safetyInit,
  readinessInit,
  persistenceInit,
  killSwitchInit,
  rejectSafety = false,
  rejectReadiness = false,
  rejectPersistence = false,
  rejectKillSwitch = false,
}: {
  safetyPayload?: unknown;
  readinessPayload?: unknown;
  persistencePayload?: unknown;
  killSwitchPayload?: unknown;
  safetyInit?: ResponseInit;
  readinessInit?: ResponseInit;
  persistenceInit?: ResponseInit;
  killSwitchInit?: ResponseInit;
  rejectSafety?: boolean;
  rejectReadiness?: boolean;
  rejectPersistence?: boolean;
  rejectKillSwitch?: boolean;
} = {}) {
  return mockFetch((input) => {
    const url = String(input);
    if (url === safetyEndpoint) {
      if (rejectSafety) {
        return Promise.reject(new TypeError("safety unavailable"));
      }
      return jsonResponse(safetyPayload, safetyInit);
    }
    if (url === readinessEndpoint) {
      if (rejectReadiness) {
        return Promise.reject(new TypeError("readiness unavailable"));
      }
      return jsonResponse(readinessPayload, readinessInit);
    }
    if (url === persistenceEndpoint) {
      if (rejectPersistence) {
        return Promise.reject(new TypeError("persistence unavailable"));
      }
      return jsonResponse(persistencePayload, persistenceInit);
    }
    if (url === killSwitchEndpoint) {
      if (rejectKillSwitch) {
        return Promise.reject(new TypeError("kill switch unavailable"));
      }
      return jsonResponse(killSwitchPayload, killSwitchInit);
    }
    return jsonResponse(operatorStatus());
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

test("shows the initial loading state while the first operator-status GET is pending", () => {
  mockFetch(() => deferredResponse().promise);

  renderDashboard();

  expect(
    screen.getByText("Loading operator status from backend authority."),
  ).toBeInTheDocument();
});

test("renders successful operator status with context, warnings, and no mutation control", async () => {
  mockFetch(() => jsonResponse(operatorStatus()));

  renderDashboard();

  expect(
    await screen.findByRole("heading", {
      level: 1,
      name: "Operator Overview",
    }),
  ).toBeInTheDocument();
  expect(screen.getByText("BINANCE_FUTURES_TESTNET")).toBeInTheDocument();
  expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
  expect(screen.getByText(/Production disabled/i)).toBeInTheDocument();
  expect(screen.getByText("Protective recovery is required.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Refresh status" })).toBeInTheDocument();
  expect(screen.getAllByRole("button")).toHaveLength(1);
});

test("renders a neutral empty warning state when backend warnings are empty", async () => {
  mockFetch(() => jsonResponse(operatorStatus({ warnings: [] })));

  renderDashboard();

  expect(await screen.findByText("No backend warnings reported.")).toBeInTheDocument();
});

test("transport unavailable fails closed and does not show an available status presentation", async () => {
  mockFetch(() => Promise.reject(new TypeError("network unavailable")));

  renderDashboard();

  expect(await screen.findByText("Backend authority unavailable")).toBeInTheDocument();
  expect(screen.getByText(/cannot infer current safety state/i)).toBeInTheDocument();
  expect(screen.queryByText(/Overall:/i)).not.toBeInTheDocument();
});

test("HTTP 403 renders the forbidden state", async () => {
  mockFetch(() => jsonResponse({ detail: "forbidden" }, { status: 403 }));

  renderDashboard();

  expect(await screen.findByText(/Operator status is forbidden/i)).toBeInTheDocument();
});

test("malformed JSON fails closed", async () => {
  mockFetch(() =>
    Promise.resolve(
      new Response("{", {
        headers: { "Content-Type": "application/json" },
        status: 200,
      }),
    ),
  );

  renderDashboard();

  expect(await screen.findByText(/payload is malformed/i)).toBeInTheDocument();
});

test("malformed schema fails closed", async () => {
  mockFetch(() =>
    jsonResponse({
      ...operatorStatus(),
      recovery_required: "false",
    }),
  );

  renderDashboard();

  expect(await screen.findByText(/payload is malformed/i)).toBeInTheDocument();
});

test("manual refresh performs exactly one additional GET", async () => {
  const fetchSpy = mockFetch(() => jsonResponse(operatorStatus({ warnings: [] })));
  const user = userEvent.setup();

  renderDashboard();
  await screen.findByText("No backend warnings reported.");

  await user.click(screen.getByRole("button", { name: "Refresh status" }));

  await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
});

test("the dashboard performs no automatic retry after an unavailable response", async () => {
  const fetchSpy = mockFetch(() => Promise.reject(new TypeError("offline")));

  renderDashboard();

  expect(await screen.findByText(/Operator status is unavailable/i)).toBeInTheDocument();
  await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
});

test("duplicate concurrent refresh activation is prevented", async () => {
  const refresh = deferredResponse();
  let requestNumber = 0;
  const fetchSpy = mockFetch(() => {
    requestNumber += 1;
    if (requestNumber === 1) {
      return jsonResponse(operatorStatus());
    }
    if (requestNumber === 2) {
      return refresh.promise;
    }
    return refresh.promise;
  });
  const user = userEvent.setup();

  renderDashboard();
  await screen.findByText("Protective recovery is required.");

  const button = screen.getByRole("button", { name: "Refresh status" });
  await user.dblClick(button);

  expect(screen.getByRole("button", { name: "Refresh in progress" })).toBeDisabled();
  expect(fetchSpy).toHaveBeenCalledTimes(2);

  refresh.resolve(
    new Response(JSON.stringify(operatorStatus({ warnings: [] })), {
      headers: { "Content-Type": "application/json" },
      status: 200,
    }),
  );
  expect(await screen.findByText("No backend warnings reported.")).toBeInTheDocument();
});

test("operator-status request uses the exact GET endpoint and JSON accept header", async () => {
  const fetchSpy = mockFetch(() => jsonResponse(operatorStatus()));

  renderDashboard();
  await screen.findByText("Protective recovery is required.");

  expect(fetchSpy).toHaveBeenCalledWith(
    endpoint,
    expect.objectContaining({
      method: "GET",
      headers: { Accept: "application/json" },
    }),
  );
  expect(fetchSpy.mock.calls[0][1]).not.toHaveProperty("body");
  expect(Object.keys(fetchSpy.mock.calls[0][1] ?? {})).toEqual([
    "method",
    "headers",
    "signal",
  ]);
});

test("positions route shows loading while the paired read-only requests are pending", () => {
  mockFetch(() => deferredResponse().promise);

  renderPositions();

  expect(
    screen.getByText(
      "Loading BTCUSDT position and protective-order state from backend authority.",
    ),
  ).toBeInTheDocument();
});

test("positions route performs one initial GET to each exact endpoint", async () => {
  const fetchSpy = mockPositionProtectionFetch();

  renderPositions();
  await screen.findByText("BTCUSDT Position");

  expect(fetchSpy).toHaveBeenCalledTimes(2);
  expect(fetchSpy).toHaveBeenCalledWith(
    positionEndpoint,
    expect.objectContaining({
      method: "GET",
      headers: { Accept: "application/json" },
    }),
  );
  expect(fetchSpy).toHaveBeenCalledWith(
    protectiveEndpoint,
    expect.objectContaining({
      method: "GET",
      headers: { Accept: "application/json" },
    }),
  );
});

test("positions route renders position and protective-order values", async () => {
  mockPositionProtectionFetch();

  renderPositions();

  expect(await screen.findByText("BTCUSDT Position")).toBeInTheDocument();
  expect(screen.getByText("Open position reported")).toBeInTheDocument();
  expect(screen.getByText("0.010")).toBeInTheDocument();
  expect(screen.getByText("64000.5")).toBeInTheDocument();
  expect(screen.getByText("Current Protective Orders")).toBeInTheDocument();
  expect(screen.getByText("State: ACTIVE")).toBeInTheDocument();
  expect(screen.getByText("stop-001")).toBeInTheDocument();
  expect(screen.getByText("take-profit-001")).toBeInTheDocument();
  expect(screen.getAllByRole("button")).toHaveLength(1);
});

test("positions route renders valid no-position and no-protection states", async () => {
  mockPositionProtectionFetch({
    positionPayload: position({
      has_open_position: false,
      position_side: null,
      direction: null,
    }),
    protectivePayload: protectiveOrders({
      state: "NONE",
      pair_id: null,
      recovery_required: false,
      blocking_reason: null,
      stop: null,
      take_profit: null,
    }),
  });

  renderPositions();

  expect(
    await screen.findByText("Backend reports no open BTCUSDT position."),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Backend reports no current protective-order lifecycle."),
  ).toBeInTheDocument();
});

test("positions route fails closed when position is forbidden", async () => {
  mockPositionProtectionFetch({
    positionPayload: { detail: "forbidden" },
    positionInit: { status: 403 },
  });

  renderPositions();

  expect(await screen.findByText("Position view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/forbidden/i)).toBeInTheDocument();
  expect(screen.queryByText("Open position reported")).not.toBeInTheDocument();
});

test("positions route fails closed when protective orders are forbidden", async () => {
  mockPositionProtectionFetch({
    protectivePayload: { detail: "forbidden" },
    protectiveInit: { status: 403 },
  });

  renderPositions();

  expect(await screen.findByText("Position view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/forbidden/i)).toBeInTheDocument();
  expect(screen.queryByText("State: ACTIVE")).not.toBeInTheDocument();
});

test("positions route fails closed when position transport is unavailable", async () => {
  mockPositionProtectionFetch({ rejectPosition: true });

  renderPositions();

  expect(await screen.findByText("Position view unavailable")).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Position view unavailable" }),
  ).toBeInTheDocument();
});

test("positions route fails closed when protective transport is unavailable", async () => {
  mockPositionProtectionFetch({ rejectProtective: true });

  renderPositions();

  expect(await screen.findByText("Position view unavailable")).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Position view unavailable" }),
  ).toBeInTheDocument();
});

test("positions route fails closed for malformed position payload", async () => {
  mockPositionProtectionFetch({
    positionPayload: { ...position(), has_open_position: "false" },
  });

  renderPositions();

  expect(await screen.findByText("Position view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/malformed/i)).toBeInTheDocument();
});

test("positions route fails closed for malformed protective payload", async () => {
  mockPositionProtectionFetch({
    protectivePayload: { ...protectiveOrders(), stop: { client_algo_id: 123 } },
  });

  renderPositions();

  expect(await screen.findByText("Position view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/malformed/i)).toBeInTheDocument();
});

test("positions route manual refresh issues one additional paired GET set", async () => {
  const fetchSpy = mockPositionProtectionFetch();
  const user = userEvent.setup();

  renderPositions();
  await screen.findByText("BTCUSDT Position");

  await user.click(screen.getByRole("button", { name: "Refresh status" }));

  await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(4));
  expect(
    fetchSpy.mock.calls.filter(([input]) => String(input) === positionEndpoint),
  ).toHaveLength(2);
  expect(
    fetchSpy.mock.calls.filter(([input]) => String(input) === protectiveEndpoint),
  ).toHaveLength(2);
});

test("positions route prevents duplicate concurrent refresh request sets", async () => {
  const positionRefresh = deferredResponse();
  const protectiveRefresh = deferredResponse();
  let positionCalls = 0;
  let protectiveCalls = 0;
  const fetchSpy = mockFetch((input) => {
    const url = String(input);
    if (url === positionEndpoint) {
      positionCalls += 1;
      return positionCalls === 1
        ? jsonResponse(position())
        : positionRefresh.promise;
    }
    if (url === protectiveEndpoint) {
      protectiveCalls += 1;
      return protectiveCalls === 1
        ? jsonResponse(protectiveOrders())
        : protectiveRefresh.promise;
    }
    return jsonResponse(operatorStatus());
  });
  const user = userEvent.setup();

  renderPositions();
  await screen.findByText("BTCUSDT Position");

  await user.dblClick(screen.getByRole("button", { name: "Refresh status" }));

  expect(screen.getByRole("button", { name: "Refresh in progress" })).toBeDisabled();
  expect(fetchSpy).toHaveBeenCalledTimes(4);
  expect(positionCalls).toBe(2);
  expect(protectiveCalls).toBe(2);

  positionRefresh.resolve(
    new Response(JSON.stringify(position({ quantity: "0.020" })), {
      headers: { "Content-Type": "application/json" },
      status: 200,
    }),
  );
  protectiveRefresh.resolve(
    new Response(JSON.stringify(protectiveOrders()), {
      headers: { "Content-Type": "application/json" },
      status: 200,
    }),
  );
  expect(await screen.findByText("0.020")).toBeInTheDocument();
});

test("positions route performs no automatic retry after a paired request failure", async () => {
  const fetchSpy = mockPositionProtectionFetch({ rejectPosition: true });

  renderPositions();

  expect(await screen.findByText("Position view unavailable")).toBeInTheDocument();
  await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
});

test("orders route shows loading while the paired read-only requests are pending", () => {
  mockFetch(() => deferredResponse().promise);

  renderOrders();

  expect(
    screen.getByText(
      "Loading execution intents and exchange orders from backend authority.",
    ),
  ).toBeInTheDocument();
});

test("orders route performs one initial GET to each exact endpoint", async () => {
  const fetchSpy = mockOrdersFetch();

  renderOrders();
  await screen.findByText("Execution Intents");

  expect(fetchSpy).toHaveBeenCalledTimes(2);
  expect(fetchSpy).toHaveBeenCalledWith(
    intentsEndpoint,
    expect.objectContaining({
      method: "GET",
      headers: { Accept: "application/json" },
    }),
  );
  expect(fetchSpy).toHaveBeenCalledWith(
    exchangeOrdersEndpoint,
    expect.objectContaining({
      method: "GET",
      headers: { Accept: "application/json" },
    }),
  );
});

test("orders route renders execution-intent and exchange-order values", async () => {
  mockOrdersFetch();

  renderOrders();

  expect(await screen.findByText("Execution Intents")).toBeInTheDocument();
  expect(screen.getByText("PROTECTIVE_ENTRY")).toBeInTheDocument();
  expect(screen.getByText("State: ACKNOWLEDGED")).toBeInTheDocument();
  expect(screen.getByText("0.010")).toBeInTheDocument();
  expect(screen.getByText("Exchange Order Identities")).toBeInTheDocument();
  expect(screen.getByText("Status: NEW")).toBeInTheDocument();
  expect(screen.getByText("stop-001")).toBeInTheDocument();
  expect(screen.getByText("8001")).toBeInTheDocument();
  expect(screen.getAllByRole("button")).toHaveLength(1);
});

test("orders route renders valid empty intent and exchange-order states", async () => {
  mockOrdersFetch({
    intentsPayload: executionIntents({ items: [], count: 0 }),
    exchangeOrdersPayload: exchangeOrders({ items: [], count: 0 }),
  });

  renderOrders();

  expect(
    await screen.findByText("Backend reports no recent execution intents."),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Backend reports no recent exchange-order identities."),
  ).toBeInTheDocument();
});

test("orders route fails closed when execution intents are forbidden", async () => {
  mockOrdersFetch({
    intentsPayload: { detail: "forbidden" },
    intentsInit: { status: 403 },
  });

  renderOrders();

  expect(await screen.findByText("Orders view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/forbidden/i)).toBeInTheDocument();
  expect(screen.queryByText("PROTECTIVE_ENTRY")).not.toBeInTheDocument();
});

test("orders route fails closed when exchange orders are forbidden", async () => {
  mockOrdersFetch({
    exchangeOrdersPayload: { detail: "forbidden" },
    exchangeOrdersInit: { status: 403 },
  });

  renderOrders();

  expect(await screen.findByText("Orders view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/forbidden/i)).toBeInTheDocument();
  expect(screen.queryByText("Status: NEW")).not.toBeInTheDocument();
});

test("orders route fails closed when execution-intent transport is unavailable", async () => {
  mockOrdersFetch({ rejectIntents: true });

  renderOrders();

  expect(await screen.findByText("Orders view unavailable")).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Orders view unavailable" }),
  ).toBeInTheDocument();
});

test("orders route fails closed when exchange-order transport is unavailable", async () => {
  mockOrdersFetch({ rejectExchangeOrders: true });

  renderOrders();

  expect(await screen.findByText("Orders view unavailable")).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Orders view unavailable" }),
  ).toBeInTheDocument();
});

test("orders route fails closed for malformed execution-intent payload", async () => {
  mockOrdersFetch({
    intentsPayload: { ...executionIntents(), count: "1" },
  });

  renderOrders();

  expect(await screen.findByText("Orders view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/malformed/i)).toBeInTheDocument();
});

test("orders route fails closed for malformed exchange-order payload", async () => {
  mockOrdersFetch({
    exchangeOrdersPayload: {
      ...exchangeOrders(),
      items: [{ ...exchangeOrders().items[0], version: "4" }],
    },
  });

  renderOrders();

  expect(await screen.findByText("Orders view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/malformed/i)).toBeInTheDocument();
});

test("orders route manual refresh issues one additional paired GET set", async () => {
  const fetchSpy = mockOrdersFetch();
  const user = userEvent.setup();

  renderOrders();
  await screen.findByText("Execution Intents");

  await user.click(screen.getByRole("button", { name: "Refresh status" }));

  await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(4));
  expect(
    fetchSpy.mock.calls.filter(([input]) => String(input) === intentsEndpoint),
  ).toHaveLength(2);
  expect(
    fetchSpy.mock.calls.filter(
      ([input]) => String(input) === exchangeOrdersEndpoint,
    ),
  ).toHaveLength(2);
});

test("orders route prevents duplicate concurrent refresh request sets", async () => {
  const intentsRefresh = deferredResponse();
  const exchangeOrdersRefresh = deferredResponse();
  let intentsCalls = 0;
  let exchangeOrderCalls = 0;
  const fetchSpy = mockFetch((input) => {
    const url = String(input);
    if (url === intentsEndpoint) {
      intentsCalls += 1;
      return intentsCalls === 1
        ? jsonResponse(executionIntents())
        : intentsRefresh.promise;
    }
    if (url === exchangeOrdersEndpoint) {
      exchangeOrderCalls += 1;
      return exchangeOrderCalls === 1
        ? jsonResponse(exchangeOrders())
        : exchangeOrdersRefresh.promise;
    }
    return jsonResponse(operatorStatus());
  });
  const user = userEvent.setup();

  renderOrders();
  await screen.findByText("Execution Intents");

  await user.dblClick(screen.getByRole("button", { name: "Refresh status" }));

  expect(screen.getByRole("button", { name: "Refresh in progress" })).toBeDisabled();
  expect(fetchSpy).toHaveBeenCalledTimes(4);
  expect(intentsCalls).toBe(2);
  expect(exchangeOrderCalls).toBe(2);

  intentsRefresh.resolve(
    new Response(
      JSON.stringify(
        executionIntents({
          items: [
            {
              ...executionIntents().items[0],
              intent_type: "ORDER_REVIEW",
            },
          ],
        }),
      ),
      {
        headers: { "Content-Type": "application/json" },
        status: 200,
      },
    ),
  );
  exchangeOrdersRefresh.resolve(
    new Response(JSON.stringify(exchangeOrders()), {
      headers: { "Content-Type": "application/json" },
      status: 200,
    }),
  );
  expect(await screen.findByText("ORDER_REVIEW")).toBeInTheDocument();
});

test("orders route performs no automatic retry after a paired request failure", async () => {
  const fetchSpy = mockOrdersFetch({ rejectIntents: true });

  renderOrders();

  expect(await screen.findByText("Orders view unavailable")).toBeInTheDocument();
  await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
});

test("live-safety route shows loading while four read-only requests are pending", () => {
  mockFetch(() => deferredResponse().promise);

  renderLiveSafety();

  expect(
    screen.getByText("Loading live-safety detail from backend authority."),
  ).toBeInTheDocument();
});

test("live-safety route performs one initial GET to each exact endpoint", async () => {
  const fetchSpy = mockLiveSafetyFetch();

  renderLiveSafety();
  await screen.findByText("Safety Status");

  expect(fetchSpy).toHaveBeenCalledTimes(4);
  for (const endpointUrl of [
    safetyEndpoint,
    readinessEndpoint,
    persistenceEndpoint,
    killSwitchEndpoint,
  ]) {
    expect(fetchSpy).toHaveBeenCalledWith(
      endpointUrl,
      expect.objectContaining({
        method: "GET",
        headers: { Accept: "application/json" },
      }),
    );
  }
});

test("live-safety route renders safety, readiness, persistence, and kill-switch values", async () => {
  mockLiveSafetyFetch();

  renderLiveSafety();

  expect(await screen.findByText("Safety Status")).toBeInTheDocument();
  expect(screen.getAllByText("BINANCE_FUTURES_TESTNET")).toHaveLength(2);
  expect(screen.getByText("Live trading enabled")).toBeInTheDocument();
  expect(screen.getByText("Recovery required")).toBeInTheDocument();
  expect(screen.getByText("Readiness")).toBeInTheDocument();
  expect(screen.getByText("Status: WARNING")).toBeInTheDocument();
  expect(screen.getByText("Official BTC validation gate warning.")).toBeInTheDocument();
  expect(screen.getByText("Persistence")).toBeInTheDocument();
  expect(screen.getByText("rev-001")).toBeInTheDocument();
  expect(screen.getByText("Kill Switch Status")).toBeInTheDocument();
  expect(screen.getByText("State: ENGAGED")).toBeInTheDocument();
  expect(screen.getByText("Version")).toBeInTheDocument();
  expect(screen.getAllByRole("button")).toHaveLength(1);
  expect(
    screen.queryByRole("button", { name: /engage|release|reset|toggle/i }),
  ).not.toBeInTheDocument();
});

test("live-safety route renders empty blocking and nullable field states", async () => {
  mockLiveSafetyFetch({
    readinessPayload: readiness({ blocking_reasons: [] }),
    persistencePayload: persistence({ migration_revision: null }),
    killSwitchPayload: killSwitch({
      state: null,
      version: null,
      updated_at: null,
      blocking_code: null,
    }),
  });

  renderLiveSafety();

  expect(
    await screen.findByText("Backend reports no readiness blocking reasons."),
  ).toBeInTheDocument();
  expect(screen.getByText("Backend reports no migration revision.")).toBeInTheDocument();
  expect(
    screen.getByText(
      "Backend reports one or more nullable kill-switch fields as not reported.",
    ),
  ).toBeInTheDocument();
});

test("live-safety route fails closed when safety status is forbidden", async () => {
  mockLiveSafetyFetch({
    safetyPayload: { detail: "forbidden" },
    safetyInit: { status: 403 },
  });

  renderLiveSafety();

  expect(await screen.findByText("Live-safety view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/forbidden/i)).toBeInTheDocument();
  expect(screen.queryByText("Safety Status")).not.toBeInTheDocument();
});

test("live-safety route fails closed when readiness is forbidden", async () => {
  mockLiveSafetyFetch({
    readinessPayload: { detail: "forbidden" },
    readinessInit: { status: 403 },
  });

  renderLiveSafety();

  expect(await screen.findByText("Live-safety view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/forbidden/i)).toBeInTheDocument();
});

test("live-safety route fails closed when persistence is forbidden", async () => {
  mockLiveSafetyFetch({
    persistencePayload: { detail: "forbidden" },
    persistenceInit: { status: 403 },
  });

  renderLiveSafety();

  expect(await screen.findByText("Live-safety view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/forbidden/i)).toBeInTheDocument();
});

test("live-safety route fails closed when kill-switch status is forbidden", async () => {
  mockLiveSafetyFetch({
    killSwitchPayload: { detail: "forbidden" },
    killSwitchInit: { status: 403 },
  });

  renderLiveSafety();

  expect(await screen.findByText("Live-safety view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/forbidden/i)).toBeInTheDocument();
});

test("live-safety route fails closed when safety transport is unavailable", async () => {
  mockLiveSafetyFetch({ rejectSafety: true });

  renderLiveSafety();

  expect(await screen.findByText("Live-safety view unavailable")).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Live-safety view unavailable" }),
  ).toBeInTheDocument();
});

test("live-safety route fails closed when readiness transport is unavailable", async () => {
  mockLiveSafetyFetch({ rejectReadiness: true });

  renderLiveSafety();

  expect(await screen.findByText("Live-safety view unavailable")).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Live-safety view unavailable" }),
  ).toBeInTheDocument();
});

test("live-safety route fails closed when persistence transport is unavailable", async () => {
  mockLiveSafetyFetch({ rejectPersistence: true });

  renderLiveSafety();

  expect(await screen.findByText("Live-safety view unavailable")).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Live-safety view unavailable" }),
  ).toBeInTheDocument();
});

test("live-safety route fails closed when kill-switch transport is unavailable", async () => {
  mockLiveSafetyFetch({ rejectKillSwitch: true });

  renderLiveSafety();

  expect(await screen.findByText("Live-safety view unavailable")).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Live-safety view unavailable" }),
  ).toBeInTheDocument();
});

test("live-safety route fails closed for malformed safety payload", async () => {
  mockLiveSafetyFetch({
    safetyPayload: { ...safetyStatus(), live_trading_enabled: "false" },
  });

  renderLiveSafety();

  expect(await screen.findByText("Live-safety view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/malformed/i)).toBeInTheDocument();
});

test("live-safety route fails closed for malformed readiness payload", async () => {
  mockLiveSafetyFetch({
    readinessPayload: { ...readiness(), blocking_reasons: ["ok", 12] },
  });

  renderLiveSafety();

  expect(await screen.findByText("Live-safety view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/malformed/i)).toBeInTheDocument();
});

test("live-safety route fails closed for malformed persistence payload", async () => {
  mockLiveSafetyFetch({
    persistencePayload: { ...persistence(), migration_revision: 123 },
  });

  renderLiveSafety();

  expect(await screen.findByText("Live-safety view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/malformed/i)).toBeInTheDocument();
});

test("live-safety route fails closed for malformed kill-switch payload", async () => {
  mockLiveSafetyFetch({
    killSwitchPayload: { ...killSwitch(), version: "7" },
  });

  renderLiveSafety();

  expect(await screen.findByText("Live-safety view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/malformed/i)).toBeInTheDocument();
});

test("live-safety route manual refresh issues one additional four-request set", async () => {
  const fetchSpy = mockLiveSafetyFetch();
  const user = userEvent.setup();

  renderLiveSafety();
  await screen.findByText("Safety Status");

  await user.click(screen.getByRole("button", { name: "Refresh status" }));

  await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(8));
  for (const endpointUrl of [
    safetyEndpoint,
    readinessEndpoint,
    persistenceEndpoint,
    killSwitchEndpoint,
  ]) {
    expect(
      fetchSpy.mock.calls.filter(([input]) => String(input) === endpointUrl),
    ).toHaveLength(2);
  }
});

test("live-safety route prevents duplicate concurrent refresh request sets", async () => {
  const safetyRefresh = deferredResponse();
  const readinessRefresh = deferredResponse();
  const persistenceRefresh = deferredResponse();
  const killSwitchRefresh = deferredResponse();
  let safetyCalls = 0;
  let readinessCalls = 0;
  let persistenceCalls = 0;
  let killSwitchCalls = 0;
  const fetchSpy = mockFetch((input) => {
    const url = String(input);
    if (url === safetyEndpoint) {
      safetyCalls += 1;
      return safetyCalls === 1 ? jsonResponse(safetyStatus()) : safetyRefresh.promise;
    }
    if (url === readinessEndpoint) {
      readinessCalls += 1;
      return readinessCalls === 1 ? jsonResponse(readiness()) : readinessRefresh.promise;
    }
    if (url === persistenceEndpoint) {
      persistenceCalls += 1;
      return persistenceCalls === 1
        ? jsonResponse(persistence())
        : persistenceRefresh.promise;
    }
    if (url === killSwitchEndpoint) {
      killSwitchCalls += 1;
      return killSwitchCalls === 1
        ? jsonResponse(killSwitch())
        : killSwitchRefresh.promise;
    }
    return jsonResponse(operatorStatus());
  });
  const user = userEvent.setup();

  renderLiveSafety();
  await screen.findByText("Safety Status");

  await user.dblClick(screen.getByRole("button", { name: "Refresh status" }));

  expect(screen.getByRole("button", { name: "Refresh in progress" })).toBeDisabled();
  expect(fetchSpy).toHaveBeenCalledTimes(8);
  expect(safetyCalls).toBe(2);
  expect(readinessCalls).toBe(2);
  expect(persistenceCalls).toBe(2);
  expect(killSwitchCalls).toBe(2);

  safetyRefresh.resolve(
    new Response(
      JSON.stringify(safetyStatus({ environment: "BINANCE_FUTURES_TESTNET" })),
      {
        headers: { "Content-Type": "application/json" },
        status: 200,
      },
    ),
  );
  readinessRefresh.resolve(
    new Response(JSON.stringify(readiness({ checks_failed: 2 })), {
      headers: { "Content-Type": "application/json" },
      status: 200,
    }),
  );
  persistenceRefresh.resolve(
    new Response(JSON.stringify(persistence()), {
      headers: { "Content-Type": "application/json" },
      status: 200,
    }),
  );
  killSwitchRefresh.resolve(
    new Response(JSON.stringify(killSwitch()), {
      headers: { "Content-Type": "application/json" },
      status: 200,
    }),
  );
  expect(await screen.findByText("Checks failed")).toBeInTheDocument();
  expect(screen.getByText("2")).toBeInTheDocument();
});

test("live-safety route performs no automatic retry after a four-request failure", async () => {
  const fetchSpy = mockLiveSafetyFetch({ rejectSafety: true });

  renderLiveSafety();

  expect(await screen.findByText("Live-safety view unavailable")).toBeInTheDocument();
  await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(4));
});

test("recovery route shows loading while the read-only request is pending", () => {
  mockFetch(() => deferredResponse().promise);

  renderRecovery();

  expect(
    screen.getByText("Loading recovery status from backend authority."),
  ).toBeInTheDocument();
});

test("recovery route performs one initial GET to the exact endpoint", async () => {
  const fetchSpy = mockRecoveryFetch();

  renderRecovery();
  await screen.findByText("Recovery Status");

  expect(fetchSpy).toHaveBeenCalledTimes(1);
  expect(fetchSpy).toHaveBeenCalledWith(
    recoveryEndpoint,
    expect.objectContaining({
      method: "GET",
      headers: { Accept: "application/json" },
    }),
  );
});

test("recovery route renders required recovery detail", async () => {
  mockRecoveryFetch();

  renderRecovery();

  expect(await screen.findByText("Recovery Status")).toBeInTheDocument();
  expect(screen.getAllByText("Recovery required")).toHaveLength(2);
  expect(screen.getByText("PROTECTIVE_RECOVERY_REQUIRED")).toBeInTheDocument();
  expect(screen.getByText("pair-001")).toBeInTheDocument();
  expect(screen.getByText("RECOVERY_REQUIRED")).toBeInTheDocument();
  expect(screen.getByText("Active lock")).toBeInTheDocument();
  expect(screen.getAllByText("Yes")).toHaveLength(2);
  expect(screen.getByText("2026-08-14T12:00:08+00:00")).toBeInTheDocument();
});

test("recovery route renders valid no-recovery and nullable field states", async () => {
  mockRecoveryFetch({
    payload: recoveryStatus({
      required: false,
      reason: null,
      pair_id: null,
      phase: null,
      active_lock: false,
    }),
  });

  renderRecovery();

  expect(
    await screen.findByText("Backend reports no recovery requirement."),
  ).toBeInTheDocument();
  expect(screen.getByText("No recovery required")).toBeInTheDocument();
  expect(screen.getAllByText("Backend did not provide this value.")).toHaveLength(3);
  expect(screen.getAllByText("No")).toHaveLength(2);
});

test("recovery route fails closed on 403", async () => {
  mockRecoveryFetch({
    payload: { detail: "forbidden" },
    init: { status: 403 },
  });

  renderRecovery();

  expect(await screen.findByText("Recovery view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/forbidden/i)).toBeInTheDocument();
  expect(screen.queryByText("Recovery Status")).not.toBeInTheDocument();
});

test("recovery route fails closed on unavailable transport", async () => {
  const fetchSpy = mockRecoveryFetch({ reject: true });

  renderRecovery();

  expect(await screen.findByText("Recovery view unavailable")).toBeInTheDocument();
  expect(
    screen.getByText(/Current recovery state is not inferred/i),
  ).toBeInTheDocument();
  await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
});

test("recovery route fails closed for malformed required", async () => {
  mockRecoveryFetch({
    payload: { ...recoveryStatus(), required: "true" },
  });

  renderRecovery();

  expect(await screen.findByText("Recovery view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/malformed/i)).toBeInTheDocument();
});

test("recovery route fails closed for malformed nullable fields", async () => {
  for (const payload of [
    { ...recoveryStatus(), reason: 123 },
    { ...recoveryStatus(), pair_id: false },
    { ...recoveryStatus(), phase: ["RECOVERY_REQUIRED"] },
  ]) {
    vi.restoreAllMocks();
    mockRecoveryFetch({ payload });

    const view = renderRecovery();

    expect(await screen.findByText("Recovery view unavailable")).toBeInTheDocument();
    expect(screen.getByText(/malformed/i)).toBeInTheDocument();
    view.unmount();
  }
});

test("recovery route fails closed for malformed active lock", async () => {
  mockRecoveryFetch({
    payload: { ...recoveryStatus(), active_lock: "false" },
  });

  renderRecovery();

  expect(await screen.findByText("Recovery view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/malformed/i)).toBeInTheDocument();
});

test("recovery route fails closed for malformed updated timestamp", async () => {
  mockRecoveryFetch({
    payload: { ...recoveryStatus(), updated_at: null },
  });

  renderRecovery();

  expect(await screen.findByText("Recovery view unavailable")).toBeInTheDocument();
  expect(screen.getByText(/malformed/i)).toBeInTheDocument();
});

test("recovery route manual refresh issues one additional GET", async () => {
  const fetchSpy = mockRecoveryFetch();
  const user = userEvent.setup();

  renderRecovery();
  await screen.findByText("Recovery Status");

  await user.click(screen.getByRole("button", { name: "Refresh status" }));

  await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
  expect(
    fetchSpy.mock.calls.filter(([input]) => String(input) === recoveryEndpoint),
  ).toHaveLength(2);
});

test("recovery route prevents duplicate concurrent refresh requests", async () => {
  const recoveryRefresh = deferredResponse();
  let recoveryCalls = 0;
  const fetchSpy = mockFetch((input) => {
    const url = String(input);
    if (url === recoveryEndpoint) {
      recoveryCalls += 1;
      return recoveryCalls === 1
        ? jsonResponse(recoveryStatus())
        : recoveryRefresh.promise;
    }
    return jsonResponse(operatorStatus());
  });
  const user = userEvent.setup();

  renderRecovery();
  await screen.findByText("Recovery Status");

  await user.dblClick(screen.getByRole("button", { name: "Refresh status" }));

  expect(screen.getByRole("button", { name: "Refresh in progress" })).toBeDisabled();
  expect(fetchSpy).toHaveBeenCalledTimes(2);
  expect(recoveryCalls).toBe(2);

  recoveryRefresh.resolve(
    new Response(JSON.stringify(recoveryStatus({ reason: "RECOVERY_RECHECK" })), {
      headers: { "Content-Type": "application/json" },
      status: 200,
    }),
  );
  expect(await screen.findByText("RECOVERY_RECHECK")).toBeInTheDocument();
});

test("recovery route performs no automatic retry after failure", async () => {
  const fetchSpy = mockRecoveryFetch({ reject: true });

  renderRecovery();

  expect(await screen.findByText("Recovery view unavailable")).toBeInTheDocument();
  await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
});

test("recovery route does not use polling or streaming transports", async () => {
  const webSocketSpy =
    "WebSocket" in globalThis ? vi.spyOn(globalThis, "WebSocket") : null;
  const eventSourceSpy =
    "EventSource" in globalThis ? vi.spyOn(globalThis, "EventSource") : null;
  const fetchSpy = mockRecoveryFetch();

  renderRecovery();
  await screen.findByText("Recovery Status");

  expect(fetchSpy).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "Refresh status" })).toBeEnabled();
  if (webSocketSpy) {
    expect(webSocketSpy).not.toHaveBeenCalled();
  }
  if (eventSourceSpy) {
    expect(eventSourceSpy).not.toHaveBeenCalled();
  }
});

test("recovery route exposes no recovery action controls or mutation methods", async () => {
  const fetchSpy = mockRecoveryFetch();

  renderRecovery();
  await screen.findByText("Recovery Status");

  expect(screen.getAllByRole("button")).toHaveLength(1);
  expect(
    screen.queryByRole("button", {
      name: /recover|start recovery|trigger recovery|clear recovery|acknowledge recovery|retry recovery|repair|resume|unlock|release lock|cancel recovery|complete recovery/i,
    }),
  ).not.toBeInTheDocument();
  for (const [, init] of fetchSpy.mock.calls) {
    expect(init).toEqual(
      expect.objectContaining({
        method: "GET",
      }),
    );
    expect(init).not.toEqual(expect.objectContaining({ method: "POST" }));
    expect(init).not.toEqual(expect.objectContaining({ method: "PUT" }));
    expect(init).not.toEqual(expect.objectContaining({ method: "PATCH" }));
    expect(init).not.toEqual(expect.objectContaining({ method: "DELETE" }));
  }
});

test("pair-audit route starts idle with explicit pair-scoped context and labelled input", () => {
  const fetchSpy = mockPairAuditFetch();

  renderPairAudit();

  expect(
    screen.getByRole("heading", { level: 1, name: "Pair-Scoped Audit Activity" }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Protective pair ID")).toBeInTheDocument();
  expect(
    screen.getByText("No pair-scoped event request has been submitted."),
  ).toBeInTheDocument();
  expect(screen.getByText(/one protective pair only/i)).toBeInTheDocument();
  expect(screen.queryByText(/global/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/system-wide/i)).not.toBeInTheDocument();
  expect(fetchSpy).not.toHaveBeenCalled();
});

test("pair-audit blank pair id sends no request", async () => {
  const fetchSpy = mockPairAuditFetch();
  const user = userEvent.setup();

  renderPairAudit();
  await user.click(screen.getByRole("button", { name: "Load pair events" }));

  expect(await screen.findByText("Invalid protective pair ID")).toBeInTheDocument();
  expect(fetchSpy).not.toHaveBeenCalled();
});

test("pair-audit invalid pair id sends no request", async () => {
  const fetchSpy = mockPairAuditFetch();
  const user = userEvent.setup();

  renderPairAudit();
  await user.type(screen.getByLabelText("Protective pair ID"), "-bad-pair");
  await user.click(screen.getByRole("button", { name: "Load pair events" }));

  expect(await screen.findByText("Invalid protective pair ID")).toBeInTheDocument();
  expect(fetchSpy).not.toHaveBeenCalled();
});

test("pair-audit valid pair id constructs the encoded read-only default request", async () => {
  const fetchSpy = mockPairAuditFetch();
  const user = userEvent.setup();

  renderPairAudit();
  await user.type(screen.getByLabelText("Protective pair ID"), "pair:001");
  await user.click(screen.getByRole("button", { name: "Load pair events" }));

  expect(await screen.findByText("Pair-scoped event history")).toBeInTheDocument();
  expect(fetchSpy).toHaveBeenCalledTimes(1);
  expect(fetchSpy).toHaveBeenCalledWith(
    encodedPairAuditEndpoint,
    expect.objectContaining({
      method: "GET",
      headers: { Accept: "application/json" },
    }),
  );
  expect(fetchSpy.mock.calls[0][1]).not.toHaveProperty("body");
  expect(fetchSpy.mock.calls[0][1]).not.toEqual(
    expect.objectContaining({ method: "POST" }),
  );
  expect(fetchSpy.mock.calls[0][1]).not.toEqual(
    expect.objectContaining({ method: "PUT" }),
  );
  expect(fetchSpy.mock.calls[0][1]).not.toEqual(
    expect.objectContaining({ method: "PATCH" }),
  );
  expect(fetchSpy.mock.calls[0][1]).not.toEqual(
    expect.objectContaining({ method: "DELETE" }),
  );
});

test("pair-audit success renders all backend event fields and pagination values", async () => {
  mockPairAuditFetch();
  const user = userEvent.setup();

  renderPairAudit();
  await user.type(screen.getByLabelText("Protective pair ID"), "pair-001");
  await user.click(screen.getByRole("button", { name: "Load pair events" }));

  expect(await screen.findByText("Pair-scoped event history")).toBeInTheDocument();
  expect(screen.getByText("pair-001")).toBeInTheDocument();
  expect(screen.getByText("limit 50, offset 0")).toBeInTheDocument();
  expect(screen.getByText("RECOVERY_EVENT")).toBeInTheDocument();
  expect(screen.getByText("11111111-1111-4111-8111-111111111111")).toBeInTheDocument();
  expect(screen.getByText("PAIR_RECOVERY_STARTED")).toBeInTheDocument();
  expect(screen.getByText("PAIR_RECOVERY_VIEWED")).toBeInTheDocument();
  expect(screen.getByText("ACTIVE")).toBeInTheDocument();
  expect(screen.getByText("RECOVERY_REQUIRED")).toBeInTheDocument();
  expect(screen.getByText("EXCHANGE_ORDER_MISSING")).toBeInTheDocument();
  expect(screen.getByText("RECORDED")).toBeInTheDocument();
  expect(screen.getByText("NOT_APPLICABLE")).toBeInTheDocument();
  expect(screen.getByText("2026-08-14T12:01:00+00:00")).toBeInTheDocument();
});

test("pair-audit renders explicit nullable and empty-events states", async () => {
  mockPairAuditFetch({
    payload: pairAuditResponse({
      events: [],
    }),
  });
  const user = userEvent.setup();

  renderPairAudit();
  await user.type(screen.getByLabelText("Protective pair ID"), "pair-001");
  await user.click(screen.getByRole("button", { name: "Load pair events" }));

  expect(
    await screen.findByText(
      "Backend reports no pair-scoped events for this protective pair.",
    ),
  ).toBeInTheDocument();
});

test("pair-audit fails closed for HTTP 400", async () => {
  mockPairAuditFetch({
    payload: { detail: "bad request" },
    init: { status: 400 },
  });
  const user = userEvent.setup();

  renderPairAudit();
  await user.type(screen.getByLabelText("Protective pair ID"), "pair-001");
  await user.click(screen.getByRole("button", { name: "Load pair events" }));

  expect(
    await screen.findByText("Pair-scoped event view unavailable"),
  ).toBeInTheDocument();
  expect(screen.getByText(/rejected this pair-scoped request/i)).toBeInTheDocument();
  expect(screen.queryByText("Pair-scoped event history")).not.toBeInTheDocument();
});

test("pair-audit fails closed for HTTP 403", async () => {
  mockPairAuditFetch({
    payload: { detail: "forbidden" },
    init: { status: 403 },
  });
  const user = userEvent.setup();

  renderPairAudit();
  await user.type(screen.getByLabelText("Protective pair ID"), "pair-001");
  await user.click(screen.getByRole("button", { name: "Load pair events" }));

  expect(
    await screen.findByText("Pair-scoped event view unavailable"),
  ).toBeInTheDocument();
  expect(screen.getByText(/forbidden/i)).toBeInTheDocument();
});

test("pair-audit fails closed for HTTP 404", async () => {
  mockPairAuditFetch({
    payload: { detail: "not found" },
    init: { status: 404 },
  });
  const user = userEvent.setup();

  renderPairAudit();
  await user.type(screen.getByLabelText("Protective pair ID"), "pair-001");
  await user.click(screen.getByRole("button", { name: "Load pair events" }));

  expect(
    await screen.findByText("Pair-scoped event view unavailable"),
  ).toBeInTheDocument();
  expect(screen.getByText(/did not find this protective pair/i)).toBeInTheDocument();
});

test("pair-audit fails closed for unavailable transport", async () => {
  const fetchSpy = mockPairAuditFetch({ reject: true });
  const user = userEvent.setup();

  renderPairAudit();
  await user.type(screen.getByLabelText("Protective pair ID"), "pair-001");
  await user.click(screen.getByRole("button", { name: "Load pair events" }));

  expect(
    await screen.findByText("Pair-scoped event view unavailable"),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("heading", {
      name: "Pair-scoped event view unavailable",
    }),
  ).toBeInTheDocument();
  await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
});

test("pair-audit fails closed for malformed top-level response", async () => {
  mockPairAuditFetch({
    payload: { ...pairAuditResponse(), limit: "50" },
  });
  const user = userEvent.setup();

  renderPairAudit();
  await user.type(screen.getByLabelText("Protective pair ID"), "pair-001");
  await user.click(screen.getByRole("button", { name: "Load pair events" }));

  expect(
    await screen.findByText("Pair-scoped event view unavailable"),
  ).toBeInTheDocument();
  expect(screen.getByText(/malformed/i)).toBeInTheDocument();
});

test("pair-audit fails closed for malformed event item", async () => {
  mockPairAuditFetch({
    payload: pairAuditResponse({
      events: [
        {
          ...pairAuditResponse().events[0],
          error_code: false,
        },
      ],
    }),
  });
  const user = userEvent.setup();

  renderPairAudit();
  await user.type(screen.getByLabelText("Protective pair ID"), "pair-001");
  await user.click(screen.getByRole("button", { name: "Load pair events" }));

  expect(
    await screen.findByText("Pair-scoped event view unavailable"),
  ).toBeInTheDocument();
  expect(screen.getByText(/malformed/i)).toBeInTheDocument();
});

test("pair-audit duplicate concurrent submission sends no additional request", async () => {
  const pending = deferredResponse();
  const fetchSpy = mockFetch((input) => {
    if (String(input) === pairAuditEndpoint) {
      return pending.promise;
    }
    return jsonResponse(operatorStatus());
  });
  const user = userEvent.setup();

  renderPairAudit();
  await user.type(screen.getByLabelText("Protective pair ID"), "pair-001");
  await user.dblClick(screen.getByRole("button", { name: "Load pair events" }));

  expect(screen.getByRole("button", { name: "Loading pair events" })).toBeDisabled();
  expect(fetchSpy).toHaveBeenCalledTimes(1);

  pending.resolve(
    new Response(JSON.stringify(pairAuditResponse()), {
      headers: { "Content-Type": "application/json" },
      status: 200,
    }),
  );
  expect(await screen.findByText("Pair-scoped event history")).toBeInTheDocument();
});

test("pair-audit performs no automatic retry, polling, streaming, or mutation controls", async () => {
  const webSocketSpy =
    "WebSocket" in globalThis ? vi.spyOn(globalThis, "WebSocket") : null;
  const eventSourceSpy =
    "EventSource" in globalThis ? vi.spyOn(globalThis, "EventSource") : null;
  const fetchSpy = mockPairAuditFetch({ reject: true });
  const user = userEvent.setup();

  renderPairAudit();
  await user.type(screen.getByLabelText("Protective pair ID"), "pair-001");
  await user.click(screen.getByRole("button", { name: "Load pair events" }));

  expect(
    await screen.findByText("Pair-scoped event view unavailable"),
  ).toBeInTheDocument();
  await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
  expect(screen.getAllByRole("button")).toHaveLength(1);
  expect(
    screen.queryByRole("button", {
      name: /create|update|delete|cancel|submit order|trade|permit|recover|kill switch|protective pair/i,
    }),
  ).not.toBeInTheDocument();
  if (webSocketSpy) {
    expect(webSocketSpy).not.toHaveBeenCalled();
  }
  if (eventSourceSpy) {
    expect(eventSourceSpy).not.toHaveBeenCalled();
  }
  for (const [, init] of fetchSpy.mock.calls) {
    expect(init).toEqual(expect.objectContaining({ method: "GET" }));
    expect(init).not.toEqual(expect.objectContaining({ method: "POST" }));
    expect(init).not.toEqual(expect.objectContaining({ method: "PUT" }));
    expect(init).not.toEqual(expect.objectContaining({ method: "PATCH" }));
    expect(init).not.toEqual(expect.objectContaining({ method: "DELETE" }));
  }
});
