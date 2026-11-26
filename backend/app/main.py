from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.errors import error_response, install_error_handlers
from app.api.projects import router as projects_router
from app.api.read import router as read_router
from app.api.system import router as system_router
from app.api.write import router as write_router
from app.config import Settings, get_settings
from app.storage import DataStore

def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title="Graphloom",
        version="0.2.0",
        description=(
            "Local single-user ontology and knowledge-graph workbench. The saved graph is "
            "exposed read-only to a consuming agent."
        ),
        docs_url="/api/v1/docs",
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.state.settings = settings
    app.state.store = DataStore(settings.resolved_data_dir)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.middleware("http")
    async def body_limit_middleware(request: Request, call_next):
        raw_length = request.headers.get("content-length")
        if raw_length:
            try:
                length = int(raw_length)
            except ValueError:
                length = 0
            if length > settings.max_body_bytes:
                return error_response(
                    request,
                    413,
                    "payload_too_large",
                    "Request body exceeds the configured limit",
                    {"max_body_bytes": settings.max_body_bytes},
                )
        return await call_next(request)

    install_error_handlers(app)

    app.include_router(system_router)
    app.include_router(projects_router)
    app.include_router(read_router)
    app.include_router(write_router)

    dist = Path(settings.frontend_dist)
    if (dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")
    else:

        @app.get("/", include_in_schema=False)
        def root() -> dict:
            return {
                "app": "graphloom",
                "api": "/api/v1",
                "docs": "/api/v1/docs",
                "reader_openapi": "/api/v1/openapi.reader.json",
            }

    return app


app = create_app()
