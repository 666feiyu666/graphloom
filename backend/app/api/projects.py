from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ProjectDep, StoreDep
from app.api.errors import ApiError
from app.api.schemas import LayoutUpdate, ProjectCreate, ProjectUpdate

router = APIRouter(prefix="/api/v1")


@router.get("/projects")
def list_projects(store: StoreDep) -> dict:
    return {"projects": store.list_projects()}


@router.post("/projects", status_code=201)
def create_project(payload: ProjectCreate, store: StoreDep) -> dict:
    return store.create_project(payload.name, payload.description)


@router.get("/projects/{project_id}")
def get_project(project: ProjectDep) -> dict:
    return project


@router.patch("/projects/{project_id}")
def update_project(payload: ProjectUpdate, project: ProjectDep, store: StoreDep) -> dict:
    if payload.name is None and payload.description is None:
        raise ApiError(422, "no_updates", "Provide a name or a description to update")
    return store.rename_project(
        project["id"],
        name=payload.name,
        description=payload.description,
    )


@router.delete("/projects/{project_id}")
def delete_project(project: ProjectDep, store: StoreDep) -> dict:
    store.delete_project(project["id"])
    return {"project_id": project["id"], "deleted": True}


@router.get("/projects/{project_id}/layout")
def get_layout(project: ProjectDep, store: StoreDep) -> dict:
    return store.get_layout(project["id"])


@router.put("/projects/{project_id}/layout")
def put_layout(payload: LayoutUpdate, project: ProjectDep, store: StoreDep) -> dict:
    return store.save_layout(project["id"], payload.data)
