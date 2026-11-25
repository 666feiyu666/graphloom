from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.changesets import ChangeSetEnvelope
from app.domain.queries import QueryEnvelope

__all__ = [
    "ChangeSetEnvelope",
    "CommitRequest",
    "CredentialCreate",
    "LayoutUpdate",
    "ProjectCreate",
    "QueryEnvelope",
    "RestorePreviewRequest",
    "SnapshotCreate",
]


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class CommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)


class SnapshotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    revision: int | None = Field(default=None, ge=0)


class RestorePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = ""


class LayoutUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    data: dict = Field(default_factory=dict)


class CredentialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=200)
    project_ids: list[UUID] = Field(default_factory=list)
