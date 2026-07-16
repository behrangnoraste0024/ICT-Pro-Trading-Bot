from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .live_control_plane_routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="ICT Pro Trading Bot Live Control Plane", version="2.89.0")

    @app.exception_handler(RequestValidationError)
    async def sanitized_recovery_validation_error(request: Request, exc: RequestValidationError):
        if request.url.path == "/api/v1/live/recovery/run":
            return JSONResponse(
                status_code=422,
                content={
                    "accepted": False,
                    "blocking_code": "INVALID_REQUEST",
                    "message": "Request validation failed.",
                },
            )
        return await request_validation_exception_handler(request, exc)

    app.include_router(router)
    return app


app = create_app()
