from __future__ import annotations

from infrastructure.security.live_execution_request_fingerprint import build_live_execution_request_fingerprint
from models.live_execution_authorization import LiveExecutionOperation
from models.live_execution_permit_enforcement import LiveExecutionUnsignedMutationRequest


def _fingerprint_from_envelope(
    envelope: LiveExecutionUnsignedMutationRequest,
    operation: LiveExecutionOperation,
):
    """Fingerprint the exact immutable request that the client will transmit."""
    if not isinstance(envelope, LiveExecutionUnsignedMutationRequest) or envelope.operation != operation:
        raise ValueError("PERMIT_REQUEST_INVALID")
    return build_live_execution_request_fingerprint(dict(envelope.fingerprint_context))


def build_protective_create_from_final_request(envelope: LiveExecutionUnsignedMutationRequest):
    return _fingerprint_from_envelope(envelope, LiveExecutionOperation.PROTECTIVE_CREATE)


def build_protective_cancel_from_final_request(envelope: LiveExecutionUnsignedMutationRequest):
    return _fingerprint_from_envelope(envelope, LiveExecutionOperation.PROTECTIVE_CANCEL)


def build_lifecycle_create_from_final_request(envelope: LiveExecutionUnsignedMutationRequest):
    return _fingerprint_from_envelope(envelope, LiveExecutionOperation.ORDER_LIFECYCLE_CREATE)


def build_lifecycle_cancel_from_final_request(envelope: LiveExecutionUnsignedMutationRequest):
    return _fingerprint_from_envelope(envelope, LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL)


def build_signed_order_test_create_from_final_request(envelope: LiveExecutionUnsignedMutationRequest):
    return _fingerprint_from_envelope(envelope, LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE)
