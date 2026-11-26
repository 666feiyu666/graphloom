from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import UUID, uuid4

from .domain.graph import GraphState, empty_state


class ProjectNotFound(Exception):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DataStore:
    """One JSON file per project, written atomically with a previous-state backup."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    # -- paths ---------------------------------------------------------------
    def _path(self, project_id: str) -> Path:
        return self.data_dir / f"{project_id}.json"

    def _layout_path(self, project_id: str) -> Path:
        return self.data_dir / f"{project_id}.layout.json"

    def _backup_path(self, project_id: str) -> Path:
        return self.data_dir / f"{project_id}.bak"

    # -- low-level IO --------------------------------------------------------
    def _load_raw(self, project_id: str) -> dict:
        path = self._path(project_id)
        if not path.exists():
            raise ProjectNotFound(project_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_atomic(self, path: Path, payload: dict, *, backup: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if backup and path.exists():
            shutil.copyfile(path, path.with_name(path.stem + ".bak"))
        tmp = path.with_name(path.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)

    # -- projects ------------------------------------------------------------
    def list_projects(self) -> list[dict]:
        projects: list[dict] = []
        for path in sorted(self.data_dir.glob("*.json")):
            if path.name.endswith(".layout.json"):
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            projects.append(self._meta(raw))
        projects.sort(key=lambda item: item["created_at"])
        return projects

    def create_project(self, name: str, description: str = "") -> dict:
        project_id = str(uuid4())
        stamp = _now_iso()
        payload = {
            "format_version": 1,
            "id": project_id,
            "name": name,
            "description": description,
            "created_at": stamp,
            "updated_at": stamp,
            "version": 0,
            "saved_at": stamp,
            "objects": [],
        }
        with self._lock:
            self._write_atomic(self._path(project_id), payload)
        return self._meta(payload)

    def get_project(self, project_id: str) -> dict:
        return self._meta(self._load_raw(project_id))

    def read_state(self, project_id: str) -> GraphState:
        raw = self._load_raw(project_id)
        return GraphState(
            format_version=raw.get("format_version", 1),
            project_id=UUID(raw["id"]),
            objects=raw.get("objects", []),
        )

    def save_state(self, project_id: str, state: GraphState) -> dict:
        with self._lock:
            raw = self._load_raw(project_id)
            stamp = _now_iso()
            version = int(raw.get("version", 0)) + 1
            payload = {
                **raw,
                "updated_at": stamp,
                "version": version,
                "saved_at": stamp,
                "objects": json.loads(state.model_dump_json())["objects"],
            }
            self._write_atomic(self._path(project_id), payload, backup=True)
        return self._meta(payload)

    def get_layout(self, project_id: str) -> dict:
        self._load_raw(project_id)  # 404 if the project is gone
        path = self._layout_path(project_id)
        if not path.exists():
            return {"project_id": project_id, "data": {}}
        return {"project_id": project_id, "data": json.loads(path.read_text(encoding="utf-8"))}

    def save_layout(self, project_id: str, data: dict) -> dict:
        self._load_raw(project_id)
        with self._lock:
            self._write_atomic(self._layout_path(project_id), data)
        return {"project_id": project_id, "data": data}

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _meta(raw: dict) -> dict:
        objects = raw.get("objects", [])
        counts = {"objects": len(objects), "classes": 0, "instances": 0, "relations": 0, "assertions": 0}
        for obj in objects:
            kind = obj.get("kind")
            if kind == "class":
                counts["classes"] += 1
            elif kind == "instance":
                counts["instances"] += 1
            elif kind == "relation":
                counts["relations"] += 1
                counts["assertions"] += 1
            elif kind == "attribute_value":
                counts["assertions"] += 1
        return {
            "id": raw["id"],
            "name": raw["name"],
            "description": raw.get("description", ""),
            "version": int(raw.get("version", 0)),
            "saved_at": raw.get("saved_at"),
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
            "counts": counts,
        }
