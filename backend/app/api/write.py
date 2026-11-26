from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body
from pydantic import ValidationError

from app.api.deps import ProjectDep, StoreDep
from app.domain.operations import (
    BatchEnvelope,
    OperationError,
    apply_operations,
)
from app.domain.validation import validate_state

router = APIRouter(prefix="/api/v1")


@router.post("/projects/{project_id}/batch")
def apply_batch(
    project: ProjectDep,
    store: StoreDep,
    payload: Annotated[dict, Body(...)],
) -> dict:
    try:
        envelope = BatchEnvelope.model_validate(payload)
    except ValidationError as exc:
        raise OperationError(
            [
                {
                    "code": "invalid_operation",
                    "message": "The batch payload is malformed",
                    "details": exc.errors(include_url=False, include_context=False),
                }
            ]
        ) from exc

    base = store.read_state(project["id"])
    applied = apply_operations(base, envelope.operations)
    validation = validate_state(applied.state, deleted_ids=applied.deleted_ids)
    errors = applied.errors + validation.errors
    if errors:
        only_dependencies = all(error.get("code") == "delete_dependency" for error in errors)
        raise OperationError(
            errors,
            status_code=409 if only_dependencies else 422,
            code="dependency_conflict" if only_dependencies else "invalid_batch",
        )

    changed = bool(applied.added_ids or applied.updated_ids or applied.deleted_ids)
    if changed:
        meta = store.save_state(project["id"], applied.state)
        version = meta["version"]
    else:
        version = project["version"]

    return {
        "project_id": project["id"],
        "version": version,
        "changed": changed,
        "added_ids": sorted(applied.added_ids),
        "updated_ids": sorted(applied.updated_ids),
        "deleted_ids": sorted(applied.deleted_ids),
        "id_map": applied.id_map,
        "warnings": validation.warnings,
    }
