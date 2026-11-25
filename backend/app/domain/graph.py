from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .objects import (
    REF_FIELDS,
    ClassObject,
    GraphObject,
    NamedBase,
    object_label,
)


class GraphState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: int = 1
    project_id: UUID
    revision: int = 0
    objects: list[GraphObject] = Field(default_factory=list)


def empty_state(project_id: UUID, revision: int = 0) -> GraphState:
    return GraphState(project_id=project_id, revision=revision, objects=[])


def object_map(state: GraphState) -> dict[str, GraphObject]:
    return {str(obj.id): obj for obj in state.objects}


def get_object(state: GraphState, object_id: str | UUID) -> GraphObject | None:
    return object_map(state).get(str(object_id))


def objects_of_kind(state: GraphState, kind: str) -> list[GraphObject]:
    return [obj for obj in state.objects if obj.kind == kind]


def display_label(obj: BaseModel) -> str:
    return object_label(obj)


def class_children(state: GraphState) -> dict[str, set[str]]:
    children: dict[str, set[str]] = defaultdict(set)
    for obj in state.objects:
        if isinstance(obj, ClassObject):
            for parent in obj.parent_ids:
                children[str(parent)].add(str(obj.id))
    return children


def descendant_classes(state: GraphState, class_id: str | UUID) -> set[str]:
    children = class_children(state)
    root = str(class_id)
    seen: set[str] = set()
    queue = deque([root])
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        for child in children.get(current, set()):
            if child not in seen:
                queue.append(child)
    return seen


def ancestor_classes(state: GraphState, class_id: str | UUID) -> set[str]:
    objects = object_map(state)
    seen: set[str] = set()
    queue = deque([str(class_id)])
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        obj = objects.get(current)
        if isinstance(obj, ClassObject):
            for parent in obj.parent_ids:
                if str(parent) not in seen:
                    queue.append(str(parent))
    return seen


def reference_values(obj: GraphObject) -> Iterable[tuple[str, str]]:
    for field in REF_FIELDS.get(obj.kind, ()):
        value = getattr(obj, field, None)
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            for item in value:
                yield field, str(item)
        else:
            yield field, str(value)


def references_to(state: GraphState, target_id: str | UUID) -> list[dict]:
    target = str(target_id)
    found: list[dict] = []
    for obj in state.objects:
        for field, ref in reference_values(obj):
            if ref == target:
                found.append(
                    {
                        "object_id": str(obj.id),
                        "kind": obj.kind,
                        "label": display_label(obj),
                        "field": field,
                    }
                )
    return sorted(found, key=lambda item: (item["object_id"], item["field"]))


def instance_class_ids(obj: GraphObject) -> set[str]:
    return {str(class_id) for class_id in getattr(obj, "class_ids", [])}


def is_instance_of_any(
    state: GraphState,
    instance: GraphObject,
    allowed_class_ids: Iterable[str | UUID],
    *,
    include_descendants: bool = True,
) -> bool:
    allowed: set[str] = set()
    for class_id in allowed_class_ids:
        if include_descendants:
            allowed |= descendant_classes(state, class_id)
        else:
            allowed.add(str(class_id))
    return bool(instance_class_ids(instance) & allowed)


def instance_labels(state: GraphState) -> dict[str, str]:
    return {
        str(obj.id): display_label(obj)
        for obj in state.objects
        if obj.kind == "instance"
    }


def named_object_ids_by_label(state: GraphState) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for obj in state.objects:
        if isinstance(obj, NamedBase):
            key = " ".join(obj.label.casefold().split())
            grouped[key].add(str(obj.id))
    return grouped
