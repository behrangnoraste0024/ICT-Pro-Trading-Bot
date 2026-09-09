import {
  parseKillSwitchStatusResponse,
  parseLiveReadinessResponse,
  parseLiveSafetyStatusResponse,
  parsePersistenceStatusResponse,
  type KillSwitchControlResponse,
  type LiveReadinessResponse,
  type LiveSafetyStatusResponse,
  type PersistenceStatusResponse,
} from "../models/liveSafetyDetail";
import {
  parseOperatorStatusResponse,
  type OperatorStatusResponse,
} from "../models/operatorStatus";
import {
  parseExchangeOrderListResponse,
  parseExecutionIntentListResponse,
  type ExchangeOrderIdentityListResponse,
  type ExecutionIntentListResponse,
} from "../models/orderVisibility";
import {
  parsePositionResponse,
  parseProtectiveOrdersCurrentResponse,
  type PositionResponse,
  type ProtectiveOrdersCurrentResponse,
} from "../models/positionProtection";
import {
  parseRecoveryStatusResponse,
  type RecoveryStatusResponse,
} from "../models/recoveryStatus";
import {
  parsePairAuditResponse,
  type PairAuditResponse,
} from "../models/pairAudit";

export interface ReadOnlyClient {
  operatorStatus(signal?: AbortSignal): Promise<OperatorStatusResponse>;
  executionIntents(signal?: AbortSignal): Promise<ExecutionIntentListResponse>;
  exchangeOrders(
    signal?: AbortSignal,
  ): Promise<ExchangeOrderIdentityListResponse>;
  liveSafetyStatus(signal?: AbortSignal): Promise<LiveSafetyStatusResponse>;
  liveReadiness(signal?: AbortSignal): Promise<LiveReadinessResponse>;
  persistenceStatus(signal?: AbortSignal): Promise<PersistenceStatusResponse>;
  killSwitchStatus(signal?: AbortSignal): Promise<KillSwitchControlResponse>;
  recoveryStatus(signal?: AbortSignal): Promise<RecoveryStatusResponse>;
  position(signal?: AbortSignal): Promise<PositionResponse>;
  protectiveOrders(
    signal?: AbortSignal,
  ): Promise<ProtectiveOrdersCurrentResponse>;
  protectivePairEvents(
    pairId: string,
    limit: number,
    offset: number,
    signal?: AbortSignal,
  ): Promise<PairAuditResponse>;
}

export class BadRequestReadOnlyRequestError extends Error {
  constructor(message = "Read-only request was invalid.") {
    super(message);
    this.name = "BadRequestReadOnlyRequestError";
  }
}

export class ForbiddenReadOnlyRequestError extends Error {
  constructor(message = "Read-only request was forbidden.") {
    super(message);
    this.name = "ForbiddenReadOnlyRequestError";
  }
}

export class NotFoundReadOnlyRequestError extends Error {
  constructor(message = "Read-only resource was not found.") {
    super(message);
    this.name = "NotFoundReadOnlyRequestError";
  }
}

export class MalformedReadOnlyResponseError extends Error {
  constructor(message = "Read-only response was malformed.") {
    super(message);
    this.name = "MalformedReadOnlyResponseError";
  }
}

export class UnavailableReadOnlyRequestError extends Error {
  constructor(message = "Read-only request was unavailable.") {
    super(message);
    this.name = "UnavailableReadOnlyRequestError";
  }
}

export class ForbiddenOperatorStatusError extends ForbiddenReadOnlyRequestError {
  constructor() {
    super("Operator status request was forbidden.");
    this.name = "ForbiddenOperatorStatusError";
  }
}

export class MalformedOperatorStatusError extends MalformedReadOnlyResponseError {
  constructor() {
    super("Operator status response was malformed.");
    this.name = "MalformedOperatorStatusError";
  }
}

export class UnavailableOperatorStatusError extends UnavailableReadOnlyRequestError {
  constructor() {
    super("Operator status request was unavailable.");
    this.name = "UnavailableOperatorStatusError";
  }
}

export const operatorStatusUrl = "/api/v1/live/operator/status";
export const executionIntentsUrl = "/api/v1/live/execution-intents";
export const exchangeOrdersUrl = "/api/v1/live/exchange-orders";
export const liveSafetyStatusUrl = "/api/v1/live/safety/status";
export const liveReadinessUrl = "/api/v1/live/readiness";
export const persistenceStatusUrl = "/api/v1/live/persistence/status";
export const killSwitchStatusUrl = "/api/v1/live/kill-switch/status";
export const recoveryStatusUrl = "/api/v1/live/recovery/status";
export const positionUrl = "/api/v1/live/positions/BTCUSDT";
export const protectiveOrdersUrl = "/api/v1/live/protective-orders/current";
export function protectivePairEventsUrl(
  pairId: string,
  limit: number,
  offset: number,
) {
  return `/api/v1/live/protective-pairs/${encodeURIComponent(
    pairId,
  )}/events?limit=${limit}&offset=${offset}`;
}

async function requestJson(url: string, signal?: AbortSignal): Promise<unknown> {
  let response: Response;

  try {
    response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new UnavailableReadOnlyRequestError();
  }

  if (response.status === 403) {
    throw new ForbiddenReadOnlyRequestError();
  }

  if (response.status === 400) {
    throw new BadRequestReadOnlyRequestError();
  }

  if (response.status === 404) {
    throw new NotFoundReadOnlyRequestError();
  }

  if (!response.ok) {
    throw new UnavailableReadOnlyRequestError();
  }

  try {
    return await response.json();
  } catch {
    throw new MalformedReadOnlyResponseError();
  }
}

export const readOnlyClient: ReadOnlyClient = {
  async operatorStatus(signal?: AbortSignal): Promise<OperatorStatusResponse> {
    try {
      const payload = await requestJson(operatorStatusUrl, signal);
      const parsed = parseOperatorStatusResponse(payload);
      if (!parsed.ok) {
        throw new MalformedOperatorStatusError();
      }

      return parsed.data;
    } catch (error) {
      if (error instanceof ForbiddenReadOnlyRequestError) {
        throw new ForbiddenOperatorStatusError();
      }
      if (error instanceof UnavailableReadOnlyRequestError) {
        throw new UnavailableOperatorStatusError();
      }
      if (error instanceof MalformedReadOnlyResponseError) {
        throw new MalformedOperatorStatusError();
      }
      throw error;
    }
  },

  async executionIntents(
    signal?: AbortSignal,
  ): Promise<ExecutionIntentListResponse> {
    const payload = await requestJson(executionIntentsUrl, signal);
    const parsed = parseExecutionIntentListResponse(payload);
    if (!parsed.ok) {
      throw new MalformedReadOnlyResponseError();
    }

    return parsed.data;
  },

  async exchangeOrders(
    signal?: AbortSignal,
  ): Promise<ExchangeOrderIdentityListResponse> {
    const payload = await requestJson(exchangeOrdersUrl, signal);
    const parsed = parseExchangeOrderListResponse(payload);
    if (!parsed.ok) {
      throw new MalformedReadOnlyResponseError();
    }

    return parsed.data;
  },

  async liveSafetyStatus(
    signal?: AbortSignal,
  ): Promise<LiveSafetyStatusResponse> {
    const payload = await requestJson(liveSafetyStatusUrl, signal);
    const parsed = parseLiveSafetyStatusResponse(payload);
    if (!parsed.ok) {
      throw new MalformedReadOnlyResponseError();
    }

    return parsed.data;
  },

  async liveReadiness(signal?: AbortSignal): Promise<LiveReadinessResponse> {
    const payload = await requestJson(liveReadinessUrl, signal);
    const parsed = parseLiveReadinessResponse(payload);
    if (!parsed.ok) {
      throw new MalformedReadOnlyResponseError();
    }

    return parsed.data;
  },

  async persistenceStatus(
    signal?: AbortSignal,
  ): Promise<PersistenceStatusResponse> {
    const payload = await requestJson(persistenceStatusUrl, signal);
    const parsed = parsePersistenceStatusResponse(payload);
    if (!parsed.ok) {
      throw new MalformedReadOnlyResponseError();
    }

    return parsed.data;
  },

  async killSwitchStatus(
    signal?: AbortSignal,
  ): Promise<KillSwitchControlResponse> {
    const payload = await requestJson(killSwitchStatusUrl, signal);
    const parsed = parseKillSwitchStatusResponse(payload);
    if (!parsed.ok) {
      throw new MalformedReadOnlyResponseError();
    }

    return parsed.data;
  },

  async recoveryStatus(signal?: AbortSignal): Promise<RecoveryStatusResponse> {
    const payload = await requestJson(recoveryStatusUrl, signal);
    const parsed = parseRecoveryStatusResponse(payload);
    if (!parsed.ok) {
      throw new MalformedReadOnlyResponseError();
    }

    return parsed.data;
  },

  async position(signal?: AbortSignal): Promise<PositionResponse> {
    const payload = await requestJson(positionUrl, signal);
    const parsed = parsePositionResponse(payload);
    if (!parsed.ok) {
      throw new MalformedReadOnlyResponseError();
    }

    return parsed.data;
  },

  async protectiveOrders(
    signal?: AbortSignal,
  ): Promise<ProtectiveOrdersCurrentResponse> {
    const payload = await requestJson(protectiveOrdersUrl, signal);
    const parsed = parseProtectiveOrdersCurrentResponse(payload);
    if (!parsed.ok) {
      throw new MalformedReadOnlyResponseError();
    }

    return parsed.data;
  },

  async protectivePairEvents(
    pairId: string,
    limit: number,
    offset: number,
    signal?: AbortSignal,
  ): Promise<PairAuditResponse> {
    const payload = await requestJson(
      protectivePairEventsUrl(pairId, limit, offset),
      signal,
    );
    const parsed = parsePairAuditResponse(payload);
    if (!parsed.ok) {
      throw new MalformedReadOnlyResponseError();
    }

    return parsed.data;
  },
};
