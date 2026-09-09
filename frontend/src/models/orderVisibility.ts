export interface ExecutionIntentReadResponse {
  correlation_id: string;
  environment: string;
  symbol: string;
  intent_type: string;
  state: string;
  requested_quantity: string | null;
  requested_price: string | null;
  failure_code: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ExecutionIntentListResponse {
  items: ExecutionIntentReadResponse[];
  limit: number;
  offset: number;
  count: number;
  updated_at: string;
}

export interface ExchangeOrderIdentityReadResponse {
  leg_type: string;
  client_algo_id: string;
  exchange_algo_id: string | null;
  exchange_order_id: string | null;
  status: string;
  trigger_price: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  pair_id: string;
  correlation_id: string;
}

export interface ExchangeOrderIdentityListResponse {
  items: ExchangeOrderIdentityReadResponse[];
  limit: number;
  offset: number;
  count: number;
  updated_at: string;
}

export type ExecutionIntentListParseResult =
  | { ok: true; data: ExecutionIntentListResponse }
  | { ok: false };

export type ExchangeOrderListParseResult =
  | { ok: true; data: ExchangeOrderIdentityListResponse }
  | { ok: false };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isInteger(value: unknown): value is number {
  return Number.isInteger(value);
}

function parseExecutionIntent(
  value: unknown,
): ExecutionIntentReadResponse | null {
  if (!isRecord(value)) {
    return null;
  }

  const correlationId = value.correlation_id;
  const environment = value.environment;
  const symbol = value.symbol;
  const intentType = value.intent_type;
  const state = value.state;
  const requestedQuantity = value.requested_quantity;
  const requestedPrice = value.requested_price;
  const failureCode = value.failure_code;
  const version = value.version;
  const createdAt = value.created_at;
  const updatedAt = value.updated_at;

  if (
    !isString(correlationId) ||
    !isString(environment) ||
    !isString(symbol) ||
    !isString(intentType) ||
    !isString(state) ||
    !isNullableString(requestedQuantity) ||
    !isNullableString(requestedPrice) ||
    !isNullableString(failureCode) ||
    !isInteger(version) ||
    !isString(createdAt) ||
    !isString(updatedAt)
  ) {
    return null;
  }

  return {
    correlation_id: correlationId,
    environment,
    symbol,
    intent_type: intentType,
    state,
    requested_quantity: requestedQuantity,
    requested_price: requestedPrice,
    failure_code: failureCode,
    version,
    created_at: createdAt,
    updated_at: updatedAt,
  };
}

function parseExchangeOrder(
  value: unknown,
): ExchangeOrderIdentityReadResponse | null {
  if (!isRecord(value)) {
    return null;
  }

  const legType = value.leg_type;
  const clientAlgoId = value.client_algo_id;
  const exchangeAlgoId = value.exchange_algo_id;
  const exchangeOrderId = value.exchange_order_id;
  const status = value.status;
  const triggerPrice = value.trigger_price;
  const version = value.version;
  const createdAt = value.created_at;
  const updatedAt = value.updated_at;
  const pairId = value.pair_id;
  const correlationId = value.correlation_id;

  if (
    !isString(legType) ||
    !isString(clientAlgoId) ||
    !isNullableString(exchangeAlgoId) ||
    !isNullableString(exchangeOrderId) ||
    !isString(status) ||
    !isNullableString(triggerPrice) ||
    !isInteger(version) ||
    !isString(createdAt) ||
    !isString(updatedAt) ||
    !isString(pairId) ||
    !isString(correlationId)
  ) {
    return null;
  }

  return {
    leg_type: legType,
    client_algo_id: clientAlgoId,
    exchange_algo_id: exchangeAlgoId,
    exchange_order_id: exchangeOrderId,
    status,
    trigger_price: triggerPrice,
    version,
    created_at: createdAt,
    updated_at: updatedAt,
    pair_id: pairId,
    correlation_id: correlationId,
  };
}

function parseListMetadata(value: Record<string, unknown>) {
  const limit = value.limit;
  const offset = value.offset;
  const count = value.count;
  const updatedAt = value.updated_at;

  if (
    !isInteger(limit) ||
    !isInteger(offset) ||
    !isInteger(count) ||
    !isString(updatedAt)
  ) {
    return null;
  }

  return { limit, offset, count, updated_at: updatedAt };
}

export function parseExecutionIntentListResponse(
  value: unknown,
): ExecutionIntentListParseResult {
  if (!isRecord(value) || !Array.isArray(value.items)) {
    return { ok: false };
  }

  const metadata = parseListMetadata(value);
  if (metadata === null) {
    return { ok: false };
  }

  const items: ExecutionIntentReadResponse[] = [];
  for (const item of value.items) {
    const parsed = parseExecutionIntent(item);
    if (parsed === null) {
      return { ok: false };
    }
    items.push(parsed);
  }

  return {
    ok: true,
    data: {
      items,
      ...metadata,
    },
  };
}

export function parseExchangeOrderListResponse(
  value: unknown,
): ExchangeOrderListParseResult {
  if (!isRecord(value) || !Array.isArray(value.items)) {
    return { ok: false };
  }

  const metadata = parseListMetadata(value);
  if (metadata === null) {
    return { ok: false };
  }

  const items: ExchangeOrderIdentityReadResponse[] = [];
  for (const item of value.items) {
    const parsed = parseExchangeOrder(item);
    if (parsed === null) {
      return { ok: false };
    }
    items.push(parsed);
  }

  return {
    ok: true,
    data: {
      items,
      ...metadata,
    },
  };
}
