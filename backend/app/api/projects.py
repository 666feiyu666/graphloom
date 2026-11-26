from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ProjectDep, StoreDep
from app.api.schemas import LayoutUpdate, ProjectCreate

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


@router.get("/projects/{project_id}/layout")
def get_layout(project: ProjectDep, store: StoreDep) -> dict:
    return store.get_layout(project["id"])


@router.put("/projects/{project_id}/layout")
def put_layout(payload: LayoutUpdate, project: ProjectDep, store: StoreDep) -> dict:
    return store.save_layout(project["id"], payload.data)
