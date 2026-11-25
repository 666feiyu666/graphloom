from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.diff import diff_is_empty, diff_states
from app.domain.graph import GraphState, empty_state
from app.domain.objects import (
    DATA_MODELS,
    REF_FIELDS,
    Kind,
    apply_update,
    build_object,
    new_uuid,
)
from app.domain.serialization import payload_hash
from app.domain.validation import compute_impact, validate_state
from app.storage.models import (
    ChangeSet,
    CommitIdempotency,
    Project,
    ProjectState,
    Revision,
)


class ChangeSetError(Exception):
    status_code = 422
    code = "change_set_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class StaleBaseRevision(ChangeSetError):
    status_code = 409
    code = "revision_conflict"

    def __init__(self, expected: int, current: int, intervening: list[int] | None = None) -> None:
        super().__init__(
            "The change set was prepared against a revision that is no longer current",
            details={
                "expected_revision": expected,
                "current_revision": current,
                "intervening_revisions": intervening or [],
            },
        )


class IdempotencyConflict(ChangeSetError):
    status_code = 409
    code = "idempotency_conflict"

    def __init__(self) -> None:
        super().__init__("The idempotency key was already used with a different payload")


class InvalidChangeSet(ChangeSetError):
    status_code = 422
    code = "invalid_change_set"

    def __init__(self, errors: list[dict]) -> None:
        super().__init__(
            "The change set has structural errors and cannot be committed",
            details={"errors": errors},
        )


class CreateOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["create"]
    ref: str
    kind: Kind
    data: dict[str, Any]

    @field_validator("ref")
    @classmethod
    def _ref_is_temporary(cls, value: str) -> str:
        if not value.startswith("new:"):
            raise ValueError("create.ref must begin with 'new:'")
        return value


class UpdateOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["update"]
    id: UUID
    fields: dict[str, Any]


class DeleteOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["delete"]
    id: UUID


Operation = Annotated[
    Union[CreateOperation, UpdateOperation, DeleteOperation],
    Field(discriminator="op"),
]


class ChangeSetEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_revision: int = Field(ge=0)
    reason: str = ""
    operations: list[Operation] = Field(default_factory=list)


@dataclass
class ApplyResult:
    state: GraphState
    normalized: list[dict] = field(default_factory=list)
    id_map: dict[str, str] = field(default_factory=dict)
    touched_ids: set[str] = field(default_factory=set)
    deleted_ids: set[str] = field(default_factory=set)
    errors: list[dict] = field(default_factory=list)


def _issue(
    code: str,
    message: str,
    *,
    object_id: str | None = None,
    field_name: str | None = None,
    details: dict | None = None,
) -> dict:
    issue: dict[str, Any] = {"code": code, "message": message}
    if object_id is not None:
        issue["object_id"] = object_id
    if field_name is not None:
        issue["field"] = field_name
    if details:
        issue["details"] = details
    return issue


def _resolve_ref(value: Any, id_map: dict[str, str], errors: list[dict], *, ref: str) -> Any:
    if not isinstance(value, str):
        errors.append(
            _issue(
                "invalid_reference",
                "Reference values must be strings",
                object_id=ref,
            )
        )
        return value
    if value.startswith("new:"):
        if value not in id_map:
            errors.append(
                _issue(
                    "undefined_temporary_reference",
                    f"Temporary reference '{value}' is not defined in this batch",
                    object_id=ref,
                    details={"reference": value},
                )
            )
            return value
        return id_map[value]
    return value


def _resolve_payload(
    payload: dict[str, Any],
    kind: str,
    id_map: dict[str, str],
    errors: list[dict],
    *,
    ref: str,
) -> tuple[dict[str, Any], bool]:
    resolved = dict(payload)
    failed = False
    for field_name in REF_FIELDS.get(kind, ()):
        if field_name not in resolved:
            continue
        value = resolved[field_name]
        if isinstance(value, list):
            resolved[field_name] = [
                _resolve_ref(item, id_map, errors, ref=ref) for item in value
            ]
        else:
            resolved[field_name] = _resolve_ref(value, id_map, errors, ref=ref)
    return resolved, failed


def apply_operations(base: GraphState, operations: list, actor: str) -> ApplyResult:
    result = ApplyResult(state=base.model_copy(deep=True))
    objects = {str(obj.id): obj for obj in result.state.objects}

    # Allocate every created identifier first so that forward references work.
    for op in operations:
        if isinstance(op, CreateOperation):
            if op.ref in result.id_map:
                result.errors.append(
                    _issue(
                        "duplicate_temporary_reference",
                        f"Temporary reference '{op.ref}' appears more than once",
                        object_id=op.ref,
                    )
                )
                continue
            result.id_map[op.ref] = str(new_uuid())

    written: dict[str, str] = {}

    for index, op in enumerate(operations):
        if isinstance(op, CreateOperation):
            object_id = result.id_map.get(op.ref)
            if object_id is None:
                continue
            if object_id in objects:
                result.errors.append(
                    _issue(
                        "conflicting_write",
                        "Object is written more than once in the same batch",
                        object_id=object_id,
                    )
                )
                continue
            data_model = DATA_MODELS.get(op.kind)
            if data_model is None:
                result.errors.append(
                    _issue("unknown_kind", f"Unknown kind '{op.kind}'", object_id=op.ref)
                )
                continue
            try:
                parsed = data_model.model_validate(op.data)
            except ValidationError as exc:
                result.errors.append(
                    _issue(
                        "invalid_operation",
                        "Create payload is invalid",
                        object_id=op.ref,
                        details={"errors": exc.errors(include_url=False, include_context=False)},
                    )
                )
                continue
            payload, _ = _resolve_payload(
                parsed.model_dump(mode="json"), op.kind, result.id_map, result.errors, ref=op.ref
            )
            try:
                obj = build_object(
                    op.kind,
                    UUID(object_id),
                    base.project_id,
                    data_model.model_validate(payload),
                    actor,
                )
            except (ValidationError, ValueError) as exc:
                details = (
                    exc.errors(include_url=False, include_context=False)
                    if isinstance(exc, ValidationError)
                    else {"message": str(exc)}
                )
                result.errors.append(
                    _issue(
                        "invalid_operation",
                        "Create payload could not be materialized",
                        object_id=op.ref,
                        details=details,
                    )
                )
                continue
            objects[object_id] = obj
            result.touched_ids.add(object_id)
            result.normalized.append(
                {
                    "op": "create",
                    "ref": op.ref,
                    "id": object_id,
                    "kind": op.kind,
                    "data": payload,
                }
            )
            written[object_id] = "create"

        elif isinstance(op, UpdateOperation):
            object_id = str(op.id)
            if object_id in written:
                result.errors.append(
                    _issue(
                        "conflicting_write",
                        "Object is written more than once in the same batch",
                        object_id=object_id,
                    )
                )
                continue
            existing = objects.get(object_id)
            if existing is None:
                result.errors.append(
                    _issue(
                        "unknown_object",
                        "Update target does not exist in the base revision",
                        object_id=object_id,
                    )
                )
                continue
            payload, _ = _resolve_payload(
                dict(op.fields), existing.kind, result.id_map, result.errors, ref=object_id
            )
            try:
                updated = apply_update(existing, payload, actor)
            except (ValidationError, ValueError) as exc:
                details = (
                    exc.errors(include_url=False, include_context=False)
                    if isinstance(exc, ValidationError)
                    else {"message": str(exc)}
                )
                result.errors.append(
                    _issue(
                        "invalid_update",
                        "Update fields are invalid",
                        object_id=object_id,
                        details=details,
                    )
                )
                continue
            objects[object_id] = updated
            result.touched_ids.add(object_id)
            written[object_id] = "update"
            result.normalized.append(
                {"op": "update", "id": object_id, "fields": payload}
            )

        elif isinstance(op, DeleteOperation):
            object_id = str(op.id)
            if object_id in written:
                result.errors.append(
                    _issue(
                        "conflicting_write",
                        "Object is written more than once in the same batch",
                        object_id=object_id,
                    )
                )
                continue
            if object_id not in objects:
                result.errors.append(
                    _issue(
                        "unknown_object",
                        "Delete target does not exist in the base revision",
                        object_id=object_id,
                    )
                )
                continue
            del objects[object_id]
            result.touched_ids.add(object_id)
            result.deleted_ids.add(object_id)
            written[object_id] = "delete"
            result.normalized.append({"op": "delete", "id": object_id})

    result.state.objects = [objects[key] for key in sorted(objects)]
    return result


def state_at_revision(
    session: Session, project: Project, revision: int | None
) -> GraphState | None:
    if revision is None:
        revision = project.current_revision
    if revision < 0 or revision > project.current_revision:
        return None
    if revision == 0:
        return empty_state(UUID(project.id), 0)
    row = session.scalar(
        select(Revision).where(
            Revision.project_id == project.id,
            Revision.revision == revision,
        )
    )
    if row is None:
        return None
    return GraphState.model_validate_json(row.state_json)


def current_state(session: Session, project: Project) -> GraphState:
    row = session.get(ProjectState, project.id)
    if row is None:
        return empty_state(UUID(project.id), project.current_revision)
    return GraphState.model_validate_json(row.state_json)


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def prepare_change_set(
    session: Session,
    project: Project,
    envelope: ChangeSetEnvelope,
    actor: str,
) -> ChangeSet:
    if envelope.base_revision > project.current_revision:
        raise StaleBaseRevision(envelope.base_revision, project.current_revision)
    base = state_at_revision(session, project, envelope.base_revision)
    if base is None:
        raise StaleBaseRevision(envelope.base_revision, project.current_revision)

    applied = apply_operations(base, envelope.operations, actor)
    applied.state.revision = envelope.base_revision + 1

    validation = validate_state(applied.state, deleted_ids=applied.deleted_ids)
    errors = applied.errors + validation.errors
    diff = diff_states(base, applied.state)
    impacted = compute_impact(base, applied.state, applied.touched_ids)
    hash_payload = {
        "base_revision": envelope.base_revision,
        "reason": envelope.reason,
        "operations": applied.normalized,
    }
    change_set = ChangeSet(
        id=str(uuid4()),
        project_id=project.id,
        base_revision=envelope.base_revision,
        status="invalid" if errors else "prepared",
        payload_hash=payload_hash(hash_payload),
        normalized_json=_json_dump(applied.normalized),
        candidate_state_json=applied.state.model_dump_json(),
        diff_json=_json_dump(diff),
        impacted_json=_json_dump(impacted),
        errors_json=_json_dump(errors),
        warnings_json=_json_dump(validation.warnings),
        id_map_json=_json_dump(applied.id_map),
        actor=actor,
        reason=envelope.reason,
    )
    session.add(change_set)
    return change_set


def prepare_replacement(
    session: Session,
    project: Project,
    candidate: GraphState,
    *,
    actor: str,
    reason: str,
    source: dict,
    base_revision: int | None = None,
) -> ChangeSet:
    base_revision = project.current_revision if base_revision is None else base_revision
    base = state_at_revision(session, project, base_revision)
    if base is None:
        raise StaleBaseRevision(base_revision, project.current_revision)

    candidate.project_id = UUID(project.id)
    candidate.revision = base_revision + 1
    validation = validate_state(candidate)
    diff = diff_states(base, candidate)
    touched = {str(obj.id) for obj in candidate.objects} | {
        str(obj.id) for obj in base.objects
    }
    impacted = compute_impact(base, candidate, touched)
    normalized = {"mode": "replace", "source": source}
    hash_payload = {
        "base_revision": base_revision,
        "reason": reason,
        "operations": normalized,
        "objects": candidate.model_dump(mode="json")["objects"],
    }
    change_set = ChangeSet(
        id=str(uuid4()),
        project_id=project.id,
        base_revision=base_revision,
        status="invalid" if validation.errors else "prepared",
        payload_hash=payload_hash(hash_payload),
        normalized_json=_json_dump(normalized),
        candidate_state_json=candidate.model_dump_json(),
        diff_json=_json_dump(diff),
        impacted_json=_json_dump(impacted),
        errors_json=_json_dump(validation.errors),
        warnings_json=_json_dump(validation.warnings),
        id_map_json=_json_dump({}),
        actor=actor,
        reason=reason,
    )
    session.add(change_set)
    return change_set


def commit_change_set(
    session: Session,
    project: Project,
    change_set: ChangeSet,
    *,
    expected_revision: int,
    idempotency_key: str,
    actor: str,
) -> dict:
    if not idempotency_key:
        raise ChangeSetError("An Idempotency-Key header is required")

    existing = session.scalar(
        select(CommitIdempotency).where(
            CommitIdempotency.actor == actor,
            CommitIdempotency.project_id == project.id,
            CommitIdempotency.key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.payload_hash != change_set.payload_hash:
            raise IdempotencyConflict()
        payload = json.loads(existing.result_json)
        payload["idempotent_replay"] = True
        return payload

    if expected_revision != change_set.base_revision:
        raise ChangeSetError(
            "expected_revision must equal the change set's base_revision",
            details={
                "expected_revision": expected_revision,
                "base_revision": change_set.base_revision,
            },
        )

    if project.current_revision != expected_revision:
        intervening = list(
            session.scalars(
                select(Revision.revision)
                .where(
                    Revision.project_id == project.id,
                    Revision.revision > expected_revision,
                )
                .order_by(Revision.revision)
            )
        )
        raise StaleBaseRevision(expected_revision, project.current_revision, intervening)

    if change_set.status != "prepared":
        errors = json.loads(change_set.errors_json or "[]")
        raise InvalidChangeSet(errors)

    candidate = GraphState.model_validate_json(change_set.candidate_state_json)
    candidate.revision = project.current_revision + 1
    validation = validate_state(candidate)
    if validation.errors:
        change_set.status = "invalid"
        change_set.errors_json = _json_dump(validation.errors)
        session.commit()
        raise InvalidChangeSet(validation.errors)

    before = current_state(session, project)
    diff = diff_states(before, candidate)

    if diff_is_empty(diff):
        result = {
            "project_id": project.id,
            "revision": project.current_revision,
            "changed": False,
            "change_set_id": change_set.id,
            "diff": diff,
            "warnings": json.loads(change_set.warnings_json or "[]"),
            "id_map": json.loads(change_set.id_map_json or "{}"),
        }
        change_set.status = "committed"
        change_set.committed_revision = project.current_revision
        session.add(
            CommitIdempotency(
                id=str(uuid4()),
                actor=actor,
                project_id=project.id,
                key=idempotency_key,
                payload_hash=change_set.payload_hash,
                change_set_id=change_set.id,
                result_json=_json_dump(result),
            )
        )
        session.commit()
        return result

    new_revision = project.current_revision + 1
    revision_row = Revision(
        id=str(uuid4()),
        project_id=project.id,
        revision=new_revision,
        state_json=candidate.model_dump_json(),
        diff_json=_json_dump(diff),
        actor=actor,
        reason=change_set.reason,
        change_set_id=change_set.id,
    )
    session.add(revision_row)

    state_row = session.get(ProjectState, project.id)
    if state_row is None:
        state_row = ProjectState(project_id=project.id, revision=new_revision, state_json="{}")
        session.add(state_row)
    state_row.revision = new_revision
    state_row.state_json = candidate.model_dump_json()

    project.current_revision = new_revision
    project.updated_at = datetime.now(timezone.utc)
    change_set.status = "committed"
    change_set.committed_revision = new_revision

    result = {
        "project_id": project.id,
        "revision": new_revision,
        "changed": True,
        "change_set_id": change_set.id,
        "diff": diff,
        "warnings": json.loads(change_set.warnings_json or "[]"),
        "id_map": json.loads(change_set.id_map_json or "{}"),
    }
    session.add(
        CommitIdempotency(
            id=str(uuid4()),
            actor=actor,
            project_id=project.id,
            key=idempotency_key,
            payload_hash=change_set.payload_hash,
            change_set_id=change_set.id,
            result_json=_json_dump(result),
        )
    )
    session.commit()
    return result


def change_set_dict(change_set: ChangeSet) -> dict:
    return {
        "id": change_set.id,
        "project_id": change_set.project_id,
        "base_revision": change_set.base_revision,
        "status": change_set.status,
        "payload_hash": change_set.payload_hash,
        "operations": json.loads(change_set.normalized_json or "[]"),
        "diff": json.loads(change_set.diff_json or "{}"),
        "impacted": json.loads(change_set.impacted_json or "{}"),
        "errors": json.loads(change_set.errors_json or "[]"),
        "warnings": json.loads(change_set.warnings_json or "[]"),
        "id_map": json.loads(change_set.id_map_json or "{}"),
        "reason": change_set.reason,
        "actor": change_set.actor,
        "created_at": change_set.created_at.isoformat() if change_set.created_at else None,
        "committed_revision": change_set.committed_revision,
    }


def revision_dict(revision: Revision) -> dict:
    return {
        "id": revision.id,
        "revision": revision.revision,
        "actor": revision.actor,
        "reason": revision.reason,
        "change_set_id": revision.change_set_id,
        "created_at": revision.created_at.isoformat() if revision.created_at else None,
        "diff": json.loads(revision.diff_json or "{}"),
    }
