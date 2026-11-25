from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.changesets import ChangeSetError
from app.domain.queries import QueryError
from app.exports.native import ImportValidationError

logger = logging.getLogger("graphloom")


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    if value:
        return value
    value = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = value
    return value


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {"code": code, "message": message, "details": details or {}},
            "request_id": request_id(request),
        },
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(request, exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(ChangeSetError)
    async def _change_set_error(request: Request, exc: ChangeSetError) -> JSONResponse:
        return error_response(
            request, exc.status_code, exc.code, exc.message, exc.details
        )

    @app.exception_handler(QueryError)
    async def _query_error(request: Request, exc: QueryError) -> JSONResponse:
        return error_response(request, 422, exc.code, exc.message, exc.details)

    @app.exception_handler(ImportValidationError)
    async def _import_error(request: Request, exc: ImportValidationError) -> JSONResponse:
        return error_response(request, 422, "invalid_import", exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            request,
            422,
            "invalid_request",
            "Request validation failed",
            {"errors": jsonable_encoder(exc.errors())},
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server error", exc_info=exc)
        return error_response(
            request,
            500,
            "internal_error",
            "Unexpected server error",
        )
