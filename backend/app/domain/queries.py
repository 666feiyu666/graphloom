from __future__ import annotations

from typing import Any
from uuid import UUID

from .graph import (
    descendant_classes,
    display_label,
    instance_class_ids,
    object_map,
    references_to,
)
from .objects import (
    AttributeValueObject,
    ClassObject,
    InstanceObject,
    RelationObject,
    RelationTypeObject,
)


class QueryError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _serialize_many(objects) -> list[dict]:
    return [obj.model_dump(mode="json") for obj in objects]


def _definitions_for(state, objects, relation_objects) -> list[dict]:
    index = object_map(state)
    needed: set[str] = set()
    for obj in objects:
        if isinstance(obj, InstanceObject):
            needed.update(str(item) for item in obj.class_ids)
    for rel in relation_objects:
        needed.add(str(rel.relation_type_id))
    for value in objects:
        if isinstance(value, AttributeValueObject):
            needed.add(str(value.attribute_type_id))
    result = []
    for object_id in sorted(needed):
        obj = index.get(object_id)
        if obj is not None:
            result.append(obj.model_dump(mode="json"))
    return result


def _external_references(state, included_ids: set[str], objects) -> list[dict]:
    index = object_map(state)
    refs: dict[tuple[str, str], dict] = {}
    for obj in objects:
        for field_name in (
            "source_id",
            "target_id",
            "subject_id",
            "relation_type_id",
            "attribute_type_id",
        ):
            value = getattr(obj, field_name, None)
            if value is None:
                continue
            ref_id = str(value)
            if ref_id not in included_ids:
                target = index.get(ref_id)
                refs[(ref_id, field_name)] = {
                    "id": ref_id,
                    "kind": target.kind if target is not None else None,
                    "label": display_label(target) if target is not None else None,
                    "field": field_name,
                    "from_object_id": str(obj.id),
                }
        for field_name in ("class_ids", "source_ref_ids"):
            values = getattr(obj, field_name, None)
            if not values:
                continue
            for value in values:
                ref_id = str(value)
                if ref_id not in included_ids:
                    target = index.get(ref_id)
                    refs[(ref_id, field_name)] = {
                        "id": ref_id,
                        "kind": target.kind if target is not None else None,
                        "label": display_label(target) if target is not None else None,
                        "field": field_name,
                        "from_object_id": str(obj.id),
                    }
    return sorted(refs.values(), key=lambda item: (item["id"], item["field"]))


def neighbors(
    state,
    object_id: str | UUID,
    *,
    direction: str = "both",
    relation_type_ids: list[str] | None = None,
    depth: int = 1,
    include_attribute_values: bool = True,
    max_objects: int = 500,
) -> dict:
    index = object_map(state)
    start = index.get(str(object_id))
    if start is None:
        raise QueryError(
            "unknown_object",
            "The requested object does not exist",
            {"object_id": str(object_id)},
        )

    if not isinstance(start, InstanceObject):
        # For schema objects, expose the local dependency neighborhood rather
        # than inventing edges.
        dependents = references_to(state, start.id)
        related_ids = {item["object_id"] for item in dependents}
        for field_name in (
            "parent_ids",
            "domain_ids",
            "range_ids",
            "class_ids",
            "source_ref_ids",
        ):
            for value in getattr(start, field_name, []) or []:
                related_ids.add(str(value))
        related = [index[item] for item in sorted(related_ids) if item in index]
        truncated = len(related) > max_objects
        related = related[:max_objects]
        included = {str(start.id)} | {str(obj.id) for obj in related}
        return {
            "query_type": "neighbors",
            "objects": _serialize_many([start] + related),
            "relation_ids": [],
            "attribute_value_ids": [],
            "definitions": _definitions_for(state, [start] + related, []),
            "external_references": _external_references(state, included, [start] + related),
            "truncated": truncated,
            "hidden_count": max(0, len(related_ids) - max_objects),
            "returned_count": len(related) + 1,
            "relation_count": 0,
        }

    relations = [obj for obj in state.objects if isinstance(obj, RelationObject)]
    allowed_types = {str(item) for item in (relation_type_ids or [])}
    visited: set[str] = {str(start.id)}
    frontier: list[str] = [str(start.id)]
    collected_relations: dict[str, RelationObject] = {}
    boundary: set[str] = set()
    truncated = False

    def matches(rel: RelationObject, node: str) -> str | None:
        if allowed_types and str(rel.relation_type_id) not in allowed_types:
            return None
        if direction in {"outgoing", "both"} and str(rel.source_id) == node:
            return str(rel.target_id)
        if direction in {"incoming", "both"} and str(rel.target_id) == node:
            return str(rel.source_id)
        return None

    for _level in range(max(1, min(depth, 2))):
        next_frontier: list[str] = []
        for node in sorted(frontier):
            for rel in sorted(relations, key=lambda item: str(item.id)):
                other = matches(rel, node)
                if other is None:
                    continue
                if str(rel.id) not in collected_relations:
                    if len(collected_relations) >= max_objects:
                        truncated = True
                        continue
                    collected_relations[str(rel.id)] = rel
                if other in visited:
                    continue
                if len(visited) >= max_objects:
                    truncated = True
                    boundary.add(other)
                    continue
                visited.add(other)
                next_frontier.append(other)
        frontier = next_frontier
        if not frontier:
            break

    instance_objects = [
        index[item]
        for item in sorted(visited)
        if item in index and isinstance(index[item], InstanceObject)
    ]
    relation_objects = [collected_relations[key] for key in sorted(collected_relations)]

    attribute_values: list[AttributeValueObject] = []
    if include_attribute_values:
        for value in state.objects:
            if (
                isinstance(value, AttributeValueObject)
                and str(value.subject_id) in visited
                and len(attribute_values) < max_objects
            ):
                attribute_values.append(value)
        attribute_values.sort(key=lambda item: str(item.id))

    core = instance_objects + relation_objects + attribute_values
    included = {str(obj.id) for obj in core}
    definitions = _definitions_for(state, core, relation_objects)
    hidden = len(boundary) + sum(
        1
        for value in state.objects
        if isinstance(value, AttributeValueObject)
        and str(value.subject_id) in visited
        and str(value.id) not in {str(item.id) for item in attribute_values}
    )

    return {
        "query_type": "neighbors",
        "objects": _serialize_many(core),
        "relation_ids": [str(obj.id) for obj in relation_objects],
        "attribute_value_ids": [str(obj.id) for obj in attribute_values],
        "definitions": definitions,
        "external_references": _external_references(state, included, core),
        "truncated": truncated,
        "hidden_count": hidden,
        "returned_count": len(core),
        "relation_count": len(relation_objects),
    }


def instances_of(
    state,
    class_id: str | UUID,
    *,
    include_descendants: bool = True,
    max_objects: int = 500,
) -> dict:
    index = object_map(state)
    class_obj = index.get(str(class_id))
    if class_obj is None or not isinstance(class_obj, ClassObject):
        raise QueryError(
            "unknown_class",
            "The requested class does not exist",
            {"class_id": str(class_id)},
        )
    allowed = (
        descendant_classes(state, class_obj.id)
        if include_descendants
        else {str(class_obj.id)}
    )
    instances = [
        obj
        for obj in state.objects
        if isinstance(obj, InstanceObject) and instance_class_ids(obj) & allowed
    ]
    instances.sort(key=lambda item: str(item.id))
    total = len(instances)
    truncated = total > max_objects
    instances = instances[:max_objects]
    definitions = [
        index[item].model_dump(mode="json")
        for item in sorted(allowed)
        if item in index and isinstance(index[item], ClassObject)
    ]
    included = {str(obj.id) for obj in instances}
    return {
        "query_type": "instances_of",
        "class_id": str(class_obj.id),
        "include_descendants": include_descendants,
        "objects": _serialize_many(instances),
        "relation_ids": [],
        "attribute_value_ids": [],
        "definitions": definitions,
        "external_references": _external_references(state, included, instances),
        "truncated": truncated,
        "hidden_count": max(0, total - max_objects),
        "returned_count": len(instances),
    }


def references_of(state, object_id: str | UUID, *, max_objects: int = 500) -> dict:
    index = object_map(state)
    target = index.get(str(object_id))
    if target is None:
        raise QueryError(
            "unknown_object",
            "The requested object does not exist",
            {"object_id": str(object_id)},
        )
    references = references_to(state, target.id)
    unique_ids = sorted({item["object_id"] for item in references})
    truncated = len(unique_ids) > max_objects
    included_ids = unique_ids[:max_objects]
    objects = [index[item] for item in included_ids if item in index]
    return {
        "query_type": "references_to",
        "object_id": str(target.id),
        "references": [item for item in references if item["object_id"] in set(included_ids)],
        "objects": _serialize_many(objects),
        "definitions": _definitions_for(state, objects, []),
        "external_references": _external_references(state, set(included_ids), objects),
        "truncated": truncated,
        "hidden_count": max(0, len(unique_ids) - max_objects),
        "returned_count": len(objects),
    }
