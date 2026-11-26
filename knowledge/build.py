#!/usr/bin/env python3
"""Generic knowledge-graph builder.

Turns a case directory of declarative JSON — ontology.json, sources.json,
data.json — into a Graphloom project. Stable author-facing slugs in the JSON are
mapped to UUIDs by the backend.

    cd graphloom/backend && uv run python ../knowledge/build.py --case banksy
    cd graphloom/backend && uv run python ../knowledge/build.py --case banksy --replace
    cd graphloom/backend && uv run python ../knowledge/build.py --case banksy --data-dir .local/dev
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

GRAPHLOOM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GRAPHLOOM_DIR / "backend"))

from app.config import Settings  # noqa: E402
from app.domain.graph import empty_state  # noqa: E402
from app.domain.operations import BatchEnvelope, apply_operations  # noqa: E402
from app.domain.validation import validate_state  # noqa: E402
from app.storage import DataStore  # noqa: E402


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def new_ref(slug: str) -> str:
    return f"new:{slug}"


def build_operations(ontology: dict, sources: dict, data: dict) -> list[dict]:
    ops: list[dict] = []

    for cls in ontology["classes"]:
        ops.append(
            {
                "op": "create",
                "ref": new_ref(cls["id"]),
                "kind": "class",
                "data": {
                    "label": cls["label"],
                    "definition": cls.get("definition", ""),
                    "aliases": cls.get("aliases", []),
                    "parent_ids": [new_ref(parent) for parent in cls.get("parents", [])],
                    "notes": cls.get("notes", ""),
                },
            }
        )

    for relation_type in ontology["relation_types"]:
        ops.append(
            {
                "op": "create",
                "ref": new_ref(relation_type["id"]),
                "kind": "relation_type",
                "data": {
                    "label": relation_type["label"],
                    "definition": relation_type.get("definition", ""),
                    "domain_ids": [new_ref(item) for item in relation_type.get("domain", [])],
                    "range_ids": [new_ref(item) for item in relation_type.get("range", [])],
                },
            }
        )

    for attribute_type in ontology["attribute_types"]:
        ops.append(
            {
                "op": "create",
                "ref": new_ref(attribute_type["id"]),
                "kind": "attribute_type",
                "data": {
                    "label": attribute_type["label"],
                    "definition": attribute_type.get("definition", ""),
                    "domain_ids": [new_ref(item) for item in attribute_type.get("domain", [])],
                    "value_type": attribute_type["value_type"],
                },
            }
        )

    for source in sources.get("sources", []):
        ops.append(
            {
                "op": "create",
                "ref": new_ref(source["id"]),
                "kind": "source_ref",
                "data": {
                    "label": source["label"],
                    "locator": source["locator"],
                    "citation_text": source.get("citation_text", ""),
                    "evidence_state": source.get("evidence_state", "unverified"),
                },
            }
        )

    for instance in data["instances"]:
        ops.append(
            {
                "op": "create",
                "ref": new_ref(instance["id"]),
                "kind": "instance",
                "data": {
                    "label": instance["label"],
                    "definition": instance.get("definition", ""),
                    "aliases": instance.get("aliases", []),
                    "class_ids": [new_ref(item) for item in instance["classes"]],
                    "notes": instance.get("notes", ""),
                    "source_ref_ids": [new_ref(item) for item in instance.get("sources", [])],
                },
            }
        )

    for relation in data.get("relations", []):
        ops.append(
            {
                "op": "create",
                "ref": new_ref(relation["id"]),
                "kind": "relation",
                "data": {
                    "source_id": new_ref(relation["source"]),
                    "relation_type_id": new_ref(relation["type"]),
                    "target_id": new_ref(relation["target"]),
                    "notes": relation.get("notes", ""),
                    "source_ref_ids": [new_ref(item) for item in relation.get("sources", [])],
                },
            }
        )

    for value in data.get("attribute_values", []):
        ops.append(
            {
                "op": "create",
                "ref": new_ref(value["id"]),
                "kind": "attribute_value",
                "data": {
                    "subject_id": new_ref(value["subject"]),
                    "attribute_type_id": new_ref(value["attribute"]),
                    "value": value["value"],
                    "notes": value.get("notes", ""),
                    "source_ref_ids": [new_ref(item) for item in value.get("sources", [])],
                },
            }
        )

    return ops


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="banksy", help="Directory under knowledge/.")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--profile", choices=["prod", "dev"], default="prod")
    parser.add_argument("--replace", action="store_true", help="Rebuild an existing project with the same name.")
    args = parser.parse_args(argv)

    case_dir = GRAPHLOOM_DIR / "knowledge" / args.case
    if not case_dir.is_dir():
        raise SystemExit(f"Case directory not found: {case_dir}")

    ontology = load_json(case_dir / "ontology.json")
    sources = load_json(case_dir / "sources.json")
    data = load_json(case_dir / "data.json")

    settings = Settings(profile=args.profile, data_dir=args.data_dir)
    store = DataStore(settings.resolved_data_dir)
    name = ontology["project"]["name"]
    description = ontology["project"].get("description", "")

    existing = [item for item in store.list_projects() if item["name"] == name]
    created = False
    if existing and not args.replace:
        print(json.dumps({"status": "exists", "project_id": existing[0]["id"], "version": existing[0]["version"]}, indent=2))
        return 0
    if existing:
        project = existing[0]
        base = empty_state(UUID(project["id"]))
    else:
        project = store.create_project(name, description)
        base = store.read_state(project["id"])
        created = True

    applied = apply_operations(base, BatchEnvelope(operations=build_operations(ontology, sources, data)).operations)
    validation = validate_state(applied.state, deleted_ids=applied.deleted_ids)
    errors = applied.errors + validation.errors
    if errors:
        if created:
            (store.data_dir / f"{project['id']}.json").unlink(missing_ok=True)
        raise SystemExit(f"Build failed: {json.dumps(errors, ensure_ascii=False, indent=2)}")

    meta = store.save_state(project["id"], applied.state)
    print(
        json.dumps(
            {
                "status": "built",
                "case": args.case,
                "project_id": project["id"],
                "project_name": meta["name"],
                "data_dir": str(settings.resolved_data_dir),
                "version": meta["version"],
                "objects": meta["counts"]["objects"],
                "classes": meta["counts"]["classes"],
                "instances": meta["counts"]["instances"],
                "relations": meta["counts"]["relations"],
                "warnings": len(validation.warnings),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
