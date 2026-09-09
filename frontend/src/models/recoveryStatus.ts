export interface RecoveryStatusResponse {
  required: boolean;
  reason: string | null;
  pair_id: string | null;
  phase: string | null;
  active_lock: boolean;
  updated_at: string;
}

type ParseRecoveryStatusResult =
  | { ok: true; data: RecoveryStatusResponse }
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

function isBoolean(value: unknown): value is boolean {
  return typeof value === "boolean";
}

export function parseRecoveryStatusResponse(
  value: unknown,
): ParseRecoveryStatusResult {
  if (!isRecord(value)) {
    return { ok: false };
  }

  const required = value.required;
  const reason = value.reason;
  const pairId = value.pair_id;
  const phase = value.phase;
  const activeLock = value.active_lock;
  const updatedAt = value.updated_at;

  if (
    isBoolean(required) &&
    isNullableString(reason) &&
    isNullableString(pairId) &&
    isNullableString(phase) &&
    isBoolean(activeLock) &&
    isString(updatedAt)
  ) {
    return {
      ok: true,
      data: {
        required,
        reason,
        pair_id: pairId,
        phase,
        active_lock: activeLock,
        updated_at: updatedAt,
      },
    };
  }

  return { ok: false };
}
