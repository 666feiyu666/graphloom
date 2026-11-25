from __future__ import annotations

import logging
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.errors import error_response, install_error_handlers
from app.api.projects import router as projects_router
from app.api.read import router as read_router
from app.api.system import router as system_router
from app.api.write import router as write_router
from app.config import Settings, get_settings
from app.storage.db import make_engine, make_session_factory, run_migrations

logger = logging.getLogger("graphloom")


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = monotonic()
        with self._lock:
            events = self._events[key]
            boundary = now - self.window_seconds
            while events and events[0] < boundary:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        run_migrations(settings.db_path)
        yield
        application.state.engine.dispose()

    app = FastAPI(
        title="Graphloom",
        version="0.1.0",
        description=(
            "Local ontology and knowledge-graph workbench. The owner editing surface and "
            "the reader-facing graph contract are intentionally separate."
        ),
        lifespan=lifespan,
        docs_url="/api/v1/docs",
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.state.settings = settings
    app.state.engine = make_engine(settings.db_path)
    app.state.session_factory = make_session_factory(app.state.engine)
    limiter = SlidingWindowLimiter(settings.rate_limit_per_minute)
    app.state.rate_limiter = limiter

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

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if request.url.path == "/api/v1/health":
            return await call_next(request)
        key = request.headers.get("authorization") or (
            request.client.host if request.client else "anonymous"
        )
        if not limiter.allow(key):
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": "60"},
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many local requests; retry shortly",
                        "details": {"limit_per_minute": settings.rate_limit_per_minute},
                    },
                    "request_id": getattr(request.state, "request_id", ""),
                },
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
