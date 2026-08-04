from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .kill_switch_control_models import (
    KillSwitchControlResponse,
    KillSwitchEngageRequest,
    KillSwitchReleaseRequest,
)
from .kill_switch_control_service import KillSwitchControlService, KillSwitchHTTPError
from .live_control_plane_models import (
    LiveControlPlaneError,
    LiveExecutionPermitStatusResponse,
    LivePositionResponse,
    LiveProtectiveOrdersCurrentResponse,
    LiveReadinessResponse,
    LiveRecoveryStatusResponse,
    LiveSafetyStatusResponse,
    OperatorStatusResponse,
    ExchangeOrderReadResponse,
    ExecutionIntentListResponse,
    ExecutionIntentReadResponse,
    PersistenceStatusResponse,
    ProtectivePairEventsResponse,
    ProtectivePairOrdersResponse,
    ProtectivePairReadResponse,
)
from .live_control_plane_service import LiveControlPlaneHTTPError, LiveControlPlaneService
from .live_execution_permit_status_service import (
    LiveExecutionPermitStatusHTTPError,
    LiveExecutionPermitStatusService,
)
from .operator_status_service import OperatorStatusService
from .persistence_read_model_service import PersistenceReadModelHTTPError, PersistenceReadModelService
from .supervised_recovery_models import SupervisedRecoveryRequest, SupervisedRecoveryResponse
from .supervised_recovery_service import SupervisedRecoveryHTTPError, SupervisedRecoveryService


def get_live_control_plane_service() -> LiveControlPlaneService:
    return LiveControlPlaneService()


def get_persistence_read_model_service() -> PersistenceReadModelService:
    return PersistenceReadModelService()


def get_supervised_recovery_service() -> SupervisedRecoveryService:
    return SupervisedRecoveryService()


def get_kill_switch_control_service() -> KillSwitchControlService:
    return KillSwitchControlService()


def get_operator_status_service() -> OperatorStatusService:
    return OperatorStatusService()


def get_live_execution_permit_status_service() -> LiveExecutionPermitStatusService:
    return LiveExecutionPermitStatusService()


router = APIRouter(prefix="/api/v1/live", tags=["live-control-plane"])


def _safe_call(callback):
    try:
        return callback()
    except LiveControlPlaneHTTPError as exc:
        error = LiveControlPlaneError(code=exc.code, message=exc.message)
        payload = error.model_dump() if hasattr(error, "model_dump") else error.dict()
        raise HTTPException(status_code=exc.status_code, detail=payload) from exc
    except Exception as exc:
        error = LiveControlPlaneError(code="LIVE_CONTROL_PLANE_UNAVAILABLE", message="Live control plane state is unavailable.")
        payload = error.model_dump() if hasattr(error, "model_dump") else error.dict()
        raise HTTPException(status_code=503, detail=payload) from exc


def _safe_persistence_call(callback):
    try:
        return callback()
    except PersistenceReadModelHTTPError as exc:
        error = LiveControlPlaneError(code=exc.code, message=exc.message)
        payload = error.model_dump() if hasattr(error, "model_dump") else error.dict()
        raise HTTPException(status_code=exc.status_code, detail=payload) from exc
    except Exception as exc:
        error = LiveControlPlaneError(code="PERSISTENCE_UNAVAILABLE", message="Persistence read model is unavailable.")
        payload = error.model_dump() if hasattr(error, "model_dump") else error.dict()
        raise HTTPException(status_code=503, detail=payload) from exc


def _safe_recovery_call(callback):
    try:
        return callback()
    except SupervisedRecoveryHTTPError as exc:
        error = LiveControlPlaneError(code=exc.code, message=exc.message)
        payload = error.model_dump() if hasattr(error, "model_dump") else error.dict()
        raise HTTPException(status_code=exc.status_code, detail=payload) from exc
    except Exception as exc:
        error = LiveControlPlaneError(code="RECOVERY_UNAVAILABLE", message="Supervised recovery is unavailable.")
        payload = error.model_dump() if hasattr(error, "model_dump") else error.dict()
        raise HTTPException(status_code=503, detail=payload) from exc


def _safe_kill_switch_call(callback):
    try:
        return callback()
    except KillSwitchHTTPError as exc:
        error = LiveControlPlaneError(code=exc.code, message=exc.message)
        payload = error.model_dump() if hasattr(error, "model_dump") else error.dict()
        raise HTTPException(status_code=exc.status_code, detail=payload) from exc
    except Exception as exc:
        error = LiveControlPlaneError(code="KILL_SWITCH_UNAVAILABLE", message="Kill switch control is unavailable.")
        payload = error.model_dump() if hasattr(error, "model_dump") else error.dict()
        raise HTTPException(status_code=503, detail=payload) from exc


def _safe_operator_status_call(callback):
    try:
        return callback()
    except Exception as exc:
        error = LiveControlPlaneError(code="OPERATOR_STATUS_UNAVAILABLE", message="Operator status is unavailable.")
        payload = error.model_dump() if hasattr(error, "model_dump") else error.dict()
        raise HTTPException(status_code=503, detail=payload) from exc


def _safe_permit_status_call(callback):
    try:
        return callback()
    except LiveExecutionPermitStatusHTTPError as exc:
        error = LiveControlPlaneError(code=exc.code, message=exc.message)
        payload = error.model_dump() if hasattr(error, "model_dump") else error.dict()
        raise HTTPException(status_code=exc.status_code, detail=payload) from exc
    except Exception as exc:
        error = LiveControlPlaneError(code="PERMIT_STATUS_UNAVAILABLE", message="Live execution permit status is unavailable.")
        payload = error.model_dump() if hasattr(error, "model_dump") else error.dict()
        raise HTTPException(status_code=503, detail=payload) from exc


@router.get("/safety/status", response_model=LiveSafetyStatusResponse)
def safety_status(service: LiveControlPlaneService = Depends(get_live_control_plane_service)):
    return _safe_call(service.safety_status)


@router.get("/readiness", response_model=LiveReadinessResponse)
def readiness(service: LiveControlPlaneService = Depends(get_live_control_plane_service)):
    return _safe_call(service.readiness)


@router.get("/positions/{symbol}", response_model=LivePositionResponse)
def position(symbol: str, service: LiveControlPlaneService = Depends(get_live_control_plane_service)):
    return _safe_call(lambda: service.position(symbol))


@router.get("/protective-orders/current", response_model=LiveProtectiveOrdersCurrentResponse)
def protective_orders_current(service: LiveControlPlaneService = Depends(get_live_control_plane_service)):
    return _safe_call(service.protective_orders_current)


@router.get("/recovery/status", response_model=LiveRecoveryStatusResponse)
def recovery_status(service: LiveControlPlaneService = Depends(get_live_control_plane_service)):
    return _safe_call(service.recovery_status)


@router.post("/recovery/run", response_model=SupervisedRecoveryResponse)
def run_recovery(
    request: SupervisedRecoveryRequest,
    service: SupervisedRecoveryService = Depends(get_supervised_recovery_service),
):
    return _safe_recovery_call(lambda: service.run(request))


@router.get("/kill-switch/status", response_model=KillSwitchControlResponse)
def kill_switch_status(service: KillSwitchControlService = Depends(get_kill_switch_control_service)):
    return _safe_kill_switch_call(service.status)


@router.get("/operator/status", response_model=OperatorStatusResponse)
def operator_status(service: OperatorStatusService = Depends(get_operator_status_service)):
    return _safe_operator_status_call(service.status)


@router.post("/kill-switch/engage", response_model=KillSwitchControlResponse)
def engage_kill_switch(
    request: KillSwitchEngageRequest,
    service: KillSwitchControlService = Depends(get_kill_switch_control_service),
):
    return _safe_kill_switch_call(service.engage)


@router.post("/kill-switch/release", response_model=KillSwitchControlResponse)
def release_kill_switch(
    request: KillSwitchReleaseRequest,
    service: KillSwitchControlService = Depends(get_kill_switch_control_service),
):
    return _safe_kill_switch_call(service.release)


@router.get("/persistence/status", response_model=PersistenceStatusResponse)
def persistence_status(service: PersistenceReadModelService = Depends(get_persistence_read_model_service)):
    return _safe_persistence_call(service.status)


@router.get("/execution-intents", response_model=ExecutionIntentListResponse)
def execution_intents(
    limit: str = Query(default="50"),
    offset: str = Query(default="0"),
    service: PersistenceReadModelService = Depends(get_persistence_read_model_service),
):
    return _safe_persistence_call(lambda: service.execution_intents(limit=limit, offset=offset))


@router.get("/execution-intents/{correlation_id}", response_model=ExecutionIntentReadResponse)
def execution_intent(correlation_id: str, service: PersistenceReadModelService = Depends(get_persistence_read_model_service)):
    return _safe_persistence_call(lambda: service.execution_intent(correlation_id))


@router.get("/protective-pairs/{pair_id}", response_model=ProtectivePairReadResponse)
def protective_pair(pair_id: str, service: PersistenceReadModelService = Depends(get_persistence_read_model_service)):
    return _safe_persistence_call(lambda: service.protective_pair(pair_id))


@router.get("/protective-pairs/{pair_id}/orders", response_model=ProtectivePairOrdersResponse)
def protective_pair_orders(pair_id: str, service: PersistenceReadModelService = Depends(get_persistence_read_model_service)):
    return _safe_persistence_call(lambda: service.protective_pair_orders(pair_id))


@router.get("/protective-pairs/{pair_id}/events", response_model=ProtectivePairEventsResponse)
def protective_pair_events(
    pair_id: str,
    limit: str = Query(default="50"),
    offset: str = Query(default="0"),
    service: PersistenceReadModelService = Depends(get_persistence_read_model_service),
):
    return _safe_persistence_call(lambda: service.protective_pair_events(pair_id, limit=limit, offset=offset))


@router.get("/execution-permits/{permit_id}", response_model=LiveExecutionPermitStatusResponse)
def execution_permit_status(
    permit_id: str,
    service: LiveExecutionPermitStatusService = Depends(get_live_execution_permit_status_service),
):
    return _safe_permit_status_call(lambda: service.status(permit_id))
