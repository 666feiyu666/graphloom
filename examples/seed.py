#!/usr/bin/env python3
"""Seed a synthetic project into the development data store.

This is throwaway development data: it writes to `.local/dev` by default and
refuses to touch the production store (`.local/projects`) unless `--force` is
given. Nothing here is a research finding.

    cd graphloom/backend && uv run python ../examples/seed.py
    cd graphloom/backend && uv run python ../examples/seed.py --data-dir /tmp/graphloom-demo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

GRAPHLOOM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GRAPHLOOM_DIR / "backend"))

from app.config import PRODUCTION_DATA_DIR, Settings  # noqa: E402
from app.domain.operations import BatchEnvelope, apply_operations  # noqa: E402
from app.domain.validation import validate_state  # noqa: E402
from app.storage import DataStore  # noqa: E402


def synthetic_operations() -> list[dict]:
    return [
        {
            "op": "create",
            "ref": "new:class",
            "kind": "class",
            "data": {"label": "Synthetic category", "definition": "Development fixture; not a research claim."},
        },
        {
            "op": "create",
            "ref": "new:rel",
            "kind": "relation_type",
            "data": {
                "label": "Synthetic relation",
                "definition": "Development fixture.",
                "domain_ids": ["new:class"],
                "range_ids": ["new:class"],
            },
        },
        {
            "op": "create",
            "ref": "new:a",
            "kind": "instance",
            "data": {
                "label": "Synthetic A",
                "definition": "Development fixture.",
                "class_ids": ["new:class"],
            },
        },
        {
            "op": "create",
            "ref": "new:b",
            "kind": "instance",
            "data": {
                "label": "Synthetic B",
                "definition": "Development fixture.",
                "class_ids": ["new:class"],
            },
        },
        {
            "op": "create",
            "ref": "new:relationship",
            "kind": "relation",
            "data": {"source_id": "new:a", "relation_type_id": "new:rel", "target_id": "new:b"},
        },
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["dev", "prod"], default="dev")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--name", default="Synthetic development project")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow writing to the production data directory (.local/projects).",
    )
    args = parser.parse_args(argv)

    settings = Settings(profile=args.profile, data_dir=args.data_dir)
    data_dir = settings.resolved_data_dir

    if data_dir.resolve() == PRODUCTION_DATA_DIR.resolve() and not args.force:
        parser.error(
            "Refusing to seed the production data directory; pass --force if this is intentional."
        )

    store = DataStore(data_dir)
    project = store.create_project(args.name, "Synthetic fixture; not research data.")
    base = store.read_state(project["id"])
    envelope = BatchEnvelope(operations=synthetic_operations())
    applied = apply_operations(base, envelope.operations)
    validation = validate_state(applied.state, deleted_ids=applied.deleted_ids)
    errors = applied.errors + validation.errors
    if errors:
        raise SystemExit(f"Seed failed: {errors}")

    meta = store.save_state(project["id"], applied.state)
    print(
        json.dumps(
            {
                "project_id": project["id"],
                "project_name": meta["name"],
                "data_dir": str(data_dir),
                "version": meta["version"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
