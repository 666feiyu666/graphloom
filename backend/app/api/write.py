from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Header
from sqlalchemy import select

from app.api.deps import DbSession, OwnerDep, OwnerProjectDep
from app.api.errors import ApiError
from app.api.schemas import (
    ChangeSetEnvelope,
    CommitRequest,
    RestorePreviewRequest,
    SnapshotCreate,
)
from app.domain.changesets import (
    change_set_dict,
    commit_change_set,
    prepare_change_set,
    prepare_replacement,
    state_at_revision,
)
from app.exports.native import parse_native_import
from app.storage.models import ChangeSet, Snapshot

router = APIRouter(prefix="/api/v1")


def _get_change_set(session: DbSession, project_id: str, change_set_id: str) -> ChangeSet:
    row = session.get(ChangeSet, change_set_id)
    if row is None or row.project_id != project_id:
        raise ApiError(404, "change_set_not_found", "Change set does not exist")
    return row


@router.post("/projects/{project_id}/change-sets", status_code=201)
def prepare(
    payload: ChangeSetEnvelope,
    project: OwnerProjectDep,
    session: DbSession,
    credential: OwnerDep,
) -> dict:
    change_set = prepare_change_set(session, project, payload, credential.label)
    session.commit()
    return change_set_dict(change_set)


@router.get("/projects/{project_id}/change-sets/{change_set_id}")
def get_change_set(
    project: OwnerProjectDep,
    session: DbSession,
    change_set_id: str,
) -> dict:
    return change_set_dict(_get_change_set(session, project.id, change_set_id))


@router.post("/projects/{project_id}/change-sets/{change_set_id}/commit")
def commit(
    payload: CommitRequest,
    project: OwnerProjectDep,
    session: DbSession,
    credential: OwnerDep,
    change_set_id: str,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict:
    change_set = _get_change_set(session, project.id, change_set_id)
    return commit_change_set(
        session,
        project,
        change_set,
        expected_revision=payload.expected_revision,
        idempotency_key=idempotency_key,
        actor=credential.label,
    )


@router.post(
    "/projects/{project_id}/revisions/{revision}/restore-preview", status_code=201
)
def restore_revision_preview(
    payload: RestorePreviewRequest,
    project: OwnerProjectDep,
    session: DbSession,
    credential: OwnerDep,
    revision: int,
) -> dict:
    state = state_at_revision(session, project, revision)
    if state is None:
        raise ApiError(
            404,
            "revision_not_found",
            "The requested revision does not exist for this project",
            {"revision": revision, "current_revision": project.current_revision},
        )
    reason = payload.reason or f"Restore revision {revision}"
    change_set = prepare_replacement(
        session,
        project,
        state.model_copy(deep=True),
        actor=credential.label,
        reason=reason,
        source={"revision": revision},
    )
    session.commit()
    return change_set_dict(change_set)


@router.post("/projects/{project_id}/snapshots", status_code=201)
def create_snapshot(
    payload: SnapshotCreate,
    project: OwnerProjectDep,
    session: DbSession,
) -> dict:
    revision = project.current_revision if payload.revision is None else payload.revision
    if revision < 0 or revision > project.current_revision:
        raise ApiError(
            422,
            "unknown_revision",
            "Snapshot must point at an existing revision",
            {"revision": revision, "current_revision": project.current_revision},
        )
    snapshot = Snapshot(
        id=str(uuid4()),
        project_id=project.id,
        name=payload.name,
        revision=revision,
        created_at=datetime.now(timezone.utc),
    )
    session.add(snapshot)
    session.commit()
    return {
        "id": snapshot.id,
        "project_id": project.id,
        "name": snapshot.name,
        "revision": snapshot.revision,
        "created_at": snapshot.created_at.isoformat(),
    }


@router.post("/projects/{project_id}/snapshots/{snapshot_id}/restore-preview", status_code=201)
def restore_preview(
    payload: RestorePreviewRequest,
    project: OwnerProjectDep,
    session: DbSession,
    credential: OwnerDep,
    snapshot_id: str,
) -> dict:
    snapshot = session.get(Snapshot, snapshot_id)
    if snapshot is None or snapshot.project_id != project.id:
        raise ApiError(404, "snapshot_not_found", "Snapshot does not exist")
    state = state_at_revision(session, project, snapshot.revision)
    if state is None:
        raise ApiError(
            404,
            "revision_not_found",
            "The snapshot's revision is no longer available",
        )
    reason = payload.reason or f"Restore snapshot '{snapshot.name}'"
    change_set = prepare_replacement(
        session,
        project,
        state.model_copy(deep=True),
        actor=credential.label,
        reason=reason,
        source={"snapshot_id": snapshot.id, "revision": snapshot.revision},
    )
    session.commit()
    return change_set_dict(change_set)


@router.post("/projects/{project_id}/import-preview", status_code=201)
def import_preview(
    project: OwnerProjectDep,
    session: DbSession,
    credential: OwnerDep,
    payload: dict = Body(...),
) -> dict:
    state, source = parse_native_import(payload, project.id)
    reason = "Import replacement from {project} at revision {revision}".format(
        project=source.get("project_name") or source.get("project_id") or "unknown project",
        revision=source.get("revision"),
    )
    change_set = prepare_replacement(
        session,
        project,
        state,
        actor=credential.label,
        reason=reason,
        source=source,
    )
    session.commit()
    return change_set_dict(change_set)
