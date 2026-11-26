from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

Kind = Literal[
    "class",
    "relation_type",
    "attribute_type",
    "instance",
    "relation",
    "attribute_value",
    "source_ref",
]
Status = Literal["active", "deprecated"]
EvidenceState = Literal[
    "discovered",
    "bibliographically_verified",
    "abstract_preview_verified",
    "full_text_verified",
    "secondary_only",
    "unverified",
]
ValueType = Literal["string", "number", "boolean", "date", "uri"]
LocatorKind = Literal["url", "workspace_relative_path", "zotero_key", "free_text"]

NAMED_KINDS: set[str] = {"class", "relation_type", "attribute_type", "instance"}
SCHEMA_KINDS: set[str] = {"class", "relation_type", "attribute_type"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Locator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: LocatorKind
    value: str


class StoredBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    project_id: UUID
    created_at: datetime
    updated_at: datetime
    status: Status = "active"
    notes: str = ""
    source_ref_ids: list[UUID] = Field(default_factory=list)


class NamedBase(StoredBase):
    label: str
    definition: str = ""
    aliases: list[str] = Field(default_factory=list)


class ClassObject(NamedBase):
    kind: Literal["class"]
    parent_ids: list[UUID] = Field(default_factory=list)


class RelationTypeObject(NamedBase):
    kind: Literal["relation_type"]
    domain_ids: list[UUID] = Field(default_factory=list)
    range_ids: list[UUID] = Field(default_factory=list)


class AttributeTypeObject(NamedBase):
    kind: Literal["attribute_type"]
    domain_ids: list[UUID] = Field(default_factory=list)
    value_type: ValueType


class InstanceObject(NamedBase):
    kind: Literal["instance"]
    class_ids: list[UUID] = Field(default_factory=list)


class RelationObject(StoredBase):
    kind: Literal["relation"]
    source_id: UUID
    relation_type_id: UUID
    target_id: UUID


class AttributeValueObject(StoredBase):
    kind: Literal["attribute_value"]
    subject_id: UUID
    attribute_type_id: UUID
    value: Any


class SourceRefObject(StoredBase):
    kind: Literal["source_ref"]
    label: str
    locator: Locator
    citation_text: str = ""
    evidence_state: EvidenceState = "unverified"


GraphObject = Annotated[
    Union[
        ClassObject,
        RelationTypeObject,
        AttributeTypeObject,
        InstanceObject,
        RelationObject,
        AttributeValueObject,
        SourceRefObject,
    ],
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# Input payloads. Reference fields are strings so that they can carry a
# caller-local `new:` identifier until the backend allocates UUIDs.
# ---------------------------------------------------------------------------


class NamedData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    definition: str = ""
    aliases: list[str] = Field(default_factory=list)
    notes: str = ""
    source_ref_ids: list[str] = Field(default_factory=list)
    status: Status = "active"


class ClassData(NamedData):
    parent_ids: list[str] = Field(default_factory=list)


class RelationTypeData(NamedData):
    domain_ids: list[str] = Field(default_factory=list)
    range_ids: list[str] = Field(default_factory=list)


class AttributeTypeData(NamedData):
    domain_ids: list[str] = Field(default_factory=list)
    value_type: ValueType


class InstanceData(NamedData):
    class_ids: list[str] = Field(default_factory=list)


class AssertionData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str = ""
    source_ref_ids: list[str] = Field(default_factory=list)
    status: Status = "active"


class RelationData(AssertionData):
    source_id: str
    relation_type_id: str
    target_id: str


class AttributeValueData(AssertionData):
    subject_id: str
    attribute_type_id: str
    value: Any


class SourceRefData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    locator: Locator
    citation_text: str = ""
    evidence_state: EvidenceState = "unverified"
    notes: str = ""
    source_ref_ids: list[str] = Field(default_factory=list)
    status: Status = "active"


DATA_MODELS: dict[str, type[BaseModel]] = {
    "class": ClassData,
    "relation_type": RelationTypeData,
    "attribute_type": AttributeTypeData,
    "instance": InstanceData,
    "relation": RelationData,
    "attribute_value": AttributeValueData,
    "source_ref": SourceRefData,
}

OBJECT_MODELS: dict[str, type[BaseModel]] = {
    "class": ClassObject,
    "relation_type": RelationTypeObject,
    "attribute_type": AttributeTypeObject,
    "instance": InstanceObject,
    "relation": RelationObject,
    "attribute_value": AttributeValueObject,
    "source_ref": SourceRefObject,
}

# Fields on stored objects that point at other objects.
REF_FIELDS: dict[str, tuple[str, ...]] = {
    "class": ("parent_ids", "source_ref_ids"),
    "relation_type": ("domain_ids", "range_ids", "source_ref_ids"),
    "attribute_type": ("domain_ids", "source_ref_ids"),
    "instance": ("class_ids", "source_ref_ids"),
    "relation": ("source_id", "relation_type_id", "target_id", "source_ref_ids"),
    "attribute_value": ("subject_id", "attribute_type_id", "source_ref_ids"),
    "source_ref": ("source_ref_ids",),
}


class ClassUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str | None = None
    definition: str | None = None
    aliases: list[str] | None = None
    parent_ids: list[str] | None = None
    notes: str | None = None
    source_ref_ids: list[str] | None = None
    status: Status | None = None


class RelationTypeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str | None = None
    definition: str | None = None
    aliases: list[str] | None = None
    domain_ids: list[str] | None = None
    range_ids: list[str] | None = None
    notes: str | None = None
    source_ref_ids: list[str] | None = None
    status: Status | None = None


class AttributeTypeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str | None = None
    definition: str | None = None
    aliases: list[str] | None = None
    domain_ids: list[str] | None = None
    value_type: ValueType | None = None
    notes: str | None = None
    source_ref_ids: list[str] | None = None
    status: Status | None = None


class InstanceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str | None = None
    definition: str | None = None
    aliases: list[str] | None = None
    class_ids: list[str] | None = None
    notes: str | None = None
    source_ref_ids: list[str] | None = None
    status: Status | None = None


class RelationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str | None = None
    relation_type_id: str | None = None
    target_id: str | None = None
    notes: str | None = None
    source_ref_ids: list[str] | None = None
    status: Status | None = None


class AttributeValueUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_id: str | None = None
    attribute_type_id: str | None = None
    value: Any = None
    notes: str | None = None
    source_ref_ids: list[str] | None = None
    status: Status | None = None


class SourceRefUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str | None = None
    locator: Locator | None = None
    citation_text: str | None = None
    evidence_state: EvidenceState | None = None
    notes: str | None = None
    source_ref_ids: list[str] | None = None
    status: Status | None = None


UPDATE_MODELS: dict[str, type[BaseModel]] = {
    "class": ClassUpdate,
    "relation_type": RelationTypeUpdate,
    "attribute_type": AttributeTypeUpdate,
    "instance": InstanceUpdate,
    "relation": RelationUpdate,
    "attribute_value": AttributeValueUpdate,
    "source_ref": SourceRefUpdate,
}

NULLABLE_TEXT_FIELDS = {"definition", "notes", "citation_text"}


def new_uuid() -> UUID:
    return uuid4()


def object_label(obj: BaseModel) -> str:
    label = getattr(obj, "label", None)
    if isinstance(label, str) and label:
        return label
    kind = getattr(obj, "kind", "object")
    return f"{kind} {str(getattr(obj, 'id', ''))[:8]}"


def build_object(
    kind: str,
    object_id: UUID,
    project_id: UUID,
    data: BaseModel,
    *,
    now: datetime | None = None,
) -> BaseModel:
    model = OBJECT_MODELS[kind]
    payload = data.model_dump(mode="json")
    stamp = now or utcnow()
    return model.model_validate(
        {
            **payload,
            "id": object_id,
            "project_id": project_id,
            "kind": kind,
            "created_at": stamp,
            "updated_at": stamp,
        }
    )


def apply_update(
    obj: BaseModel,
    fields: dict[str, Any],
    *,
    now: datetime | None = None,
) -> BaseModel:
    kind = obj.kind
    update_model = UPDATE_MODELS[kind]
    validated = update_model.model_validate(fields)
    changes = validated.model_dump(exclude_unset=True)

    cleaned: dict[str, Any] = {}
    for key, value in changes.items():
        if value is None:
            if key in NULLABLE_TEXT_FIELDS:
                cleaned[key] = ""
                continue
            raise ValueError(f"Field '{key}' cannot be cleared")
        cleaned[key] = value

    merged = obj.model_dump(mode="json")
    merged.update(cleaned)
    merged["updated_at"] = (now or utcnow()).isoformat()
    return OBJECT_MODELS[kind].model_validate(merged)


def validate_value_type(value_type: str, value: Any) -> str | None:
    if value_type == "string":
        if not isinstance(value, str):
            return "Expected a string literal"
    elif value_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return "Expected a number literal"
    elif value_type == "boolean":
        if not isinstance(value, bool):
            return "Expected a boolean literal"
    elif value_type == "date":
        if not isinstance(value, str):
            return "Expected an ISO date string (YYYY-MM-DD)"
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return "Expected an ISO date string (YYYY-MM-DD)"
    elif value_type == "uri":
        if not isinstance(value, str) or not value.strip():
            return "Expected a non-empty URI string"
    else:
        return f"Unknown value type '{value_type}'"
    return None
