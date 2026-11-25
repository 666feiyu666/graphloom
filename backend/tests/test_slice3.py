from __future__ import annotations

import copy
import json

from tests.conftest import commit, prepare


def seed_rich_graph(client, project_id, headers, key="rich-seed"):
    operations = [
        {
            "op": "create",
            "ref": "new:parent",
            "kind": "class",
            "data": {"label": "Category", "definition": "Synthetic parent class."},
        },
        {
            "op": "create",
            "ref": "new:child",
            "kind": "class",
            "data": {
                "label": "Subcategory",
                "definition": "Synthetic child class.",
                "parent_ids": ["new:parent"],
            },
        },
        {
            "op": "create",
            "ref": "new:rel",
            "kind": "relation_type",
            "data": {
                "label": "Points to",
                "definition": "Synthetic relation type.",
                "domain_ids": ["new:parent"],
                "range_ids": ["new:parent"],
            },
        },
        {
            "op": "create",
            "ref": "new:attr",
            "kind": "attribute_type",
            "data": {
                "label": "Caption",
                "definition": "Synthetic attribute type.",
                "domain_ids": ["new:parent"],
                "value_type": "string",
            },
        },
        {
            "op": "create",
            "ref": "new:source",
            "kind": "source_ref",
            "data": {
                "label": "Synthetic source",
                "locator": {"kind": "url", "value": "https://example.invalid/source"},
                "citation_text": "Synthetic citation only.",
                "evidence_state": "abstract_preview_verified",
            },
        },
        {
            "op": "create",
            "ref": "new:a",
            "kind": "instance",
            "data": {
                "label": "Alpha",
                "definition": "Synthetic instance.",
                "class_ids": ["new:child"],
                "source_ref_ids": ["new:source"],
                "review_status": "accepted",
            },
        },
        {
            "op": "create",
            "ref": "new:b",
            "kind": "instance",
            "data": {
                "label": "Beta",
                "definition": "Synthetic instance.",
                "class_ids": ["new:parent"],
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
                "notes": "Synthetic assertion note.",
            },
        },
        {
            "op": "create",
            "ref": "new:value",
            "kind": "attribute_value",
            "data": {
                "subject_id": "new:a",
                "attribute_type_id": "new:attr",
                "value": "Synthetic caption",
            },
        },
    ]
    prepared = prepare(client, project_id, headers, operations)
    assert prepared.status_code == 201, prepared.text
    change_set = prepared.json()
    assert change_set["status"] == "prepared", change_set
    result = commit(client, project_id, headers, change_set["id"], 0, key)
    assert result.status_code == 200, result.text
    return change_set, result.json()


def state_of(client, project_id, headers, revision=None):
    suffix = f"?revision={revision}" if revision is not None else ""
    response = client.get(f"/api/v1/projects/{project_id}/state{suffix}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_diff_snapshot_restore_and_history(client, owner_headers, project_id):
    seed_rich_graph(client, project_id, owner_headers)
    state = state_of(client, project_id, owner_headers, 1)
    class_object = next(
        item for item in state["objects"] if item["kind"] == "class" and item["label"] == "Category"
    )
    snapshot = client.post(
        f"/api/v1/projects/{project_id}/snapshots",
        json={"name": "baseline", "revision": 1},
        headers=owner_headers,
    )
    assert snapshot.status_code == 201, snapshot.text
    snapshot_id = snapshot.json()["id"]

    update = prepare(
        client,
        project_id,
        owner_headers,
        [
            {
                "op": "update",
                "id": class_object["id"],
                "fields": {"definition": "Changed synthetic definition."},
            }
        ],
        base_revision=1,
    ).json()
    assert update["status"] == "prepared", update
    assert commit(client, project_id, owner_headers, update["id"], 1, "def-change").status_code == 200

    diff_response = client.get(
        f"/api/v1/projects/{project_id}/diff?from=1&to=2", headers=owner_headers
    )
    assert diff_response.status_code == 200
    diff = diff_response.json()["diff"]
    assert diff["counts"]["changed"] == 1
    assert diff["changed"][0]["fields"]["definition"]["after"] == "Changed synthetic definition."

    restore = client.post(
        f"/api/v1/projects/{project_id}/snapshots/{snapshot_id}/restore-preview",
        json={"reason": "Restore the baseline snapshot"},
        headers=owner_headers,
    )
    assert restore.status_code == 201, restore.text
    restore_payload = restore.json()
    assert restore_payload["status"] == "prepared", restore_payload
    assert restore_payload["diff"]["counts"]["changed"] == 1
    restored = commit(
        client,
        project_id,
        owner_headers,
        restore_payload["id"],
        restore_payload["base_revision"],
        "restore-baseline",
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["revision"] == 3

    restored_state = state_of(client, project_id, owner_headers, 3)
    restored_class = next(item for item in restored_state["objects"] if item["id"] == class_object["id"])
    assert restored_class["definition"] == "Synthetic parent class."
    revision_two_state = state_of(client, project_id, owner_headers, 2)
    revision_two_class = next(
        item for item in revision_two_state["objects"] if item["id"] == class_object["id"]
    )
    assert revision_two_class["definition"] == "Changed synthetic definition."

    revisions = client.get(
        f"/api/v1/projects/{project_id}/revisions", headers=owner_headers
    ).json()
    assert [item["revision"] for item in revisions["revisions"]] == [1, 2, 3]
    snapshots = client.get(
        f"/api/v1/projects/{project_id}/snapshots", headers=owner_headers
    ).json()["snapshots"]
    assert snapshots[0]["revision"] == 1


def test_revision_restore_preview_creates_new_revision(client, owner_headers, project_id):
    seed_rich_graph(client, project_id, owner_headers, "revision-restore-seed")
    state = state_of(client, project_id, owner_headers, 1)
    class_object = next(
        item
        for item in state["objects"]
        if item["kind"] == "class" and item["label"] == "Category"
    )
    update = prepare(
        client,
        project_id,
        owner_headers,
        [{"op": "update", "id": class_object["id"], "fields": {"label": "Category v2"}}],
        base_revision=1,
    ).json()
    assert commit(client, project_id, owner_headers, update["id"], 1, "label-change").status_code == 200

    preview = client.post(
        f"/api/v1/projects/{project_id}/revisions/1/restore-preview",
        json={"reason": "Undo the label change"},
        headers=owner_headers,
    )
    assert preview.status_code == 201, preview.text
    payload = preview.json()
    assert payload["status"] == "prepared", payload
    result = commit(
        client, project_id, owner_headers, payload["id"], payload["base_revision"], "undo-label"
    )
    assert result.status_code == 200
    final_state = state_of(client, project_id, owner_headers, result.json()["revision"])
    final_class = next(item for item in final_state["objects"] if item["id"] == class_object["id"])
    assert final_class["label"] == "Category"
    revisions = client.get(
        f"/api/v1/projects/{project_id}/revisions", headers=owner_headers
    ).json()["revisions"]
    assert any(item["reason"] == "Undo the label change" for item in revisions)


def test_native_export_import_round_trip(
    client, app, owner_headers, reader_headers, project_id
):
    seed_rich_graph(client, project_id, owner_headers, "round-trip-seed")
    layout_response = client.put(
        f"/api/v1/projects/{project_id}/layout",
        json={"expected_version": 0, "data": {"positions": {"node": {"x": 10, "y": 20}}}},
        headers=owner_headers,
    )
    assert layout_response.status_code == 200

    exported = client.get(
        f"/api/v1/projects/{project_id}/export?format=native-json&revision=1&include_layout=true",
        headers=owner_headers,
    )
    assert exported.status_code == 200, exported.text
    native = exported.json()
    assert native["format"] == "graphloom-native"
    assert native["format_version"] == 1
    assert native["project"]["revision"] == 1
    assert native["layout"]["positions"]["node"]["x"] == 10

    reader_export = client.get(
        f"/api/v1/projects/{project_id}/export?format=native-json&revision=1&include_layout=true",
        headers=reader_headers,
    )
    assert reader_export.status_code == 200
    assert "layout" not in reader_export.json()

    target = client.post(
        "/api/v1/projects",
        json={"name": "Imported copy", "description": "Technical fixture"},
        headers=owner_headers,
    ).json()
    preview = client.post(
        f"/api/v1/projects/{target['id']}/import-preview",
        json=native,
        headers=owner_headers,
    )
    assert preview.status_code == 201, preview.text
    change_set = preview.json()
    assert change_set["status"] == "prepared", change_set
    result = commit(
        client, target["id"], owner_headers, change_set["id"], 0, "round-trip-import"
    )
    assert result.status_code == 200, result.text
    assert result.json()["revision"] == 1

    source_state = state_of(client, project_id, owner_headers, 1)
    target_state = state_of(client, target["id"], owner_headers, 1)
    source_by_id = {item["id"]: item for item in source_state["objects"]}
    target_by_id = {item["id"]: item for item in target_state["objects"]}
    assert set(source_by_id) == set(target_by_id)

    for object_id, source_object in source_by_id.items():
        target_object = target_by_id[object_id]
        assert target_object["kind"] == source_object["kind"]
        assert target_object["project_id"] == target["id"]
        for field in (
            "label",
            "definition",
            "aliases",
            "notes",
            "review_status",
            "lifecycle",
            "origin",
            "created_by",
            "updated_by",
            "parent_ids",
            "domain_ids",
            "range_ids",
            "class_ids",
            "source_ref_ids",
            "source_id",
            "target_id",
            "relation_type_id",
            "attribute_type_id",
            "subject_id",
            "value",
            "locator",
            "citation_text",
            "evidence_state",
        ):
            if field in source_object:
                assert target_object.get(field) == source_object[field], (object_id, field)

    source_relation = next(item for item in source_state["objects"] if item["kind"] == "relation")
    target_relation = next(item for item in target_state["objects"] if item["kind"] == "relation")
    assert target_relation["source_id"] == source_relation["source_id"]
    assert target_relation["target_id"] == source_relation["target_id"]

    reader_target = client.get(
        f"/api/v1/projects/{target['id']}/state", headers=reader_headers
    )
    assert reader_target.status_code == 403


def test_import_failure_does_not_mutate(client, owner_headers, reader_headers, project_id):
    bad_format = client.post(
        f"/api/v1/projects/{project_id}/import-preview",
        json={"format": "not-native", "format_version": 1},
        headers=owner_headers,
    )
    assert bad_format.status_code == 422
    assert state_of(client, project_id, owner_headers)["objects"] == []

    seed_rich_graph(client, project_id, owner_headers, "import-failure-seed")
    exported = client.get(
        f"/api/v1/projects/{project_id}/export?format=native-json&revision=1",
        headers=owner_headers,
    ).json()
    broken = copy.deepcopy(exported)
    relation = next(
        item for item in broken["graph"]["objects"] if item["kind"] == "relation"
    )
    relation["target_id"] = "00000000-0000-0000-0000-000000000000"
    preview = client.post(
        f"/api/v1/projects/{project_id}/import-preview",
        json=broken,
        headers=owner_headers,
    )
    assert preview.status_code == 201
    change_set = preview.json()
    assert change_set["status"] == "invalid"
    assert change_set["errors"]
    rejected = commit(
        client, project_id, owner_headers, change_set["id"], 1, "bad-import"
    )
    assert rejected.status_code == 422
    assert state_of(client, project_id, owner_headers, 1)["objects"]
    project = client.get(f"/api/v1/projects/{project_id}", headers=owner_headers).json()
    assert project["current_revision"] == 1


def test_turtle_export(client, owner_headers, project_id):
    seed_rich_graph(client, project_id, owner_headers, "turtle-seed")
    response = client.get(
        f"/api/v1/projects/{project_id}/export?format=turtle&revision=1",
        headers=owner_headers,
    )
    assert response.status_code == 200
    assert "text/turtle" in response.headers["content-type"]
    turtle = response.text
    assert "owl:Class" in turtle
    assert "rdfs:subClassOf" in turtle
    assert "owl:ObjectProperty" in turtle
    assert "owl:DatatypeProperty" in turtle
    assert "gl:RelationAssertion" in turtle
    assert "gl:AttributeAssertion" in turtle
    assert "gl:domain" in turtle
    assert "gl:exportWarning" in turtle
    assert "gl:evidenceState" in turtle
    assert "owl:Restriction" not in turtle
    assert "Synthetic assertion note." in turtle
