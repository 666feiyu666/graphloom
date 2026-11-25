from __future__ import annotations

import copy
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import DbSession, OwnerDep, CredentialDep
from app.api.errors import ApiError
from app.api.schemas import CredentialCreate
from app.auth import (
    create_credential,
    credential_project_ids,
    revoke_credential,
)
from app.domain.objects import Kind
from app.storage.models import Credential, Project

router = APIRouter(prefix="/api/v1")

READ_OPERATIONS = [
    "read_project",
    "read_state",
    "read_schema",
    "read_objects",
    "read_object",
    "query",
    "read_revisions",
    "read_diff",
    "read_snapshots",
    "export",
]
OWNER_OPERATIONS = READ_OPERATIONS + [
    "create_project",
    "prepare_change_set",
    "commit_change_set",
    "create_snapshot",
    "restore_snapshot",
    "import_preview",
    "save_layout",
    "manage_credentials",
]

KINDS: list[str] = [
    "class",
    "relation_type",
    "attribute_type",
    "instance",
    "relation",
    "attribute_value",
    "source_ref",
]

READER_OPENAPI_PATHS: dict[str, set[str]] = {
    "/api/v1/health": {"get"},
    "/api/v1/capabilities": {"get"},
    "/api/v1/projects": {"get"},
    "/api/v1/projects/{project_id}": {"get"},
    "/api/v1/projects/{project_id}/state": {"get"},
    "/api/v1/projects/{project_id}/schema": {"get"},
    "/api/v1/projects/{project_id}/objects": {"get"},
    "/api/v1/projects/{project_id}/objects/{object_id}": {"get"},
    "/api/v1/projects/{project_id}/query": {"post"},
    "/api/v1/projects/{project_id}/revisions": {"get"},
    "/api/v1/projects/{project_id}/diff": {"get"},
    "/api/v1/projects/{project_id}/snapshots": {"get"},
    "/api/v1/projects/{project_id}/export": {"get"},
}


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "app": "graphloom", "version": "0.1.0"}


@router.get("/capabilities")
def capabilities(credential: CredentialDep) -> dict:
    is_owner = credential.role == "owner"
    return {
        "role": credential.role,
        "actor": credential.label,
        "read_only": not is_owner,
        "api_version": "v1",
        "format_versions": {"native_json": [1], "rdf_turtle": [1]},
        "limits": {
            "page_size_default": 100,
            "page_size_max": 500,
            "query_objects_max": 500,
            "neighborhood_depth_max": 2,
            "body_bytes_max": 10 * 1024 * 1024,
        },
        "kinds": KINDS,
        "operations": OWNER_OPERATIONS if is_owner else READ_OPERATIONS,
        "project_scope": (
            "all"
            if is_owner
            else sorted(credential_project_ids(credential))
        ),
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


def _credential_dict(credential: Credential, *, include_token: str | None = None) -> dict:
    payload = {
        "id": credential.id,
        "role": credential.role,
        "label": credential.label,
        "project_ids": sorted(credential_project_ids(credential)),
        "created_at": credential.created_at.isoformat() if credential.created_at else None,
        "revoked_at": credential.revoked_at.isoformat() if credential.revoked_at else None,
    }
    if include_token is not None:
        payload["token"] = include_token
        payload["token_notice"] = "This token is shown once; store it before leaving this page."
    return payload


@router.post("/credentials")
def create_reader_credential(
    payload: CredentialCreate,
    session: DbSession,
    credential: OwnerDep,
) -> dict:
    requested = [str(item) for item in payload.project_ids]
    if requested:
        known = set(
            session.scalars(select(Project.id).where(Project.id.in_(requested))).all()
        )
        missing = sorted(set(requested) - known)
        if missing:
            raise ApiError(
                422,
                "unknown_project",
                "Reader credentials can only be scoped to existing projects",
                {"project_ids": missing},
            )
    created, token = create_credential(
        session,
        role="reader",
        label=payload.label,
        project_ids=requested,
    )
    session.commit()
    return _credential_dict(created, include_token=token)


@router.get("/credentials")
def list_credentials(session: DbSession, credential: OwnerDep) -> dict:
    rows = session.scalars(select(Credential).order_by(Credential.created_at)).all()
    return {"credentials": [_credential_dict(row) for row in rows]}


@router.delete("/credentials/{credential_id}")
def delete_credential(
    credential_id: str,
    session: DbSession,
    credential: OwnerDep,
) -> dict:
    row = session.get(Credential, credential_id)
    if row is None:
        raise ApiError(404, "credential_not_found", "Credential does not exist")
    if row.id == credential.id:
        raise ApiError(422, "cannot_revoke_self", "The active owner credential cannot revoke itself")
    revoke_credential(session, row)
    session.commit()
    return _credential_dict(row)


@router.get("/openapi.reader.json", include_in_schema=False)
def reader_openapi(request: Request) -> JSONResponse:
    spec = copy.deepcopy(request.app.openapi())
    paths: dict[str, Any] = {}
    for path, methods in READER_OPENAPI_PATHS.items():
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
        "Read-only Graphloom surface for consuming agents. Owner editing, import, "
        "restoration, project creation, layout, and credential operations are omitted."
    )
    spec["x-graphloom-read-only"] = True
    return JSONResponse(spec)
