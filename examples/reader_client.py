#!/usr/bin/env python3
"""Small read-only Graphloom consumer.

This example shows the contract a consuming agent uses: select a project, read
the current version, read schema, retrieve instances and relations, and inspect
a bounded neighborhood. It never writes and needs no credential or model call.

Run it against a locally running backend:

    python examples/reader_client.py \
      --base-url http://127.0.0.1:8000/api/v1 \
      --project-id "$GRAPPHLOOM_PROJECT_ID"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def get_json(base_url: str, path: str, params: dict[str, Any] | None = None) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    if params:
        url += f"?{urlencode(params, doseq=True)}"
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} for {path}: {body}") from exc
    except URLError as exc:
        raise SystemExit(f"Could not reach {base_url}: {exc.reason}") from exc


def read_all_objects(
    base_url: str, project_id: str, kind: str
) -> list[dict]:
    """Follow pagination across the current saved state."""
    objects: list[dict] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"kind": kind, "limit": 100}
        if cursor:
            params["cursor"] = cursor
        page = get_json(base_url, f"/projects/{project_id}/objects", params)
        objects.extend(page["objects"])
        cursor = page.get("next_cursor")
        if not cursor:
            if page.get("has_more"):
                raise SystemExit("Pagination ended while the response still reported more rows")
            return objects


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("GRAPPHLOOM_BASE_URL", "http://127.0.0.1:8000/api/v1"),
    )
    parser.add_argument(
        "--project-id",
        default=os.environ.get("GRAPPHLOOM_PROJECT_ID"),
        help="Project UUID (or GRAPPHLOOM_PROJECT_ID).",
    )
    args = parser.parse_args(argv)

    if not args.project_id:
        parser.error("--project-id or GRAPPHLOOM_PROJECT_ID is required")

    base_url = args.base_url
    project_id = args.project_id

    capabilities = get_json(base_url, "/capabilities")
    project = get_json(base_url, f"/projects/{project_id}")
    version = project["version"]

    state = get_json(base_url, f"/projects/{project_id}/state")
    schema = get_json(base_url, f"/projects/{project_id}/schema")
    instances = read_all_objects(base_url, project_id, "instance")
    relations = read_all_objects(base_url, project_id, "relation")

    neighborhood = None
    if instances:
        neighborhood = get_json(
            base_url,
            f"/projects/{project_id}/neighborhood",
            {"id": instances[0]["id"], "depth": 1, "direction": "both"},
        )

    summary = {
        "read_only": True,
        "api_version": capabilities["api_version"],
        "project": {
            "id": project["id"],
            "name": project["name"],
            "version": version,
        },
        "schema": {
            "classes": [
                {"id": item["id"], "label": item["label"]} for item in schema["classes"]
            ],
            "relation_types": [
                {"id": item["id"], "label": item["label"]}
                for item in schema["relation_types"]
            ],
            "attribute_types": [
                {"id": item["id"], "label": item["label"]}
                for item in schema["attribute_types"]
            ],
            "warnings": schema["warnings"],
        },
        "instances": [
            {
                "id": item["id"],
                "label": item["label"],
                "class_ids": item["class_ids"],
                "source_ref_ids": item["source_ref_ids"],
            }
            for item in instances
        ],
        "relations": [
            {
                "id": item["id"],
                "source_id": item["source_id"],
                "relation_type_id": item["relation_type_id"],
                "target_id": item["target_id"],
            }
            for item in relations
        ],
        "neighborhood": neighborhood,
        "full_state_object_count": len(state["objects"]),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
