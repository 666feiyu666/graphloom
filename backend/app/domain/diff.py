from __future__ import annotations

from typing import Any

from .graph import display_label, object_map
from .objects import GraphObject


def _serialize(obj: GraphObject) -> dict[str, Any]:
    return obj.model_dump(mode="json")


def diff_states(before, after) -> dict:
    before_map = object_map(before)
    after_map = object_map(after)

    added_ids = sorted(set(after_map) - set(before_map))
    removed_ids = sorted(set(before_map) - set(after_map))
    common_ids = sorted(set(before_map) & set(after_map))

    added = []
    for object_id in added_ids:
        obj = after_map[object_id]
        added.append(
            {
                "id": object_id,
                "kind": obj.kind,
                "label": display_label(obj),
                "object": _serialize(obj),
            }
        )

    removed = []
    for object_id in removed_ids:
        obj = before_map[object_id]
        removed.append(
            {
                "id": object_id,
                "kind": obj.kind,
                "label": display_label(obj),
                "object": _serialize(obj),
            }
        )

    changed = []
    for object_id in common_ids:
        old = _serialize(before_map[object_id])
        new = _serialize(after_map[object_id])
        if old == new:
            continue
        field_changes = {}
        for key in sorted(set(old) | set(new)):
            if old.get(key) != new.get(key):
                field_changes[key] = {"before": old.get(key), "after": new.get(key)}
        if field_changes:
            changed.append(
                {
                    "id": object_id,
                    "kind": after_map[object_id].kind,
                    "label": display_label(after_map[object_id]),
                    "fields": field_changes,
                }
            )

    return {
        "from_revision": before.revision,
        "to_revision": after.revision,
        "added": added,
        "removed": removed,
        "changed": changed,
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
        },
    }


def diff_is_empty(diff: dict) -> bool:
    counts = diff.get("counts", {})
    return not counts.get("added") and not counts.get("removed") and not counts.get("changed")
