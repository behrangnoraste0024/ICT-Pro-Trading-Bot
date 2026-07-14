from __future__ import annotations

from fastapi import FastAPI

from .live_control_plane_routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="ICT Pro Trading Bot Live Control Plane", version="2.85.0")
    app.include_router(router)
    return app


app = create_app()
