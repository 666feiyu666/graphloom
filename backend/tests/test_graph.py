from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import apply


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


def rich_operations():
    return [
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


def test_health_and_capabilities(client):
    assert client.get("/api/v1/health").status_code == 200
    capabilities = client.get("/api/v1/capabilities")
    assert capabilities.status_code == 200
    assert "class" in capabilities.json()["kinds"]


def test_one_batch_create_and_read(client, project_id):
    response = apply(client, project_id, base_model_operations())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["changed"] is True
    assert result["version"] == 1
    assert len(result["added_ids"]) == 5

    state = client.get(f"/api/v1/projects/{project_id}/state")
    assert state.status_code == 200
    assert state.json()["version"] == 1
    objects = state.json()["objects"]
    assert len(objects) == 5
    assert {item["kind"] for item in objects} == {
        "class",
        "relation_type",
        "instance",
        "relation",
    }

    instances = client.get(f"/api/v1/projects/{project_id}/objects?kind=instance")
    assert instances.status_code == 200
    assert instances.json()["returned_count"] == 2
    assert instances.json()["has_more"] is False

    schema = client.get(f"/api/v1/projects/{project_id}/schema")
    assert schema.status_code == 200
    assert len(schema.json()["classes"]) == 1
    assert schema.json()["warnings"] == []


def test_state_survives_restart(settings, client, project_id):
    assert apply(client, project_id, base_model_operations()).status_code == 200

    from app.main import create_app

    with TestClient(create_app(settings)) as second:
        state = second.get(f"/api/v1/projects/{project_id}/state")
        assert state.status_code == 200
        assert len(state.json()["objects"]) == 5


def test_failed_batch_leaves_no_state(client, project_id):
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
    response = apply(client, project_id, operations)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_batch"

    project = client.get(f"/api/v1/projects/{project_id}").json()
    assert project["version"] == 0
    state = client.get(f"/api/v1/projects/{project_id}/state").json()
    assert state["objects"] == []


def test_multi_object_batch_is_atomic(client, project_id):
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
    assert apply(client, project_id, operations).status_code == 422
    assert client.get(f"/api/v1/projects/{project_id}/state").json()["objects"] == []


def test_hierarchy_cycle_and_literal_mismatch_are_rejected(client, project_id):
    cycle = [
        {
            "op": "create",
            "ref": "new:a-class",
            "kind": "class",
            "data": {"label": "Cycle A", "definition": "Synthetic.", "parent_ids": ["new:b-class"]},
        },
        {
            "op": "create",
            "ref": "new:b-class",
            "kind": "class",
            "data": {"label": "Cycle B", "definition": "Synthetic.", "parent_ids": ["new:a-class"]},
        },
    ]
    response = apply(client, project_id, cycle)
    assert response.status_code == 422
    assert any(error["code"] == "hierarchy_cycle" for error in response.json()["error"]["details"]["errors"])

    literal = [
        {
            "op": "create",
            "ref": "new:attr",
            "kind": "attribute_type",
            "data": {"label": "Count", "definition": "Synthetic.", "value_type": "number"},
        },
        {
            "op": "create",
            "ref": "new:instance",
            "kind": "instance",
            "data": {"label": "Subject", "definition": "Synthetic."},
        },
        {
            "op": "create",
            "ref": "new:value",
            "kind": "attribute_value",
            "data": {
                "subject_id": "new:instance",
                "attribute_type_id": "new:attr",
                "value": "not a number",
            },
        },
    ]
    response = apply(client, project_id, literal)
    assert response.status_code == 422
    assert any(
        error["code"] == "literal_type_mismatch"
        for error in response.json()["error"]["details"]["errors"]
    )


def test_delete_dependency_is_explicit(client, project_id):
    assert apply(
        client,
        project_id,
        [
            {
                "op": "create",
                "ref": "new:class",
                "kind": "class",
                "data": {"label": "Class", "definition": "Synthetic."},
            },
            {
                "op": "create",
                "ref": "new:instance",
                "kind": "instance",
                "data": {"label": "Instance", "definition": "Synthetic.", "class_ids": ["new:class"]},
            },
        ],
    ).status_code == 200

    state = client.get(f"/api/v1/projects/{project_id}/state").json()
    class_id = next(obj["id"] for obj in state["objects"] if obj["kind"] == "class")
    response = apply(client, project_id, [{"op": "delete", "id": class_id}])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "dependency_conflict"
    errors = response.json()["error"]["details"]["errors"]
    dependency_errors = [error for error in errors if error["code"] == "delete_dependency"]
    assert dependency_errors
    assert dependency_errors[0]["details"]["deleted_id"] == class_id
    assert dependency_errors[0]["details"]["dependents"]


def test_update_preserves_identity(client, project_id):
    assert apply(client, project_id, rich_operations()).status_code == 200
    state = client.get(f"/api/v1/projects/{project_id}/state").json()
    class_obj = next(obj for obj in state["objects"] if obj["kind"] == "class" and obj["label"] == "Category")

    response = apply(
        client,
        project_id,
        [{"op": "update", "id": class_obj["id"], "fields": {"definition": "Updated synthetic definition."}}],
    )
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 2
    assert response.json()["updated_ids"] == [class_obj["id"]]

    after = client.get(f"/api/v1/projects/{project_id}/state").json()
    updated = next(obj for obj in after["objects"] if obj["id"] == class_obj["id"])
    assert updated["label"] == "Category"
    assert updated["definition"] == "Updated synthetic definition."


def test_parallel_assertions_keep_distinct_identity(client, project_id):
    operations = [
        {"op": "create", "ref": "new:class", "kind": "class", "data": {"label": "Class", "definition": "Synthetic."}},
        {"op": "create", "ref": "new:rel", "kind": "relation_type", "data": {"label": "Rel", "definition": "Synthetic."}},
        {"op": "create", "ref": "new:a", "kind": "instance", "data": {"label": "A", "definition": "Synthetic.", "class_ids": ["new:class"]}},
        {"op": "create", "ref": "new:b", "kind": "instance", "data": {"label": "B", "definition": "Synthetic.", "class_ids": ["new:class"]}},
        {
            "op": "create",
            "ref": "new:r1",
            "kind": "relation",
            "data": {"source_id": "new:a", "relation_type_id": "new:rel", "target_id": "new:b", "notes": "First."},
        },
        {
            "op": "create",
            "ref": "new:r2",
            "kind": "relation",
            "data": {"source_id": "new:a", "relation_type_id": "new:rel", "target_id": "new:b", "notes": "Second."},
        },
    ]
    assert apply(client, project_id, operations).status_code == 200
    state = client.get(f"/api/v1/projects/{project_id}/state").json()
    relations = [obj for obj in state["objects"] if obj["kind"] == "relation"]
    assert len(relations) == 2
    assert len({obj["id"] for obj in relations}) == 2
    assert {obj["notes"] for obj in relations} == {"First.", "Second."}


def test_source_reference_metadata_is_preserved(client, project_id):
    assert apply(client, project_id, rich_operations()).status_code == 200
    state = client.get(f"/api/v1/projects/{project_id}/state").json()
    source = next(obj for obj in state["objects"] if obj["kind"] == "source_ref")
    assert source["locator"] == {"kind": "url", "value": "https://example.invalid/source"}
    assert source["evidence_state"] == "abstract_preview_verified"
    instance = next(obj for obj in state["objects"] if obj.get("label") == "Alpha")
    assert source["id"] in instance["source_ref_ids"]


def test_pagination_walks_current_state(client, project_id):
    operations = [
        {
            "op": "create",
            "ref": f"new:c{index}",
            "kind": "class",
            "data": {"label": f"Class {index}", "definition": "Synthetic."},
        }
        for index in range(5)
    ]
    assert apply(client, project_id, operations).status_code == 200

    pages = []
    cursor = None
    for _ in range(6):
        url = f"/api/v1/projects/{project_id}/objects?kind=class&limit=2"
        if cursor:
            url += f"&cursor={cursor}"
        page = client.get(url).json()
        assert page["version"] == 1
        pages.append(page)
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(pages) == 3
    combined = {obj["id"] for page in pages for obj in page["objects"]}
    assert len(combined) == 5


def test_neighborhood_instances_and_references(client, project_id):
    assert apply(client, project_id, rich_operations()).status_code == 200
    state = client.get(f"/api/v1/projects/{project_id}/state").json()
    by_label = {obj.get("label"): obj for obj in state["objects"]}

    neighbors = client.get(
        f"/api/v1/projects/{project_id}/neighborhood",
        params={"id": by_label["Alpha"]["id"], "depth": 1, "direction": "outgoing"},
    )
    assert neighbors.status_code == 200, neighbors.text
    payload = neighbors.json()
    assert payload["query_type"] == "neighbors"
    labels = {obj.get("label") for obj in payload["objects"]}
    assert "Alpha" in labels and "Beta" in labels
    assert any(obj["kind"] == "relation" for obj in payload["objects"])
    assert any(obj["kind"] == "attribute_value" for obj in payload["objects"])

    instances = client.get(
        f"/api/v1/projects/{project_id}/instances",
        params={"class_id": by_label["Category"]["id"], "include_descendants": True},
    )
    assert instances.status_code == 200
    assert instances.json()["returned_count"] == 2

    references = client.get(
        f"/api/v1/projects/{project_id}/references",
        params={"id": by_label["Category"]["id"]},
    )
    assert references.status_code == 200
    assert references.json()["references"]


def test_layout_does_not_change_version(client, project_id):
    assert apply(client, project_id, base_model_operations()).status_code == 200
    response = client.put(
        f"/api/v1/projects/{project_id}/layout",
        json={"data": {"positions": {"node": {"x": 10, "y": 20}}}},
    )
    assert response.status_code == 200
    assert response.json()["data"]["positions"]["node"]["x"] == 10
    layout = client.get(f"/api/v1/projects/{project_id}/layout").json()
    assert layout["data"]["positions"]["node"]["y"] == 20
    project = client.get(f"/api/v1/projects/{project_id}").json()
    assert project["version"] == 1


def test_reader_openapi_excludes_write_routes(client):
    response = client.get("/api/v1/openapi.reader.json")
    assert response.status_code == 200
    spec = response.json()
    assert spec["x-graphloom-read-only"] is True
    paths = spec["paths"]
    assert set(paths["/api/v1/projects"]) == {"get"}
    assert "/api/v1/projects/{project_id}/batch" not in paths
    assert "/api/v1/projects/{project_id}/layout" not in paths
