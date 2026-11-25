from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from .graph import (
    class_children,
    descendant_classes,
    display_label,
    instance_class_ids,
    object_map,
    reference_values,
    references_to,
)
from .objects import (
    AttributeTypeObject,
    AttributeValueObject,
    ClassObject,
    InstanceObject,
    RelationObject,
    RelationTypeObject,
    SourceRefObject,
    validate_value_type,
)

REFERENCE_KINDS: dict[str, str] = {
    "parent_ids": "class",
    "domain_ids": "class",
    "range_ids": "class",
    "class_ids": "class",
    "source_id": "instance",
    "target_id": "instance",
    "subject_id": "instance",
    "relation_type_id": "relation_type",
    "attribute_type_id": "attribute_type",
    "source_ref_ids": "source_ref",
}


@dataclass
class ValidationResult:
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _issue(
    code: str,
    message: str,
    *,
    object_id: str | None = None,
    field_name: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict:
    issue: dict[str, Any] = {"code": code, "message": message}
    if object_id is not None:
        issue["object_id"] = object_id
    if field_name is not None:
        issue["field"] = field_name
    if details:
        issue["details"] = details
    return issue


def validate_state(
    state,
    *,
    deleted_ids: Iterable[str] = (),
) -> ValidationResult:
    result = ValidationResult()
    deleted = {str(item) for item in deleted_ids}
    objects = object_map(state)

    # Duplicate identifiers are an immediate integrity failure.
    counts: dict[str, int] = defaultdict(int)
    for obj in state.objects:
        counts[str(obj.id)] += 1
    for object_id, count in counts.items():
        if count > 1:
            result.errors.append(
                _issue(
                    "duplicate_id",
                    f"Object id appears {count} times",
                    object_id=object_id,
                )
            )

    # References must exist, belong to the same project, and point at the
    # expected kind.
    for obj in state.objects:
        for field_name, ref in reference_values(obj):
            expected_kind = REFERENCE_KINDS.get(field_name)
            target = objects.get(ref)
            if target is None:
                if ref in deleted:
                    dependents = references_to(state, ref)
                    result.errors.append(
                        _issue(
                            "delete_dependency",
                            f"Deleted object is still referenced through '{field_name}'",
                            object_id=str(obj.id),
                            field_name=field_name,
                            details={
                                "deleted_id": ref,
                                "dependent": {
                                    "object_id": str(obj.id),
                                    "kind": obj.kind,
                                    "label": display_label(obj),
                                    "field": field_name,
                                },
                                "dependents": dependents,
                            },
                        )
                    )
                else:
                    result.errors.append(
                        _issue(
                            "unknown_reference",
                            f"Reference through '{field_name}' does not exist",
                            object_id=str(obj.id),
                            field_name=field_name,
                            details={"reference_id": ref, "expected_kind": expected_kind},
                        )
                    )
                continue
            if str(target.project_id) != str(obj.project_id):
                result.errors.append(
                    _issue(
                        "cross_project_reference",
                        "Reference crosses project boundaries",
                        object_id=str(obj.id),
                        field_name=field_name,
                        details={"reference_id": ref},
                    )
                )
            if expected_kind and target.kind != expected_kind:
                result.errors.append(
                    _issue(
                        "wrong_reference_kind",
                        f"Reference through '{field_name}' must point at a {expected_kind}",
                        object_id=str(obj.id),
                        field_name=field_name,
                        details={
                            "reference_id": ref,
                            "expected_kind": expected_kind,
                            "actual_kind": target.kind,
                        },
                    )
                )

    # Hierarchy cycles are rejected for the MVP representation.
    cycle = _find_class_cycle(state)
    if cycle:
        result.errors.append(
            _issue(
                "hierarchy_cycle",
                "Class parent hierarchy contains a cycle",
                object_id=cycle[0],
                field_name="parent_ids",
                details={"cycle": cycle},
            )
        )

    # Literal datatype checks.
    for obj in state.objects:
        if isinstance(obj, AttributeValueObject):
            attribute_type = objects.get(str(obj.attribute_type_id))
            if isinstance(attribute_type, AttributeTypeObject):
                problem = validate_value_type(attribute_type.value_type, obj.value)
                if problem:
                    result.errors.append(
                        _issue(
                            "literal_type_mismatch",
                            problem,
                            object_id=str(obj.id),
                            field_name="value",
                            details={
                                "attribute_type_id": str(attribute_type.id),
                                "value_type": attribute_type.value_type,
                            },
                        )
                    )

    # Advisory warnings: these must not block exploratory modeling.
    grouped_labels: dict[tuple[str, str], list[str]] = defaultdict(list)
    for obj in state.objects:
        if hasattr(obj, "label") and obj.label:
            key = " ".join(obj.label.casefold().split())
            grouped_labels[(obj.kind, key)].append(str(obj.id))

    for obj in state.objects:
        if obj.kind in {"class", "relation_type", "attribute_type", "instance"}:
            if not getattr(obj, "definition", "").strip():
                result.warnings.append(
                    _issue(
                        "missing_definition",
                        "Named object has no definition",
                        object_id=str(obj.id),
                        field_name="definition",
                    )
                )

    for (kind, key), ids in grouped_labels.items():
        if key and len(ids) > 1:
            for object_id in ids:
                result.warnings.append(
                    _issue(
                        "duplicate_label",
                        "Another object of the same kind uses this label",
                        object_id=object_id,
                        field_name="label",
                        details={"label": key, "object_ids": sorted(ids)},
                    )
                )

    for obj in state.objects:
        if isinstance(obj, InstanceObject) and not obj.class_ids:
            result.warnings.append(
                _issue(
                    "untyped_instance",
                    "Instance has no explicit class membership",
                    object_id=str(obj.id),
                    field_name="class_ids",
                )
            )

        if isinstance(obj, RelationObject):
            relation_type = objects.get(str(obj.relation_type_id))
            if isinstance(relation_type, RelationTypeObject):
                source = objects.get(str(obj.source_id))
                target = objects.get(str(obj.target_id))
                if relation_type.domain_ids and source is not None:
                    if not _instance_in_allowed(state, source, relation_type.domain_ids):
                        result.warnings.append(
                            _issue(
                                "domain_mismatch",
                                "Relation source is outside the relation type's advisory domain",
                                object_id=str(obj.id),
                                field_name="source_id",
                                details={"relation_type_id": str(relation_type.id)},
                            )
                        )
                if relation_type.range_ids and target is not None:
                    if not _instance_in_allowed(state, target, relation_type.range_ids):
                        result.warnings.append(
                            _issue(
                                "range_mismatch",
                                "Relation target is outside the relation type's advisory range",
                                object_id=str(obj.id),
                                field_name="target_id",
                                details={"relation_type_id": str(relation_type.id)},
                            )
                        )
                if relation_type.lifecycle == "deprecated":
                    result.warnings.append(
                        _issue(
                            "deprecated_definition",
                            "Relation uses a deprecated relation type",
                            object_id=str(obj.id),
                            field_name="relation_type_id",
                            details={"definition_id": str(relation_type.id)},
                        )
                    )

        if isinstance(obj, AttributeValueObject):
            attribute_type = objects.get(str(obj.attribute_type_id))
            subject = objects.get(str(obj.subject_id))
            if isinstance(attribute_type, AttributeTypeObject):
                if attribute_type.domain_ids and subject is not None:
                    if not _instance_in_allowed(state, subject, attribute_type.domain_ids):
                        result.warnings.append(
                            _issue(
                                "domain_mismatch",
                                "Attribute subject is outside the attribute type's advisory domain",
                                object_id=str(obj.id),
                                field_name="subject_id",
                                details={"attribute_type_id": str(attribute_type.id)},
                            )
                        )
                if attribute_type.lifecycle == "deprecated":
                    result.warnings.append(
                        _issue(
                            "deprecated_definition",
                            "Attribute value uses a deprecated attribute type",
                            object_id=str(obj.id),
                            field_name="attribute_type_id",
                            details={"definition_id": str(attribute_type.id)},
                        )
                    )

        if isinstance(obj, InstanceObject):
            for class_id in obj.class_ids:
                class_obj = objects.get(str(class_id))
                if isinstance(class_obj, ClassObject) and class_obj.lifecycle == "deprecated":
                    result.warnings.append(
                        _issue(
                            "deprecated_definition",
                            "Instance uses a deprecated class",
                            object_id=str(obj.id),
                            field_name="class_ids",
                            details={"definition_id": str(class_id)},
                        )
                    )

    result.errors.sort(key=lambda item: (item.get("code", ""), item.get("object_id", "")))
    result.warnings.sort(
        key=lambda item: (item.get("code", ""), item.get("object_id", ""), item.get("field", ""))
    )
    return result


def _instance_in_allowed(state, instance, allowed_class_ids: Iterable) -> bool:
    allowed: set[str] = set()
    for class_id in allowed_class_ids:
        allowed |= descendant_classes(state, class_id)
    return bool(instance_class_ids(instance) & allowed)


def _find_class_cycle(state) -> list[str] | None:
    classes = {str(obj.id): obj for obj in state.objects if isinstance(obj, ClassObject)}
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        if node in visiting:
            start = stack.index(node)
            return stack[start:] + [node]
        if node in visited:
            return None
        visiting.add(node)
        stack.append(node)
        obj = classes.get(node)
        if obj is not None:
            for parent in obj.parent_ids:
                found = visit(str(parent))
                if found:
                    return found
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for class_id in sorted(classes):
        found = visit(class_id)
        if found:
            return found
    return None


def warning_signature(warning: dict) -> str:
    return "|".join(
        [
            warning.get("code", ""),
            warning.get("object_id", ""),
            warning.get("field", ""),
        ]
    )


def compute_impact(before, after, touched_ids: Iterable[str]) -> dict:
    before_map = object_map(before)
    after_map = object_map(after)
    touched = {str(item) for item in touched_ids}
    impacted: set[str] = set(touched)

    for object_id in list(touched):
        obj = after_map.get(object_id) or before_map.get(object_id)
        if obj is None:
            continue
        for item in references_to(after, object_id) + references_to(before, object_id):
            impacted.add(item["object_id"])

        if isinstance(obj, ClassObject):
            classes = descendant_classes(after, object_id) | descendant_classes(before, object_id)
            for other in list(after.objects) + list(before.objects):
                if isinstance(other, InstanceObject) and instance_class_ids(other) & classes:
                    impacted.add(str(other.id))
                elif isinstance(other, RelationTypeObject) and (
                    {str(x) for x in other.domain_ids + other.range_ids} & classes
                ):
                    impacted.add(str(other.id))
                elif isinstance(other, AttributeTypeObject) and (
                    {str(x) for x in other.domain_ids} & classes
                ):
                    impacted.add(str(other.id))

        if isinstance(obj, RelationTypeObject):
            for other in list(after.objects) + list(before.objects):
                if isinstance(other, RelationObject) and str(other.relation_type_id) == object_id:
                    impacted.add(str(other.id))

        if isinstance(obj, AttributeTypeObject):
            for other in list(after.objects) + list(before.objects):
                if (
                    isinstance(other, AttributeValueObject)
                    and str(other.attribute_type_id) == object_id
                ):
                    impacted.add(str(other.id))

        if isinstance(obj, InstanceObject):
            for other in list(after.objects) + list(before.objects):
                if isinstance(other, RelationObject) and object_id in {
                    str(other.source_id),
                    str(other.target_id),
                }:
                    impacted.add(str(other.id))
                elif isinstance(other, AttributeValueObject) and str(other.subject_id) == object_id:
                    impacted.add(str(other.id))

        if isinstance(obj, SourceRefObject):
            for other in list(after.objects) + list(before.objects):
                if object_id in {str(item) for item in other.source_ref_ids}:
                    impacted.add(str(other.id))

    # Expand once more so that assertions attached to impacted instances and
    # relations of impacted relation types are visible in the preview.
    for object_id in list(impacted):
        obj = after_map.get(object_id) or before_map.get(object_id)
        if isinstance(obj, InstanceObject):
            for other in list(after.objects) + list(before.objects):
                if isinstance(other, RelationObject) and object_id in {
                    str(other.source_id),
                    str(other.target_id),
                }:
                    impacted.add(str(other.id))
                elif isinstance(other, AttributeValueObject) and str(other.subject_id) == object_id:
                    impacted.add(str(other.id))
        if isinstance(obj, RelationTypeObject):
            for other in list(after.objects) + list(before.objects):
                if isinstance(other, RelationObject) and str(other.relation_type_id) == object_id:
                    impacted.add(str(other.id))

    existing = set(after_map) | set(before_map)
    impacted &= existing

    before_warnings = {warning_signature(item) for item in validate_state(before).warnings}
    after_warnings = {warning_signature(item) for item in validate_state(after).warnings}

    return {
        "object_ids": sorted(impacted),
        "instance_ids": sorted(
            object_id for object_id in impacted if getattr(after_map.get(object_id), "kind", None) == "instance"
            or getattr(before_map.get(object_id), "kind", None) == "instance"
        ),
        "assertion_ids": sorted(
            object_id
            for object_id in impacted
            if getattr(after_map.get(object_id), "kind", None)
            in {"relation", "attribute_value"}
            or getattr(before_map.get(object_id), "kind", None)
            in {"relation", "attribute_value"}
        ),
        "warning_counts": {"before": len(before_warnings), "after": len(after_warnings)},
        "warnings_added": sorted(after_warnings - before_warnings),
        "warnings_removed": sorted(before_warnings - after_warnings),
    }
