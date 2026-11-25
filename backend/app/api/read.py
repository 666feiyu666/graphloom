from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CredentialDep, DbSession, ProjectDep
from app.api.errors import ApiError
from app.api.schemas import QueryEnvelope
from app.domain.changesets import revision_dict, state_at_revision
from app.domain.diff import diff_states
from app.domain.graph import object_map
from app.domain.objects import Kind
from app.domain.queries import run_query
from app.domain.validation import validate_state
from app.exports.native import build_native_export
from app.exports.turtle import build_turtle_export
from app.storage.models import Layout, Project, Revision, Snapshot

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


def _state_or_404(session: Session, project: Project, revision: int | None):
    state = state_at_revision(session, project, revision)
    if state is None:
        raise ApiError(
            404,
            "revision_not_found",
            "The requested revision does not exist for this project",
            {"revision": revision, "current_revision": project.current_revision},
        )
    return state


def _encode_cursor(*, revision: int, kind: str | None, q: str, after: str) -> str:
    payload = {"r": revision, "k": kind, "q": q, "a": after}
    return base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).decode("ascii")


def _decode_cursor(cursor: str) -> dict:
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(decoded)
    except Exception as exc:  # noqa: BLE001 - malformed opaque cursors are a client error
        raise ApiError(422, "invalid_cursor", "The pagination cursor is not valid") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("r"), int):
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
def read_state(
    project: ProjectDep,
    session: DbSession,
    revision: int | None = Query(default=None, ge=0),
) -> dict:
    state = _state_or_404(session, project, revision)
    return {
        "format_version": state.format_version,
        "project_id": str(state.project_id),
        "project_name": project.name,
        "revision": state.revision,
        "objects": state.model_dump(mode="json")["objects"],
    }


@router.get("/projects/{project_id}/schema")
def read_schema(
    project: ProjectDep,
    session: DbSession,
    revision: int | None = Query(default=None, ge=0),
) -> dict:
    state = _state_or_404(session, project, revision)
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
        "project_id": project.id,
        "revision": state.revision,
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
    session: DbSession,
    kind: str | None = Query(default=None),
    q: str = Query(default=""),
    cursor: str | None = Query(default=None),
    revision: int | None = Query(default=None, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    if kind is not None and kind not in KINDS:
        raise ApiError(422, "invalid_kind", "Unknown object kind", {"kind": kind})

    cursor_payload = _decode_cursor(cursor) if cursor else None
    if cursor_payload is not None:
        if revision is not None and revision != cursor_payload["r"]:
            raise ApiError(
                422,
                "cursor_revision_mismatch",
                "The cursor is bound to a different revision",
                {"cursor_revision": cursor_payload["r"], "requested_revision": revision},
            )
        if kind is not None and kind != cursor_payload.get("k"):
            raise ApiError(422, "cursor_filter_mismatch", "The cursor is bound to a different kind filter")
        if q and q != cursor_payload.get("q"):
            raise ApiError(422, "cursor_filter_mismatch", "The cursor is bound to a different search")
        revision = cursor_payload["r"]
        kind = cursor_payload.get("k")
        q = cursor_payload.get("q", "")

    state = _state_or_404(session, project, revision)
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
        _encode_cursor(
            revision=state.revision,
            kind=kind,
            q=q,
            after=str(page[-1].id),
        )
        if has_more and page
        else None
    )
    return {
        "project_id": project.id,
        "revision": state.revision,
        "kind": kind,
        "q": q,
        "objects": [obj.model_dump(mode="json") for obj in page],
        "returned_count": len(page),
        "total_matching": len(filtered),
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


@router.get("/projects/{project_id}/objects/{object_id}")
def read_object(
    project: ProjectDep,
    session: DbSession,
    object_id: str,
    revision: int | None = Query(default=None, ge=0),
) -> dict:
    state = _state_or_404(session, project, revision)
    obj = object_map(state).get(object_id)
    if obj is None:
        raise ApiError(
            404,
            "object_not_found",
            "Object does not exist at this revision",
            {"object_id": object_id, "revision": state.revision},
        )
    return {
        "project_id": project.id,
        "revision": state.revision,
        "object": obj.model_dump(mode="json"),
    }


@router.post("/projects/{project_id}/query")
def query_graph(
    payload: QueryEnvelope,
    project: ProjectDep,
    session: DbSession,
) -> dict:
    state = _state_or_404(session, project, payload.revision)
    result = run_query(state, payload)
    return {
        "project_id": project.id,
        "revision": state.revision,
        "query": payload.query.model_dump(mode="json"),
        **result,
    }


@router.get("/projects/{project_id}/revisions")
def read_revisions(
    project: ProjectDep,
    session: DbSession,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    rows = session.scalars(
        select(Revision)
        .where(Revision.project_id == project.id, Revision.revision > after)
        .order_by(Revision.revision)
        .limit(limit)
    ).all()
    return {
        "project_id": project.id,
        "current_revision": project.current_revision,
        "revisions": [revision_dict(row) for row in rows],
    }


@router.get("/projects/{project_id}/diff")
def read_diff(
    project: ProjectDep,
    session: DbSession,
    from_revision: int = Query(alias="from", ge=0),
    to_revision: int = Query(alias="to", ge=0),
) -> dict:
    before = _state_or_404(session, project, from_revision)
    after = _state_or_404(session, project, to_revision)
    return {
        "project_id": project.id,
        "from_revision": from_revision,
        "to_revision": to_revision,
        "diff": diff_states(before, after),
    }


@router.get("/projects/{project_id}/export")
def export_state(
    project: ProjectDep,
    session: DbSession,
    credential: CredentialDep,
    format: str = Query(default="native-json"),
    revision: int | None = Query(default=None, ge=0),
    include_layout: bool = Query(default=False),
):
    state = _state_or_404(session, project, revision)
    if format == "native-json":
        layout_payload = None
        if include_layout and credential.role == "owner":
            row = session.get(Layout, project.id)
            layout_payload = json.loads(row.data_json) if row is not None else {}
        payload = build_native_export(
            project,
            state,
            include_layout=layout_payload is not None,
            layout=layout_payload,
        )
        return JSONResponse(payload)
    if format == "turtle":
        turtle = build_turtle_export(project, state)
        return Response(
            content=turtle,
            media_type="text/turtle; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="graphloom-{project.id}-r{state.revision}.ttl"'
            },
        )
    raise ApiError(
        422,
        "unsupported_export_format",
        "Supported export formats are native-json and turtle",
        {"format": format},
    )


@router.get("/projects/{project_id}/snapshots")
def list_snapshots(project: ProjectDep, session: DbSession) -> dict:
    rows = session.scalars(
        select(Snapshot)
        .where(Snapshot.project_id == project.id)
        .order_by(Snapshot.created_at, Snapshot.id)
    ).all()
    return {
        "project_id": project.id,
        "snapshots": [
            {
                "id": row.id,
                "name": row.name,
                "revision": row.revision,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }
