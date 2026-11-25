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


def seed_graph(client: httpx.Client, project_id: str, owner_headers: dict[str, str]) -> None:
    operations = [
        {
            "op": "create",
            "ref": "new:class",
            "kind": "class",
            "data": {
                "label": "Integration category",
                "definition": "Synthetic integration fixture.",
            },
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
    prepared = client.post(
        f"/projects/{project_id}/change-sets",
        json={"base_revision": 0, "reason": "Integration fixture", "operations": operations},
        headers=owner_headers,
    )
    assert prepared.status_code == 201, prepared.text
    change_set = prepared.json()
    assert change_set["status"] == "prepared", change_set
    committed = client.post(
        f"/projects/{project_id}/change-sets/{change_set['id']}/commit",
        json={"expected_revision": 0},
        headers={**owner_headers, "Idempotency-Key": "integration-seed"},
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["revision"] == 1


def test_reader_process_and_pinned_revision(tmp_path):
    port = free_port()
    base_url = f"http://127.0.0.1:{port}/api/v1"
    db_path = tmp_path / "integration.db"
    env = os.environ.copy()
    env.update(
        {
            "GRAPPHLOOM_DB_PATH": str(db_path),
            "GRAPPHLOOM_FRONTEND_DIST": str(tmp_path / "dist"),
            "GRAPPHLOOM_RATE_LIMIT_PER_MINUTE": "100000",
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        }
    )

    owner = subprocess.run(
        [sys.executable, "-m", "app.cli", "init-owner", "--label", "owner"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert owner.returncode == 0, f"stdout:\n{owner.stdout}\nstderr:\n{owner.stderr}"
    owner_token = json.loads(owner.stdout)["token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

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
                headers=owner_headers,
            )
            assert project_response.status_code == 201, project_response.text
            project_id = project_response.json()["id"]
            seed_graph(client, project_id, owner_headers)

            credential_response = client.post(
                "/credentials",
                json={"label": "integration reader", "project_ids": [project_id]},
                headers=owner_headers,
            )
            assert credential_response.status_code == 200, credential_response.text
            credential = credential_response.json()
            reader_token = credential["token"]
            reader_headers = {"Authorization": f"Bearer {reader_token}"}

            # The example runs as a separate process and uses the public HTTP contract.
            example = subprocess.run(
                [
                    sys.executable,
                    str(READER_CLIENT),
                    "--base-url",
                    base_url,
                    "--token",
                    reader_token,
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
            assert summary["role"] == "reader"
            assert summary["read_only"] is True
            assert summary["project"]["id"] == project_id
            assert summary["project"]["pinned_revision"] == 1
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

            # A reader credential cannot write or manage any owner operation.
            forbidden_change_set = client.post(
                f"/projects/{project_id}/change-sets",
                json={"base_revision": 1, "reason": "", "operations": []},
                headers=reader_headers,
            )
            assert forbidden_change_set.status_code == 403
            assert forbidden_change_set.json()["error"]["code"] == "owner_required"
            assert client.post(
                "/projects", json={"name": "forbidden"}, headers=reader_headers
            ).status_code == 403
            assert client.get("/credentials", headers=reader_headers).status_code == 403
            assert client.put(
                f"/projects/{project_id}/layout",
                json={"expected_version": 0, "data": {}},
                headers=reader_headers,
            ).status_code == 403

            # A reader-only OpenAPI document exists and omits owner editing routes.
            reader_spec = client.get("/openapi.reader.json")
            assert reader_spec.status_code == 200
            spec = reader_spec.json()
            assert spec["x-graphloom-read-only"] is True
            assert "/api/v1/projects" in spec["paths"]
            assert set(spec["paths"]["/api/v1/projects"]) == {"get"}
            assert not any("change-sets" in path for path in spec["paths"])
            assert not any("credentials" in path for path in spec["paths"])

            # An owner can advance the project while a reader keeps an older pin.
            advance = client.post(
                f"/projects/{project_id}/change-sets",
                json={
                    "base_revision": 1,
                    "reason": "Advance after reader pin",
                    "operations": [
                        {
                            "op": "create",
                            "ref": "new:later",
                            "kind": "class",
                            "data": {
                                "label": "Later integration class",
                                "definition": "Synthetic integration fixture.",
                            },
                        }
                    ],
                },
                headers=owner_headers,
            )
            assert advance.status_code == 201
            advance_payload = advance.json()
            assert advance_payload["status"] == "prepared", advance_payload
            advanced = client.post(
                f"/projects/{project_id}/change-sets/{advance_payload['id']}/commit",
                json={"expected_revision": 1},
                headers={**owner_headers, "Idempotency-Key": "integration-advance"},
            )
            assert advanced.status_code == 200
            assert advanced.json()["revision"] == 2

            pinned = client.get(f"/projects/{project_id}/state?revision=1", headers=reader_headers)
            assert pinned.status_code == 200
            assert pinned.json()["revision"] == 1
            assert len(pinned.json()["objects"]) == 8
            current = client.get(f"/projects/{project_id}/state", headers=reader_headers)
            assert current.json()["revision"] == 2

            # Revocation immediately ends the reader session.
            revoke = client.delete(
                f"/credentials/{credential['id']}", headers=owner_headers
            )
            assert revoke.status_code == 200
            assert client.get(
                f"/projects/{project_id}/state", headers=reader_headers
            ).status_code == 401
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
