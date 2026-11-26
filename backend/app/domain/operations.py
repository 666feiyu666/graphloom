from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .graph import GraphState
from .objects import (
    DATA_MODELS,
    REF_FIELDS,
    Kind,
    apply_update,
    build_object,
    new_uuid,
)


class OperationError(Exception):
    status_code = 422
    code = "invalid_batch"

    def __init__(self, errors: list[dict]) -> None:
        super().__init__("The batch has structural errors and was not applied")
        self.errors = errors


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


class BatchEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operations: list[Operation] = Field(default_factory=list)


@dataclass
class ApplyResult:
    state: GraphState
    id_map: dict[str, str] = field(default_factory=dict)
    touched_ids: set[str] = field(default_factory=set)
    deleted_ids: set[str] = field(default_factory=set)
    added_ids: set[str] = field(default_factory=set)
    updated_ids: set[str] = field(default_factory=set)
    errors: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _issue(
    code: str,
    message: str,
    *,
    object_id: str | None = None,
    details: dict | None = None,
) -> dict:
    issue: dict[str, Any] = {"code": code, "message": message}
    if object_id is not None:
        issue["object_id"] = object_id
    if details:
        issue["details"] = details
    return issue


def _resolve_ref(value: Any, id_map: dict[str, str], errors: list[dict], *, ref: str) -> Any:
    if not isinstance(value, str):
        errors.append(
            _issue("invalid_reference", "Reference values must be strings", object_id=ref)
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
) -> dict[str, Any]:
    resolved = dict(payload)
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
    return resolved


def apply_operations(base: GraphState, operations: list) -> ApplyResult:
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

    for op in operations:
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
            resolved = _resolve_payload(
                parsed.model_dump(mode="json"), op.kind, result.id_map, result.errors, ref=op.ref
            )
            try:
                obj = build_object(
                    op.kind,
                    UUID(object_id),
                    base.project_id,
                    data_model.model_validate(resolved),
                )
            except ValidationError as exc:
                result.errors.append(
                    _issue(
                        "invalid_operation",
                        "Create payload could not be materialized",
                        object_id=op.ref,
                        details={"errors": exc.errors(include_url=False, include_context=False)},
                    )
                )
                continue
            objects[object_id] = obj
            result.touched_ids.add(object_id)
            result.added_ids.add(object_id)
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
                        "Update target does not exist",
                        object_id=object_id,
                    )
                )
                continue
            resolved = _resolve_payload(
                dict(op.fields), existing.kind, result.id_map, result.errors, ref=object_id
            )
            try:
                updated = apply_update(existing, resolved)
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
            result.updated_ids.add(object_id)
            written[object_id] = "update"

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
                        "Delete target does not exist",
                        object_id=object_id,
                    )
                )
                continue
            del objects[object_id]
            result.touched_ids.add(object_id)
            result.deleted_ids.add(object_id)
            written[object_id] = "delete"

    result.state.objects = [objects[key] for key in sorted(objects)]
    return result
