from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .live_control_plane_models import (
    LiveControlPlaneError,
    LivePositionResponse,
    LiveProtectiveOrdersCurrentResponse,
    LiveReadinessResponse,
    LiveRecoveryStatusResponse,
    LiveSafetyStatusResponse,
)
from .live_control_plane_service import LiveControlPlaneHTTPError, LiveControlPlaneService


def get_live_control_plane_service() -> LiveControlPlaneService:
    return LiveControlPlaneService()


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
