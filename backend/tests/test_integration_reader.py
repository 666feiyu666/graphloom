from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
READER_CLIENT = PROJECT_DIR / "examples" / "reader_client.py"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_health(base_url: str, process: subprocess.Popen, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=5)
            pytest.fail(f"uvicorn exited early\nstdout:\n{stdout}\nstderr:\n{stderr}")
        try:
            response = httpx.get(f"{base_url}/health", timeout=1.0, trust_env=False)
            if response.status_code == 200:
                return
        except Exception as exc:  # noqa: BLE001 - startup polling
            last_error = exc
        time.sleep(0.15)
    pytest.fail(f"Graphloom did not become healthy: {last_error}")


def seed_graph(client: httpx.Client, project_id: str) -> None:
    operations = [
        {
            "op": "create",
            "ref": "new:class",
            "kind": "class",
            "data": {"label": "Integration category", "definition": "Synthetic integration fixture."},
        },
        {
            "op": "create",
            "ref": "new:rel",
            "kind": "relation_type",
            "data": {
                "label": "Integration relation",
                "definition": "Synthetic integration fixture.",
                "domain_ids": ["new:class"],
                "range_ids": ["new:class"],
            },
        },
        {
            "op": "create",
            "ref": "new:attr",
            "kind": "attribute_type",
            "data": {
                "label": "Integration caption",
                "definition": "Synthetic integration fixture.",
                "domain_ids": ["new:class"],
                "value_type": "string",
            },
        },
        {
            "op": "create",
            "ref": "new:source",
            "kind": "source_ref",
            "data": {
                "label": "Integration source",
                "locator": {"kind": "url", "value": "https://example.invalid/integration"},
                "citation_text": "Synthetic citation.",
                "evidence_state": "unverified",
            },
        },
        {
            "op": "create",
            "ref": "new:a",
            "kind": "instance",
            "data": {
                "label": "Integration Alpha",
                "definition": "Synthetic integration instance.",
                "class_ids": ["new:class"],
                "source_ref_ids": ["new:source"],
            },
        },
        {
            "op": "create",
            "ref": "new:b",
            "kind": "instance",
            "data": {
                "label": "Integration Beta",
                "definition": "Synthetic integration instance.",
                "class_ids": ["new:class"],
            },
        },
        {
            "op": "create",
            "ref": "new:relation",
            "kind": "relation",
            "data": {
                "source_id": "new:a",
                "relation_type_id": "new:rel",
                "target_id": "new:b",
                "notes": "Synthetic integration assertion.",
            },
        },
        {
            "op": "create",
            "ref": "new:value",
            "kind": "attribute_value",
            "data": {
                "subject_id": "new:a",
                "attribute_type_id": "new:attr",
                "value": "Synthetic integration caption",
            },
        },
    ]
    response = client.post(f"/projects/{project_id}/batch", json={"operations": operations})
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 1


def test_reader_process_reads_saved_graph(tmp_path):
    port = free_port()
    base_url = f"http://127.0.0.1:{port}/api/v1"
    data_dir = tmp_path / "projects"
    env = os.environ.copy()
    env.update(
        {
            "GRAPPHLOOM_DATA_DIR": str(data_dir),
            "GRAPPHLOOM_FRONTEND_DIST": str(tmp_path / "dist"),
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        }
    )

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=BACKEND_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_health(base_url, process)
        with httpx.Client(base_url=base_url, timeout=10.0, trust_env=False) as client:
            project_response = client.post(
                "/projects",
                json={"name": "Integration project", "description": "Synthetic technical fixture"},
            )
            assert project_response.status_code == 201, project_response.text
            project_id = project_response.json()["id"]
            seed_graph(client, project_id)

            # The example runs as a separate process and uses only the read contract.
            example = subprocess.run(
                [
                    sys.executable,
                    str(READER_CLIENT),
                    "--base-url",
                    base_url,
                    "--project-id",
                    project_id,
                ],
                cwd=PROJECT_DIR,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert example.returncode == 0, f"stdout:\n{example.stdout}\nstderr:\n{example.stderr}"
            summary = json.loads(example.stdout)
            assert summary["read_only"] is True
            assert summary["project"]["id"] == project_id
            assert summary["project"]["version"] == 1
            assert summary["full_state_object_count"] == 8
            assert {item["label"] for item in summary["schema"]["classes"]} == {
                "Integration category"
            }
            assert {item["label"] for item in summary["instances"]} == {
                "Integration Alpha",
                "Integration Beta",
            }
            assert len(summary["relations"]) == 1
            assert summary["neighborhood"]["query_type"] == "neighbors"
            neighborhood_labels = {
                item.get("label") for item in summary["neighborhood"]["objects"]
            }
            assert {"Integration Alpha", "Integration Beta"} <= neighborhood_labels

            # The reader-only OpenAPI omits the write route.
            reader_spec = client.get("/openapi.reader.json")
            assert reader_spec.status_code == 200
            spec = reader_spec.json()
            assert spec["x-graphloom-read-only"] is True
            assert set(spec["paths"]["/api/v1/projects"]) == {"get"}
            assert "/api/v1/projects/{project_id}/batch" not in spec["paths"]
            assert "/api/v1/projects/{project_id}/layout" not in spec["paths"]
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
