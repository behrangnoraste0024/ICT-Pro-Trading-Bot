export interface OperatorWarningResponse {
  code: string;
  severity: string;
  message: string;
  source: string;
}

export interface OperatorStatusResponse {
  environment: string;
  symbol: string;
  overall_status: string;
  kill_switch_state: string | null;
  kill_switch_available: boolean;
  recovery_required: boolean;
  recovery_available: boolean;
  persistence_configured: boolean;
  persistence_reachable: boolean;
  persistence_schema_ready: boolean;
  readiness_status: string;
  validation_gate: string;
  active_lock: boolean;
  warnings: OperatorWarningResponse[];
  updated_at: string;
}

export type OperatorStatusParseResult =
  | { ok: true; data: OperatorStatusResponse }
  | { ok: false };

const requiredStringFields = [
  "environment",
  "symbol",
  "overall_status",
  "readiness_status",
  "validation_gate",
  "updated_at",
] as const;

const requiredBooleanFields = [
  "kill_switch_available",
  "recovery_required",
  "recovery_available",
  "persistence_configured",
  "persistence_reachable",
  "persistence_schema_ready",
  "active_lock",
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isRequiredString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function parseWarning(value: unknown): OperatorWarningResponse | null {
  if (!isRecord(value)) {
    return null;
  }

  const { code, severity, message, source } = value;
  if (
    !isRequiredString(code) ||
    !isRequiredString(severity) ||
    !isRequiredString(message) ||
    !isRequiredString(source)
  ) {
    return null;
  }

  return { code, severity, message, source };
}

export function parseOperatorStatusResponse(
  value: unknown,
): OperatorStatusParseResult {
  if (!isRecord(value)) {
    return { ok: false };
  }

  const environment = value.environment;
  const symbol = value.symbol;
  const overallStatus = value.overall_status;
  const killSwitchState = value.kill_switch_state;
  const killSwitchAvailable = value.kill_switch_available;
  const recoveryRequired = value.recovery_required;
  const recoveryAvailable = value.recovery_available;
  const persistenceConfigured = value.persistence_configured;
  const persistenceReachable = value.persistence_reachable;
  const persistenceSchemaReady = value.persistence_schema_ready;
  const readinessStatus = value.readiness_status;
  const validationGate = value.validation_gate;
  const activeLock = value.active_lock;
  const rawWarnings = value.warnings;
  const updatedAt = value.updated_at;

  if (
    !isRequiredString(environment) ||
    !isRequiredString(symbol) ||
    !isRequiredString(overallStatus) ||
    !isRequiredString(readinessStatus) ||
    !isRequiredString(validationGate) ||
    !isRequiredString(updatedAt)
  ) {
    return { ok: false };
  }

  if (
    typeof killSwitchAvailable !== "boolean" ||
    typeof recoveryRequired !== "boolean" ||
    typeof recoveryAvailable !== "boolean" ||
    typeof persistenceConfigured !== "boolean" ||
    typeof persistenceReachable !== "boolean" ||
    typeof persistenceSchemaReady !== "boolean" ||
    typeof activeLock !== "boolean"
  ) {
    return { ok: false };
  }

  if (environment !== "BINANCE_FUTURES_TESTNET" || symbol !== "BTCUSDT") {
    return { ok: false };
  }

  if (killSwitchState !== null && typeof killSwitchState !== "string") {
    return { ok: false };
  }

  if (!Array.isArray(rawWarnings)) {
    return { ok: false };
  }

  const warnings: OperatorWarningResponse[] = [];
  for (const rawWarning of rawWarnings) {
    const warning = parseWarning(rawWarning);
    if (warning === null) {
      return { ok: false };
    }
    warnings.push(warning);
  }

  if (
    requiredStringFields.some((field) => !isRequiredString(value[field])) ||
    requiredBooleanFields.some((field) => typeof value[field] !== "boolean")
  ) {
    return { ok: false };
  }

  return {
    ok: true,
    data: {
      environment,
      symbol,
      overall_status: overallStatus,
      kill_switch_state: killSwitchState,
      kill_switch_available: killSwitchAvailable,
      recovery_required: recoveryRequired,
      recovery_available: recoveryAvailable,
      persistence_configured: persistenceConfigured,
      persistence_reachable: persistenceReachable,
      persistence_schema_ready: persistenceSchemaReady,
      readiness_status: readinessStatus,
      validation_gate: validationGate,
      active_lock: activeLock,
      warnings,
      updated_at: updatedAt,
    },
  };
}
