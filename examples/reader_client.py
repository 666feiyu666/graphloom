#!/usr/bin/env python3
"""Small read-only Graphloom consumer.

This example shows the contract a consuming agent uses:
select a project, pin a revision, read schema, retrieve instances and relations,
and inspect a bounded neighborhood. It never prepares or commits an edit and does
not require an OpenAI key or any model call.

Run it with a reader credential:

    python examples/reader_client.py \
      --base-url http://127.0.0.1:8000/api/v1 \
      --token "$GRAPPHLOOM_READER_TOKEN" \
      --project-id "$GRAPPHLOOM_PROJECT_ID"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def get_json(base_url: str, token: str, path: str) -> Any:
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} for {path}: {body}") from exc
    except URLError as exc:
        raise SystemExit(f"Could not reach {base_url}: {exc.reason}") from exc


def read_all_objects(
    base_url: str,
    token: str,
    project_id: str,
    revision: int,
    kind: str,
) -> list[dict]:
    """Follow pagination without changing the pinned revision."""
    objects: list[dict] = []
    cursor: str | None = None
    while True:
        query = f"?kind={kind}&revision={revision}&limit=100"
        if cursor:
            query += f"&cursor={cursor}"
        page = get_json(
            base_url,
            token,
            f"/projects/{project_id}/objects{query}",
        )
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
        "--token",
        default=os.environ.get("GRAPPHLOOM_READER_TOKEN"),
        help="Project-scoped reader token (or GRAPPHLOOM_READER_TOKEN).",
    )
    parser.add_argument(
        "--project-id",
        default=os.environ.get("GRAPPHLOOM_PROJECT_ID"),
        help="Project UUID (or GRAPPHLOOM_PROJECT_ID).",
    )
    args = parser.parse_args(argv)

    if not args.token:
        parser.error("--token or GRAPPHLOOM_READER_TOKEN is required")
    if not args.project_id:
        parser.error("--project-id or GRAPPHLOOM_PROJECT_ID is required")

    base_url = args.base_url
    token = args.token
    project_id = args.project_id

    capabilities = get_json(base_url, token, "/capabilities")
    project = get_json(base_url, token, f"/projects/{project_id}")

    # Pin the revision before reading anything else. All remaining reads use it.
    pinned_state = get_json(
        base_url,
        token,
        f"/projects/{project_id}/state?revision={project['current_revision']}",
    )
    revision = pinned_state["revision"]
    schema = get_json(
        base_url,
        token,
        f"/projects/{project_id}/schema?revision={revision}",
    )
    instances = read_all_objects(base_url, token, project_id, revision, "instance")
    relations = read_all_objects(base_url, token, project_id, revision, "relation")

    neighborhood = None
    if instances:
        # POST /query is read-only even though it uses HTTP POST.
        query_request = Request(
            f"{base_url.rstrip('/')}/projects/{project_id}/query",
            data=json.dumps(
                {
                    "revision": revision,
                    "query": {
                        "type": "neighbors",
                        "object_id": instances[0]["id"],
                        "depth": 1,
                        "direction": "both",
                    },
                }
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(query_request, timeout=20) as response:
                neighborhood = json.load(response)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"HTTP {exc.code} for neighborhood query: {body}") from exc

    summary = {
        "role": capabilities["role"],
        "read_only": capabilities["read_only"],
        "project": {
            "id": project["id"],
            "name": project["name"],
            "pinned_revision": revision,
        },
        "schema": {
            "classes": [
                {"id": item["id"], "label": item["label"]}
                for item in schema["classes"]
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
        "full_state_object_count": len(pinned_state["objects"]),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
