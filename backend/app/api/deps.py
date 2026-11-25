from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.auth import credential_project_ids, resolve_token
from app.storage.models import Credential, Project


def get_db(request: Request):
    factory = request.app.state.session_factory
    session: Session = factory()
    try:
        yield session
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_credential(request: Request, session: DbSession) -> Credential:
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        raise ApiError(401, "missing_credentials", "A bearer token is required")
    token = header.split(" ", 1)[1].strip()
    if not token:
        raise ApiError(401, "missing_credentials", "A bearer token is required")
    credential = resolve_token(session, token)
    if credential is None:
        raise ApiError(401, "invalid_credentials", "The bearer token is not valid")
    return credential


CredentialDep = Annotated[Credential, Depends(get_credential)]


def require_owner(credential: CredentialDep) -> Credential:
    if credential.role != "owner":
        raise ApiError(403, "owner_required", "This operation requires owner credentials")
    return credential


OwnerDep = Annotated[Credential, Depends(require_owner)]


def require_project(
    project_id: str,
    session: DbSession,
    credential: CredentialDep,
) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise ApiError(404, "project_not_found", "Project does not exist")
    if credential.role == "reader" and project.id not in credential_project_ids(credential):
        raise ApiError(403, "project_forbidden", "This reader credential cannot access the project")
    return project


ProjectDep = Annotated[Project, Depends(require_project)]


def require_owner_project(
    project_id: str,
    session: DbSession,
    credential: OwnerDep,
) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise ApiError(404, "project_not_found", "Project does not exist")
    return project


OwnerProjectDep = Annotated[Project, Depends(require_owner_project)]


def actor_label(credential: Credential) -> str:
    return credential.label
