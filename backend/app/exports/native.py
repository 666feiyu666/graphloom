from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from app.domain.graph import GraphState


class ImportValidationError(Exception):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


def build_native_export(
    project,
    state: GraphState,
    *,
    include_layout: bool = False,
    layout: dict | None = None,
) -> dict:
    payload = {
        "format": "graphloom-native",
        "format_version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "project": {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "revision": state.revision,
        },
        "graph": {
            "format_version": 1,
            "project_id": str(state.project_id),
            "revision": state.revision,
            "objects": json.loads(state.model_dump_json())["objects"],
        },
    }
    if include_layout and layout is not None:
        payload["layout"] = layout
    return payload


def parse_native_import(payload: dict, target_project_id: str) -> tuple[GraphState, dict]:
    if not isinstance(payload, dict):
        raise ImportValidationError("Native import payload must be a JSON object")
    if payload.get("format") != "graphloom-native":
        raise ImportValidationError("Expected format 'graphloom-native'")
    if payload.get("format_version") != 1:
        raise ImportValidationError(
            "Unsupported native format version",
            {"format_version": payload.get("format_version")},
        )

    graph = payload.get("graph")
    if not isinstance(graph, dict):
        raise ImportValidationError("Native import payload is missing 'graph'")
    if graph.get("format_version") not in (None, 1):
        raise ImportValidationError(
            "Unsupported graph format version",
            {"format_version": graph.get("format_version")},
        )
    objects = graph.get("objects")
    if not isinstance(objects, list):
        raise ImportValidationError("Native import payload is missing graph.objects")

    rewritten = []
    for item in objects:
        if not isinstance(item, dict) or "id" not in item:
            raise ImportValidationError("Every graph object must be a JSON object with an id")
        copied = dict(item)
        copied["project_id"] = target_project_id
        rewritten.append(copied)

    try:
        state = GraphState.model_validate(
            {
                "format_version": 1,
                "project_id": target_project_id,
                "revision": 0,
                "objects": rewritten,
            }
        )
    except Exception as exc:  # pydantic ValidationError
        details = {}
        errors = getattr(exc, "errors", None)
        if callable(errors):
            details = {"errors": errors(include_url=False, include_context=False)}
        else:
            details = {"message": str(exc)}
        raise ImportValidationError("Imported graph objects are malformed", details) from exc

    project_meta = payload.get("project") if isinstance(payload.get("project"), dict) else {}
    source = {
        "project_id": project_meta.get("id"),
        "project_name": project_meta.get("name"),
        "revision": graph.get("revision", project_meta.get("revision")),
    }
    return state, source


def json_loads(raw: bytes) -> dict:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImportValidationError("Request body is not valid JSON", {"message": str(exc)}) from exc
    if not isinstance(value, dict):
        raise ImportValidationError("Request body must be a JSON object")
    return value
