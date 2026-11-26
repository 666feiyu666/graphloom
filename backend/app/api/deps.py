from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.api.errors import ApiError
from app.storage import DataStore, ProjectNotFound


def get_store(request: Request) -> DataStore:
    return request.app.state.store


StoreDep = Annotated[DataStore, Depends(get_store)]


def require_project(project_id: str, store: StoreDep) -> dict:
    try:
        return store.get_project(project_id)
    except ProjectNotFound as exc:
        raise ApiError(404, "project_not_found", "Project does not exist") from exc


ProjectDep = Annotated[dict, Depends(require_project)]
