from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import commit, prepare


def base_model_operations():
    return [
        {
            "op": "create",
            "ref": "new:class",
            "kind": "class",
            "data": {
                "label": "Sample category",
                "definition": "Synthetic fixture; not a research claim.",
                "aliases": [],
                "parent_ids": [],
            },
        },
        {
            "op": "create",
            "ref": "new:relation-type",
            "kind": "relation_type",
            "data": {
                "label": "Sample relation",
                "definition": "Synthetic fixture.",
                "domain_ids": ["new:class"],
                "range_ids": ["new:class"],
            },
        },
        {
            "op": "create",
            "ref": "new:a",
            "kind": "instance",
            "data": {
                "label": "Synthetic instance A",
                "definition": "Synthetic fixture.",
                "class_ids": ["new:class"],
            },
        },
        {
            "op": "create",
            "ref": "new:b",
            "kind": "instance",
            "data": {
                "label": "Synthetic instance B",
                "definition": "Synthetic fixture.",
                "class_ids": ["new:class"],
            },
        },
        {
            "op": "create",
            "ref": "new:relation",
            "kind": "relation",
            "data": {
                "source_id": "new:a",
                "relation_type_id": "new:relation-type",
                "target_id": "new:b",
            },
        },
    ]


def test_health_and_capabilities(client, owner_headers, reader_headers):
    assert client.get("/api/v1/health").status_code == 200

    owner = client.get("/api/v1/capabilities", headers=owner_headers)
    assert owner.status_code == 200
    assert "prepare_change_set" in owner.json()["operations"]

    reader = client.get("/api/v1/capabilities", headers=reader_headers)
    assert reader.status_code == 200
    assert reader.json()["read_only"] is True
    assert "prepare_change_set" not in reader.json()["operations"]


def test_one_batch_create_commit_and_read(client, owner_headers, reader_headers, project_id):
    response = prepare(client, project_id, owner_headers, base_model_operations())
    assert response.status_code == 201, response.text
    change_set = response.json()
    assert change_set["status"] == "prepared", change_set
    assert change_set["errors"] == []

    committed = commit(
        client, project_id, owner_headers, change_set["id"], 0, "batch-one"
    )
    assert committed.status_code == 200, committed.text
    result = committed.json()
    assert result["changed"] is True
    assert result["revision"] == 1

    state = client.get(
        f"/api/v1/projects/{project_id}/state?revision=1", headers=owner_headers
    )
    assert state.status_code == 200
    objects = state.json()["objects"]
    assert len(objects) == 5
    assert {item["kind"] for item in objects} == {
        "class",
        "relation_type",
        "instance",
        "relation",
    }

    instances = client.get(
        f"/api/v1/projects/{project_id}/objects?kind=instance&revision=1",
        headers=reader_headers,
    )
    assert instances.status_code == 200
    assert instances.json()["returned_count"] == 2
    assert instances.json()["has_more"] is False

    schema = client.get(
        f"/api/v1/projects/{project_id}/schema?revision=1", headers=reader_headers
    )
    assert schema.status_code == 200
    assert len(schema.json()["classes"]) == 1
    assert len(schema.json()["relation_types"]) == 1
    assert schema.json()["warnings"] == []

    reader_write = prepare(
        client, project_id, reader_headers, base_model_operations(), base_revision=1
    )
    assert reader_write.status_code == 403


def test_state_survives_restart(settings, owner_headers, project_id, client):
    response = prepare(client, project_id, owner_headers, base_model_operations())
    change_set = response.json()
    assert commit(client, project_id, owner_headers, change_set["id"], 0, "restart").status_code == 200

    from app.main import create_app

    second_app = create_app(settings)
    with TestClient(second_app) as second:
        state = second.get(
            f"/api/v1/projects/{project_id}/state?revision=1", headers=owner_headers
        )
        assert state.status_code == 200
        assert len(state.json()["objects"]) == 5


def test_failed_batch_leaves_no_state(client, owner_headers, project_id):
    operations = [
        {
            "op": "create",
            "ref": "new:bad",
            "kind": "instance",
            "data": {
                "label": "Missing class reference",
                "class_ids": ["00000000-0000-0000-0000-000000000000"],
            },
        }
    ]
    response = prepare(client, project_id, owner_headers, operations)
    assert response.status_code == 201
    change_set = response.json()
    assert change_set["status"] == "invalid"
    assert change_set["errors"]

    rejected = commit(
        client, project_id, owner_headers, change_set["id"], 0, "invalid-batch"
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "invalid_change_set"

    project = client.get(f"/api/v1/projects/{project_id}", headers=owner_headers).json()
    assert project["current_revision"] == 0
    state = client.get(
        f"/api/v1/projects/{project_id}/state", headers=owner_headers
    ).json()
    assert state["objects"] == []


def test_idempotent_replay_and_conflict(client, owner_headers, project_id):
    response = prepare(client, project_id, owner_headers, base_model_operations())
    change_set = response.json()
    first = commit(client, project_id, owner_headers, change_set["id"], 0, "same-key")
    assert first.status_code == 200

    replay = commit(client, project_id, owner_headers, change_set["id"], 0, "same-key")
    assert replay.status_code == 200
    assert replay.json()["revision"] == first.json()["revision"]
    assert replay.json()["idempotent_replay"] is True

    second_prepare = prepare(client, project_id, owner_headers, base_model_operations(), base_revision=1)
    second = second_prepare.json()
    conflict = commit(client, project_id, owner_headers, second["id"], 1, "same-key")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"


def test_stale_commit_conflict(client, owner_headers, project_id):
    first_prepare = prepare(client, project_id, owner_headers, base_model_operations()).json()
    assert commit(client, project_id, owner_headers, first_prepare["id"], 0, "stale-a").status_code == 200

    second_operations = [
        {
            "op": "create",
            "ref": "new:late",
            "kind": "class",
            "data": {"label": "Late class", "definition": "Synthetic."},
        }
    ]
    stale = prepare(client, project_id, owner_headers, second_operations, base_revision=0).json()
    response = commit(client, project_id, owner_headers, stale["id"], 0, "stale-b")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "revision_conflict"
    assert response.json()["error"]["details"]["expected_revision"] == 0
    assert response.json()["error"]["details"]["current_revision"] == 1


def test_multi_object_batch_is_atomic(client, owner_headers, project_id):
    operations = [
        {
            "op": "create",
            "ref": "new:good",
            "kind": "class",
            "data": {"label": "Would-be class", "definition": "Synthetic."},
        },
        {
            "op": "create",
            "ref": "new:bad",
            "kind": "instance",
            "data": {
                "label": "Broken instance",
                "class_ids": ["00000000-0000-0000-0000-000000000000"],
            },
        },
    ]
    change_set = prepare(client, project_id, owner_headers, operations).json()
    assert change_set["status"] == "invalid"
    assert commit(
        client, project_id, owner_headers, change_set["id"], 0, "atomic-batch"
    ).status_code == 422
    assert client.get(
        f"/api/v1/projects/{project_id}/state", headers=owner_headers
    ).json()["objects"] == []


def test_reader_cannot_commit_an_owner_prepared_change_set(
    client, owner_headers, reader_headers, project_id
):
    change_set = prepare(client, project_id, owner_headers, base_model_operations()).json()
    response = commit(
        client,
        project_id,
        reader_headers,
        change_set["id"],
        0,
        "reader-commit",
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "owner_required"
