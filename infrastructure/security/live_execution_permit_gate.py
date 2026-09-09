from __future__ import annotations

import os
from typing import Callable
from uuid import UUID, uuid4

from infrastructure.observability.operational_metrics import OperationalCounterRegistry
from infrastructure.persistence.live_execution_authorization_policy import LiveExecutionAuthorizationPolicy
from infrastructure.persistence.live_execution_permit_persistence import LiveExecutionPermitPersistence, LiveExecutionPermitPersistenceError
from infrastructure.security.live_execution_request_fingerprint import LiveExecutionRequestFingerprint
from models.live_execution_authorization import LiveExecutionOperation
from models.live_execution_permit import PERMIT_ENVIRONMENT, PERMIT_SYMBOL, LiveExecutionPermitState
from models.live_execution_permit_enforcement import (
    LiveExecutionPermitConsumptionReceipt,
    LiveExecutionPermitGateError,
    LiveExecutionPermitReference,
)


class LiveExecutionPermitGate:
    def __init__(
        self,
        authorization_policy: LiveExecutionAuthorizationPolicy | None = None,
        permit_persistence_factory: Callable[..., LiveExecutionPermitPersistence] = LiveExecutionPermitPersistence,
        correlation_id_provider: Callable[[], object] = uuid4,
        env: dict[str, str] | None = None,
        operational_counter_registry: OperationalCounterRegistry | None = None,
    ) -> None:
        self.env = os.environ if env is None else env
        self.authorization_policy = authorization_policy or LiveExecutionAuthorizationPolicy(
            env=self.env,
            operational_counter_registry=operational_counter_registry,
        )
        self.permit_persistence_factory = permit_persistence_factory
        self.correlation_id_provider = correlation_id_provider

    def authorize_and_consume(
        self,
        *,
        operation: LiveExecutionOperation,
        fingerprint: LiveExecutionRequestFingerprint,
        permit_reference: LiveExecutionPermitReference,
        confirmation_verified: bool,
        credentials_configured: bool,
        runtime_config_path: str,
        current_pair_id: str | None = None,
    ) -> LiveExecutionPermitConsumptionReceipt:
        reference = self._validate_reference(permit_reference)
        if not isinstance(operation, LiveExecutionOperation):
            raise LiveExecutionPermitGateError("PERMIT_REQUEST_INVALID")
        if not isinstance(fingerprint, LiveExecutionRequestFingerprint):
            raise LiveExecutionPermitGateError("PERMIT_REQUEST_INVALID")
        if fingerprint.operation != operation or fingerprint.environment != PERMIT_ENVIRONMENT or fingerprint.symbol != PERMIT_SYMBOL:
            raise LiveExecutionPermitGateError("PERMIT_REQUEST_INVALID")
        if type(confirmation_verified) is not bool or type(credentials_configured) is not bool:
            raise LiveExecutionPermitGateError("PERMIT_REQUEST_INVALID")
        decision = self.authorization_policy.authorize(
            operation,
            environment=PERMIT_ENVIRONMENT,
            symbol=PERMIT_SYMBOL,
            confirmation_verified=confirmation_verified,
            credentials_configured=credentials_configured,
            runtime_config_path=runtime_config_path,
            current_pair_id=current_pair_id,
        )
        if not decision.allowed:
            raise LiveExecutionPermitGateError(decision.code)

        persistence = None
        consumed = None
        try:
            persistence = self.permit_persistence_factory(env=self.env)
            persistence.ensure_available()
            correlation_id = self.correlation_id_provider()
            if not isinstance(correlation_id, UUID):
                raise LiveExecutionPermitGateError("PERMIT_REQUEST_INVALID")
            consumed = persistence.consume(
                permit_id=reference.permit_id,
                expected_version=reference.expected_version,
                expected_operation=operation,
                expected_environment=fingerprint.environment,
                expected_symbol=fingerprint.symbol,
                expected_subject_type=fingerprint.subject_type,
                expected_subject_id=fingerprint.subject_id,
                expected_request_fingerprint=fingerprint.request_fingerprint,
                consumption_correlation_id=correlation_id,
            )
            if consumed.state != LiveExecutionPermitState.CONSUMED:
                raise LiveExecutionPermitGateError("PERMIT_CONSUMED_NO_TRANSPORT", permit_consumed=True)
            if (
                consumed.permit_id != reference.permit_id
                or consumed.operation != operation
                or consumed.environment != fingerprint.environment
                or consumed.symbol != fingerprint.symbol
                or consumed.subject_type != fingerprint.subject_type
                or consumed.subject_id != fingerprint.subject_id
                or consumed.request_fingerprint != fingerprint.request_fingerprint
                or consumed.consumption_correlation_id != correlation_id
                or consumed.version != reference.expected_version + 1
                or consumed.consumed_at is None
            ):
                raise LiveExecutionPermitGateError("PERMIT_CONSUMED_NO_TRANSPORT", permit_consumed=True)
            receipt = LiveExecutionPermitConsumptionReceipt(
                permit_id=consumed.permit_id,
                operation=operation,
                environment=consumed.environment,
                symbol=consumed.symbol,
                subject_type=consumed.subject_type,
                subject_id=consumed.subject_id,
                request_fingerprint=consumed.request_fingerprint,
                consumption_correlation_id=correlation_id,
                previous_version=reference.expected_version,
                consumed_version=consumed.version,
                consumed_at=consumed.consumed_at,
            )
        except LiveExecutionPermitGateError:
            raise
        except LiveExecutionPermitPersistenceError as exc:
            raise LiveExecutionPermitGateError(exc.code) from None
        except Exception:
            raise LiveExecutionPermitGateError("PERMIT_GATE_UNAVAILABLE") from None
        finally:
            if persistence is not None:
                try:
                    persistence.close()
                except Exception:
                    if consumed is not None:
                        raise LiveExecutionPermitGateError("PERMIT_CONSUMED_NO_TRANSPORT", permit_consumed=True) from None
                    raise LiveExecutionPermitGateError("PERMIT_GATE_UNAVAILABLE") from None
        return receipt

    @staticmethod
    def _validate_reference(reference: object) -> LiveExecutionPermitReference:
        if reference is None:
            raise LiveExecutionPermitGateError("PERMIT_REQUIRED")
        if not isinstance(reference, LiveExecutionPermitReference):
            raise LiveExecutionPermitGateError("PERMIT_REFERENCE_INVALID")
        try:
            return LiveExecutionPermitReference(reference.permit_id, reference.expected_version)
        except Exception:
            raise LiveExecutionPermitGateError("PERMIT_REFERENCE_INVALID") from None
