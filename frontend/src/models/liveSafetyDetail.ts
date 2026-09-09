export interface LiveSafetyStatusResponse {
  environment: string;
  live_trading_enabled: boolean;
  automatic_execution_enabled: boolean;
  kill_switch_engaged: boolean;
  credentials_configured: boolean;
  active_lock: boolean;
  recovery_required: boolean;
  production_endpoint_allowed: boolean;
  updated_at: string;
}

export interface LiveReadinessResponse {
  status: string;
  symbol: string;
  checks_passed: number;
  checks_warning: number;
  checks_failed: number;
  validation_gate: string;
  blocking_reasons: string[];
  updated_at: string;
}

export interface PersistenceStatusResponse {
  configured: boolean;
  reachable: boolean;
  schema_ready: boolean;
  migration_revision: string | null;
  read_only: boolean;
  source_of_truth: boolean;
  updated_at: string;
}

export interface KillSwitchControlResponse {
  accepted: boolean;
  environment: string;
  symbol: string;
  state: string | null;
  changed: boolean;
  version: number | null;
  updated_at: string | null;
  blocking_code: string | null;
}

export type LiveSafetyStatusParseResult =
  | { ok: true; data: LiveSafetyStatusResponse }
  | { ok: false };

export type LiveReadinessParseResult =
  | { ok: true; data: LiveReadinessResponse }
  | { ok: false };

export type PersistenceStatusParseResult =
  | { ok: true; data: PersistenceStatusResponse }
  | { ok: false };

export type KillSwitchStatusParseResult =
  | { ok: true; data: KillSwitchControlResponse }
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

function isBoolean(value: unknown): value is boolean {
  return typeof value === "boolean";
}

function isInteger(value: unknown): value is number {
  return Number.isInteger(value);
}

function isNullableInteger(value: unknown): value is number | null {
  return value === null || Number.isInteger(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isString);
}

export function parseLiveSafetyStatusResponse(
  value: unknown,
): LiveSafetyStatusParseResult {
  if (!isRecord(value)) {
    return { ok: false };
  }

  const environment = value.environment;
  const liveTradingEnabled = value.live_trading_enabled;
  const automaticExecutionEnabled = value.automatic_execution_enabled;
  const killSwitchEngaged = value.kill_switch_engaged;
  const credentialsConfigured = value.credentials_configured;
  const activeLock = value.active_lock;
  const recoveryRequired = value.recovery_required;
  const productionEndpointAllowed = value.production_endpoint_allowed;
  const updatedAt = value.updated_at;

  if (
    !isString(environment) ||
    !isBoolean(liveTradingEnabled) ||
    !isBoolean(automaticExecutionEnabled) ||
    !isBoolean(killSwitchEngaged) ||
    !isBoolean(credentialsConfigured) ||
    !isBoolean(activeLock) ||
    !isBoolean(recoveryRequired) ||
    !isBoolean(productionEndpointAllowed) ||
    !isString(updatedAt)
  ) {
    return { ok: false };
  }

  return {
    ok: true,
    data: {
      environment,
      live_trading_enabled: liveTradingEnabled,
      automatic_execution_enabled: automaticExecutionEnabled,
      kill_switch_engaged: killSwitchEngaged,
      credentials_configured: credentialsConfigured,
      active_lock: activeLock,
      recovery_required: recoveryRequired,
      production_endpoint_allowed: productionEndpointAllowed,
      updated_at: updatedAt,
    },
  };
}

export function parseLiveReadinessResponse(
  value: unknown,
): LiveReadinessParseResult {
  if (!isRecord(value)) {
    return { ok: false };
  }

  const status = value.status;
  const symbol = value.symbol;
  const checksPassed = value.checks_passed;
  const checksWarning = value.checks_warning;
  const checksFailed = value.checks_failed;
  const validationGate = value.validation_gate;
  const blockingReasons = value.blocking_reasons;
  const updatedAt = value.updated_at;

  if (
    !isString(status) ||
    !isString(symbol) ||
    !isInteger(checksPassed) ||
    !isInteger(checksWarning) ||
    !isInteger(checksFailed) ||
    !isString(validationGate) ||
    !isStringArray(blockingReasons) ||
    !isString(updatedAt)
  ) {
    return { ok: false };
  }

  return {
    ok: true,
    data: {
      status,
      symbol,
      checks_passed: checksPassed,
      checks_warning: checksWarning,
      checks_failed: checksFailed,
      validation_gate: validationGate,
      blocking_reasons: blockingReasons,
      updated_at: updatedAt,
    },
  };
}

export function parsePersistenceStatusResponse(
  value: unknown,
): PersistenceStatusParseResult {
  if (!isRecord(value)) {
    return { ok: false };
  }

  const configured = value.configured;
  const reachable = value.reachable;
  const schemaReady = value.schema_ready;
  const migrationRevision = value.migration_revision;
  const readOnly = value.read_only;
  const sourceOfTruth = value.source_of_truth;
  const updatedAt = value.updated_at;

  if (
    !isBoolean(configured) ||
    !isBoolean(reachable) ||
    !isBoolean(schemaReady) ||
    !isNullableString(migrationRevision) ||
    !isBoolean(readOnly) ||
    !isBoolean(sourceOfTruth) ||
    !isString(updatedAt)
  ) {
    return { ok: false };
  }

  return {
    ok: true,
    data: {
      configured,
      reachable,
      schema_ready: schemaReady,
      migration_revision: migrationRevision,
      read_only: readOnly,
      source_of_truth: sourceOfTruth,
      updated_at: updatedAt,
    },
  };
}

export function parseKillSwitchStatusResponse(
  value: unknown,
): KillSwitchStatusParseResult {
  if (!isRecord(value)) {
    return { ok: false };
  }

  const accepted = value.accepted;
  const environment = value.environment;
  const symbol = value.symbol;
  const state = value.state;
  const changed = value.changed;
  const version = value.version;
  const updatedAt = value.updated_at;
  const blockingCode = value.blocking_code;

  if (
    !isBoolean(accepted) ||
    !isString(environment) ||
    !isString(symbol) ||
    !isNullableString(state) ||
    !isBoolean(changed) ||
    !isNullableInteger(version) ||
    !isNullableString(updatedAt) ||
    !isNullableString(blockingCode)
  ) {
    return { ok: false };
  }

  return {
    ok: true,
    data: {
      accepted,
      environment,
      symbol,
      state,
      changed,
      version,
      updated_at: updatedAt,
      blocking_code: blockingCode,
    },
  };
}
