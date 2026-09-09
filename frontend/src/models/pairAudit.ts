export interface PairAuditEventResponse {
  event_kind: string;
  correlation_id: string | null;
  event_type: string | null;
  action: string | null;
  from_state: string | null;
  to_state: string | null;
  reason_code: string | null;
  result: string;
  error_code: string | null;
  created_at: string;
}

export interface PairAuditResponse {
  pair_id: string;
  events: PairAuditEventResponse[];
  limit: number;
  offset: number;
}

type PairAuditParseResult =
  | { ok: true; data: PairAuditResponse }
  | { ok: false };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNullableString(value: unknown): value is string | null {
  return value === null || isString(value);
}

function isInteger(value: unknown): value is number {
  return Number.isInteger(value);
}

function parsePairAuditEvent(value: unknown): PairAuditEventResponse | null {
  if (!isRecord(value)) {
    return null;
  }

  const eventKind = value.event_kind;
  const correlationId = value.correlation_id;
  const eventType = value.event_type;
  const action = value.action;
  const fromState = value.from_state;
  const toState = value.to_state;
  const reasonCode = value.reason_code;
  const result = value.result;
  const errorCode = value.error_code;
  const createdAt = value.created_at;

  if (
    !isString(eventKind) ||
    !isNullableString(correlationId) ||
    !isNullableString(eventType) ||
    !isNullableString(action) ||
    !isNullableString(fromState) ||
    !isNullableString(toState) ||
    !isNullableString(reasonCode) ||
    !isString(result) ||
    !isNullableString(errorCode) ||
    !isString(createdAt)
  ) {
    return null;
  }

  return {
    event_kind: eventKind,
    correlation_id: correlationId,
    event_type: eventType,
    action,
    from_state: fromState,
    to_state: toState,
    reason_code: reasonCode,
    result,
    error_code: errorCode,
    created_at: createdAt,
  };
}

export function parsePairAuditResponse(value: unknown): PairAuditParseResult {
  if (!isRecord(value)) {
    return { ok: false };
  }

  const pairId = value.pair_id;
  const events = value.events;
  const limit = value.limit;
  const offset = value.offset;

  if (
    !isString(pairId) ||
    !Array.isArray(events) ||
    !isInteger(limit) ||
    !isInteger(offset)
  ) {
    return { ok: false };
  }

  const parsedEvents: PairAuditEventResponse[] = [];
  for (const event of events) {
    const parsedEvent = parsePairAuditEvent(event);
    if (parsedEvent === null) {
      return { ok: false };
    }
    parsedEvents.push(parsedEvent);
  }

  return {
    ok: true,
    data: {
      pair_id: pairId,
      events: parsedEvents,
      limit,
      offset,
    },
  };
}
