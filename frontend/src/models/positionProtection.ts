export interface PositionResponse {
  symbol: string;
  position_side: string | null;
  direction: string | null;
  quantity: string;
  entry_price: string;
  break_even_price: string;
  mark_price: string;
  notional_usdt: string;
  unrealized_pnl: string;
  liquidation_price: string;
  has_open_position: boolean;
  source: string;
  updated_at: string;
}

export interface ProtectiveOrderSummaryResponse {
  client_algo_id: string | null;
  algo_id: string | null;
  status: string | null;
  trigger_price: string | null;
}

export interface ProtectiveOrdersCurrentResponse {
  state: string;
  pair_id: string | null;
  recovery_required: boolean;
  blocking_reason: string | null;
  active_lock: boolean;
  stop: ProtectiveOrderSummaryResponse | null;
  take_profit: ProtectiveOrderSummaryResponse | null;
  updated_at: string;
}

export type PositionParseResult =
  | { ok: true; data: PositionResponse }
  | { ok: false };

export type ProtectiveOrdersParseResult =
  | { ok: true; data: ProtectiveOrdersCurrentResponse }
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

function parseOrderSummary(value: unknown): ProtectiveOrderSummaryResponse | null {
  if (!isRecord(value)) {
    return null;
  }

  const clientAlgoId = value.client_algo_id;
  const algoId = value.algo_id;
  const status = value.status;
  const triggerPrice = value.trigger_price;

  if (
    !isNullableString(clientAlgoId) ||
    !isNullableString(algoId) ||
    !isNullableString(status) ||
    !isNullableString(triggerPrice)
  ) {
    return null;
  }

  return {
    client_algo_id: clientAlgoId,
    algo_id: algoId,
    status,
    trigger_price: triggerPrice,
  };
}

function parseNullableOrderSummary(
  value: unknown,
): ProtectiveOrderSummaryResponse | null | undefined {
  if (value === null) {
    return null;
  }

  const summary = parseOrderSummary(value);
  return summary ?? undefined;
}

export function parsePositionResponse(value: unknown): PositionParseResult {
  if (!isRecord(value)) {
    return { ok: false };
  }

  const symbol = value.symbol;
  const positionSide = value.position_side;
  const direction = value.direction;
  const quantity = value.quantity;
  const entryPrice = value.entry_price;
  const breakEvenPrice = value.break_even_price;
  const markPrice = value.mark_price;
  const notionalUsdt = value.notional_usdt;
  const unrealizedPnl = value.unrealized_pnl;
  const liquidationPrice = value.liquidation_price;
  const hasOpenPosition = value.has_open_position;
  const source = value.source;
  const updatedAt = value.updated_at;

  if (
    !isString(symbol) ||
    !isNullableString(positionSide) ||
    !isNullableString(direction) ||
    !isString(quantity) ||
    !isString(entryPrice) ||
    !isString(breakEvenPrice) ||
    !isString(markPrice) ||
    !isString(notionalUsdt) ||
    !isString(unrealizedPnl) ||
    !isString(liquidationPrice) ||
    typeof hasOpenPosition !== "boolean" ||
    !isString(source) ||
    !isString(updatedAt)
  ) {
    return { ok: false };
  }

  if (symbol !== "BTCUSDT") {
    return { ok: false };
  }

  return {
    ok: true,
    data: {
      symbol,
      position_side: positionSide,
      direction,
      quantity,
      entry_price: entryPrice,
      break_even_price: breakEvenPrice,
      mark_price: markPrice,
      notional_usdt: notionalUsdt,
      unrealized_pnl: unrealizedPnl,
      liquidation_price: liquidationPrice,
      has_open_position: hasOpenPosition,
      source,
      updated_at: updatedAt,
    },
  };
}

export function parseProtectiveOrdersCurrentResponse(
  value: unknown,
): ProtectiveOrdersParseResult {
  if (!isRecord(value)) {
    return { ok: false };
  }

  const state = value.state;
  const pairId = value.pair_id;
  const recoveryRequired = value.recovery_required;
  const blockingReason = value.blocking_reason;
  const activeLock = value.active_lock;
  const stop = parseNullableOrderSummary(value.stop);
  const takeProfit = parseNullableOrderSummary(value.take_profit);
  const updatedAt = value.updated_at;

  if (
    !isString(state) ||
    !isNullableString(pairId) ||
    typeof recoveryRequired !== "boolean" ||
    !isNullableString(blockingReason) ||
    typeof activeLock !== "boolean" ||
    stop === undefined ||
    takeProfit === undefined ||
    !isString(updatedAt)
  ) {
    return { ok: false };
  }

  return {
    ok: true,
    data: {
      state,
      pair_id: pairId,
      recovery_required: recoveryRequired,
      blocking_reason: blockingReason,
      active_lock: activeLock,
      stop,
      take_profit: takeProfit,
      updated_at: updatedAt,
    },
  };
}
