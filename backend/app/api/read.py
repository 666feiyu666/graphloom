from __future__ import annotations

import base64
import json

from fastapi import APIRouter, Query

from app.api.deps import ProjectDep, StoreDep
from app.api.errors import ApiError
from app.domain.graph import object_map
from app.domain.queries import instances_of, neighbors, references_of
from app.domain.validation import validate_state

router = APIRouter(prefix="/api/v1")

KINDS = {
    "class",
    "relation_type",
    "attribute_type",
    "instance",
    "relation",
    "attribute_value",
    "source_ref",
}

MAX_PAGE = 500


def _encode_cursor(*, kind: str | None, q: str, after: str) -> str:
    payload = {"k": kind, "q": q, "a": after}
    return base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).decode("ascii")


def _decode_cursor(cursor: str) -> dict:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
    except Exception as exc:  # noqa: BLE001 - malformed opaque cursors are a client error
        raise ApiError(422, "invalid_cursor", "The pagination cursor is not valid") from exc
    if not isinstance(payload, dict):
        raise ApiError(422, "invalid_cursor", "The pagination cursor is not valid")
    return payload


def _search_text(obj) -> str:
    parts: list[str] = []
    for field in ("label", "definition", "notes", "citation_text"):
        value = getattr(obj, field, None)
        if isinstance(value, str):
            parts.append(value)
    aliases = getattr(obj, "aliases", None)
    if aliases:
        parts.extend(str(item) for item in aliases)
    locator = getattr(obj, "locator", None)
    if locator is not None:
        parts.append(locator.value)
    return " ".join(parts).casefold()


@router.get("/projects/{project_id}/state")
def read_state(project: ProjectDep, store: StoreDep) -> dict:
    state = store.read_state(project["id"])
    return {
        "format_version": state.format_version,
        "project_id": str(state.project_id),
        "project_name": project["name"],
        "version": project["version"],
        "saved_at": project["saved_at"],
        "objects": state.model_dump(mode="json")["objects"],
    }


@router.get("/projects/{project_id}/schema")
def read_schema(project: ProjectDep, store: StoreDep) -> dict:
    state = store.read_state(project["id"])
    validation = validate_state(state)
    classes = [obj.model_dump(mode="json") for obj in state.objects if obj.kind == "class"]
    relation_types = [
        obj.model_dump(mode="json") for obj in state.objects if obj.kind == "relation_type"
    ]
    attribute_types = [
        obj.model_dump(mode="json") for obj in state.objects if obj.kind == "attribute_type"
    ]
    source_refs = [
        obj.model_dump(mode="json") for obj in state.objects if obj.kind == "source_ref"
    ]
    return {
        "project_id": project["id"],
        "version": project["version"],
        "saved_at": project["saved_at"],
        "classes": classes,
        "relation_types": relation_types,
        "attribute_types": attribute_types,
        "source_refs": source_refs,
        "warnings": validation.warnings,
        "counts": {
            "classes": len(classes),
            "relation_types": len(relation_types),
            "attribute_types": len(attribute_types),
            "source_refs": len(source_refs),
        },
    }


@router.get("/projects/{project_id}/objects")
def read_objects(
    project: ProjectDep,
    store: StoreDep,
    kind: str | None = Query(default=None),
    q: str = Query(default=""),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE),
) -> dict:
    if kind is not None and kind not in KINDS:
        raise ApiError(422, "invalid_kind", "Unknown object kind", {"kind": kind})

    cursor_payload = _decode_cursor(cursor) if cursor else None
    if cursor_payload is not None:
        if kind is not None and kind != cursor_payload.get("k"):
            raise ApiError(422, "cursor_filter_mismatch", "The cursor is bound to a different kind filter")
        if q and q != cursor_payload.get("q"):
            raise ApiError(422, "cursor_filter_mismatch", "The cursor is bound to a different search")
        kind = cursor_payload.get("k")
        q = cursor_payload.get("q", "")

    state = store.read_state(project["id"])
    needle = " ".join(q.casefold().split())
    filtered = []
    for obj in state.objects:
        if kind is not None and obj.kind != kind:
            continue
        if needle and needle not in _search_text(obj):
            continue
        filtered.append(obj)
    filtered.sort(key=lambda item: str(item.id))

    after = cursor_payload.get("a") if cursor_payload else None
    if after:
        filtered = [obj for obj in filtered if str(obj.id) > after]

    page = filtered[:limit]
    has_more = len(filtered) > limit
    next_cursor = (
        _encode_cursor(kind=kind, q=q, after=str(page[-1].id))
        if has_more and page
        else None
    )
    return {
        "project_id": project["id"],
        "version": project["version"],
        "saved_at": project["saved_at"],
        "kind": kind,
        "q": q,
        "objects": [obj.model_dump(mode="json") for obj in page],
        "returned_count": len(page),
        "total_matching": len(filtered),
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


@router.get("/projects/{project_id}/objects/{object_id}")
def read_object(project: ProjectDep, store: StoreDep, object_id: str) -> dict:
    state = store.read_state(project["id"])
    obj = object_map(state).get(object_id)
    if obj is None:
        raise ApiError(404, "object_not_found", "Object does not exist", {"object_id": object_id})
    return {
        "project_id": project["id"],
        "version": project["version"],
        "saved_at": project["saved_at"],
        "object": obj.model_dump(mode="json"),
    }


@router.get("/projects/{project_id}/neighborhood")
def read_neighborhood(
    project: ProjectDep,
    store: StoreDep,
    id: str = Query(...),
    depth: int = Query(default=1, ge=1, le=2),
    direction: str = Query(default="both", pattern="^(incoming|outgoing|both)$"),
    relation_type: list[str] | None = Query(default=None),
) -> dict:
    state = store.read_state(project["id"])
    return {
        "project_id": project["id"],
        "version": project["version"],
        "saved_at": project["saved_at"],
        **neighbors(
            state,
            id,
            direction=direction,
            relation_type_ids=relation_type or [],
            depth=depth,
        ),
    }


@router.get("/projects/{project_id}/instances")
def read_instances(
    project: ProjectDep,
    store: StoreDep,
    class_id: str = Query(...),
    include_descendants: bool = Query(default=True),
) -> dict:
    state = store.read_state(project["id"])
    return {
        "project_id": project["id"],
        "version": project["version"],
        "saved_at": project["saved_at"],
        **instances_of(state, class_id, include_descendants=include_descendants),
    }


@router.get("/projects/{project_id}/references")
def read_references(project: ProjectDep, store: StoreDep, id: str = Query(...)) -> dict:
    state = store.read_state(project["id"])
    return {
        "project_id": project["id"],
        "version": project["version"],
        "saved_at": project["saved_at"],
        **references_of(state, id),
    }
