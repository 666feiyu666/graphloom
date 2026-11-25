from __future__ import annotations

import json
from uuid import UUID, uuid4

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CredentialDep, DbSession, OwnerDep, OwnerProjectDep, ProjectDep
from app.api.errors import ApiError
from app.api.schemas import LayoutUpdate, ProjectCreate
from app.auth import credential_project_ids
from app.domain.changesets import current_state
from app.domain.graph import empty_state
from app.storage.models import Layout, Project, ProjectState

router = APIRouter(prefix="/api/v1")


def project_summary(project: Project, state=None) -> dict:
    counts = {"objects": 0, "classes": 0, "instances": 0, "relations": 0, "assertions": 0}
    if state is not None:
        counts["objects"] = len(state.objects)
        for obj in state.objects:
            if obj.kind == "class":
                counts["classes"] += 1
            elif obj.kind == "instance":
                counts["instances"] += 1
            elif obj.kind == "relation":
                counts["relations"] += 1
                counts["assertions"] += 1
            elif obj.kind == "attribute_value":
                counts["assertions"] += 1
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "current_revision": project.current_revision,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        "counts": counts,
    }


@router.get("/projects")
def list_projects(session: DbSession, credential: CredentialDep) -> dict:
    query = select(Project).order_by(Project.created_at)
    if credential.role == "reader":
        allowed = credential_project_ids(credential)
        query = query.where(Project.id.in_(sorted(allowed)))
    rows = session.scalars(query).all()
    return {"projects": [project_summary(row) for row in rows]}


@router.post("/projects", status_code=201)
def create_project(
    payload: ProjectCreate,
    session: DbSession,
    credential: OwnerDep,
) -> dict:
    project_id = str(uuid4())
    project = Project(
        id=project_id,
        name=payload.name,
        description=payload.description,
        current_revision=0,
    )
    session.add(project)
    session.add(
        ProjectState(
            project_id=project_id,
            revision=0,
            state_json=empty_state(UUID(project_id), 0).model_dump_json(),
        )
    )
    session.commit()
    return project_summary(project, empty_state(UUID(project_id), 0))


@router.get("/projects/{project_id}")
def get_project(project: ProjectDep, session: DbSession) -> dict:
    return project_summary(project, current_state(session, project))


@router.get("/projects/{project_id}/layout")
def get_layout(project: OwnerProjectDep, session: DbSession) -> dict:
    row = session.get(Layout, project.id)
    if row is None:
        return {"project_id": project.id, "version": 0, "data": {}}
    return {
        "project_id": project.id,
        "version": row.version,
        "data": json.loads(row.data_json),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.put("/projects/{project_id}/layout")
def put_layout(payload: LayoutUpdate, project: OwnerProjectDep, session: DbSession) -> dict:
    row = session.get(Layout, project.id)
    current_version = row.version if row is not None else 0
    if payload.expected_version != current_version:
        raise ApiError(
            409,
            "layout_conflict",
            "Layout was changed by another client",
            {"expected_version": payload.expected_version, "current_version": current_version},
        )
    if row is None:
        row = Layout(project_id=project.id, version=1, data_json="{}")
        session.add(row)
    else:
        row.version = current_version + 1
    row.data_json = json.dumps(payload.data, ensure_ascii=False)
    session.commit()
    return {"project_id": project.id, "version": row.version, "data": payload.data}
