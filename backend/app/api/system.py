from __future__ import annotations

import copy
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.domain.objects import Kind

router = APIRouter(prefix="/api/v1")

KINDS: list[str] = [
    "class",
    "relation_type",
    "attribute_type",
    "instance",
    "relation",
    "attribute_value",
    "source_ref",
]

READ_PATHS: dict[str, set[str]] = {
    "/api/v1/health": {"get"},
    "/api/v1/capabilities": {"get"},
    "/api/v1/projects": {"get"},
    "/api/v1/projects/{project_id}": {"get"},
    "/api/v1/projects/{project_id}/state": {"get"},
    "/api/v1/projects/{project_id}/schema": {"get"},
    "/api/v1/projects/{project_id}/objects": {"get"},
    "/api/v1/projects/{project_id}/objects/{object_id}": {"get"},
    "/api/v1/projects/{project_id}/neighborhood": {"get"},
    "/api/v1/projects/{project_id}/instances": {"get"},
    "/api/v1/projects/{project_id}/references": {"get"},
}


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "app": "graphloom", "version": "0.2.0"}


@router.get("/capabilities")
def capabilities() -> dict:
    return {
        "api_version": "v1",
        "read_only": False,
        "limits": {
            "page_size_default": 100,
            "page_size_max": 500,
            "query_objects_max": 500,
            "neighborhood_depth_max": 2,
            "body_bytes_max": 10 * 1024 * 1024,
        },
        "kinds": KINDS,
        "value_types": ["string", "number", "boolean", "date", "uri"],
        "evidence_states": [
            "discovered",
            "bibliographically_verified",
            "abstract_preview_verified",
            "full_text_verified",
            "secondary_only",
            "unverified",
        ],
    }


@router.get("/openapi.reader.json", include_in_schema=False)
def reader_openapi(request: Request) -> JSONResponse:
    spec = copy.deepcopy(request.app.openapi())
    paths: dict[str, Any] = {}
    for path, methods in READ_PATHS.items():
        source = spec.get("paths", {}).get(path)
        if not source:
            continue
        filtered = {
            method: operation
            for method, operation in source.items()
            if method.lower() in methods
        }
        if filtered:
            paths[path] = filtered
    spec["paths"] = paths
    spec["info"]["title"] = "Graphloom reader API"
    spec["info"]["description"] = (
        "Read-only Graphloom surface for consuming agents. Batch editing, project "
        "creation, and layout operations are omitted."
    )
    spec["x-graphloom-read-only"] = True
    return JSONResponse(spec)
