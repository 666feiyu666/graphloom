from __future__ import annotations

from tests.conftest import commit, prepare


def _create_and_commit(client, project_id, headers, operations, base_revision, key):
    change_set = prepare(client, project_id, headers, operations, base_revision=base_revision)
    assert change_set.status_code == 201, change_set.text
    payload = change_set.json()
    assert payload["status"] == "prepared", payload
    response = commit(client, project_id, headers, payload["id"], base_revision, key)
    assert response.status_code == 200, response.text
    return payload, response.json()


def _state(client, project_id, headers, revision=None):
    suffix = f"?revision={revision}" if revision is not None else ""
    response = client.get(
        f"/api/v1/projects/{project_id}/state{suffix}", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def _seed_rich_graph(client, project_id, headers):
    operations = [
        {
            "op": "create",
            "ref": "new:category",
            "kind": "class",
            "data": {"label": "Category", "definition": "Synthetic category."},
        },
        {
            "op": "create",
            "ref": "new:subcategory",
            "kind": "class",
            "data": {
                "label": "Subcategory",
                "definition": "Synthetic subcategory.",
                "parent_ids": ["new:category"],
            },
        },
        {
            "op": "create",
            "ref": "new:rel",
            "kind": "relation_type",
            "data": {
                "label": "Points to",
                "definition": "Synthetic relation.",
                "domain_ids": ["new:category"],
                "range_ids": ["new:category"],
            },
        },
        {
            "op": "create",
            "ref": "new:attr",
            "kind": "attribute_type",
            "data": {
                "label": "Caption",
                "definition": "Synthetic attribute.",
                "domain_ids": ["new:category"],
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
                "evidence_state": "unverified",
            },
        },
        {
            "op": "create",
            "ref": "new:a",
            "kind": "instance",
            "data": {
                "label": "Alpha",
                "definition": "Synthetic instance.",
                "class_ids": ["new:subcategory"],
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
                "class_ids": ["new:category"],
            },
        },
        {
            "op": "create",
            "ref": "new:assertion",
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
    change_set, result = _create_and_commit(
        client, project_id, headers, operations, 0, "rich-graph"
    )
    return change_set, result


def test_query_neighbors_instances_and_references(client, owner_headers, reader_headers, project_id):
    change_set, _ = _seed_rich_graph(client, project_id, owner_headers)
    state = _state(client, project_id, owner_headers, 1)
    by_label = {obj.get("label"): obj for obj in state["objects"]}

    response = client.post(
        f"/api/v1/projects/{project_id}/query",
        json={
            "revision": 1,
            "query": {
                "type": "neighbors",
                "object_id": by_label["Alpha"]["id"],
                "depth": 1,
                "direction": "outgoing",
            },
        },
        headers=owner_headers,
    )
    assert response.status_code == 200, response.text
    neighbors = response.json()
    assert neighbors["revision"] == 1
    assert neighbors["query_type"] == "neighbors"
    labels = {obj.get("label") for obj in neighbors["objects"]}
    assert "Alpha" in labels and "Beta" in labels
    assert any(obj["kind"] == "relation" for obj in neighbors["objects"])
    assert any(obj["kind"] == "attribute_value" for obj in neighbors["objects"])
    assert {item["kind"] for item in neighbors["definitions"]} >= {
        "class",
        "relation_type",
        "attribute_type",
    }

    instances = client.post(
        f"/api/v1/projects/{project_id}/query",
        json={
            "revision": 1,
            "query": {
                "type": "instances_of",
                "class_id": by_label["Category"]["id"],
                "include_descendants": True,
            },
        },
        headers=reader_headers,
    )
    assert instances.status_code == 200, instances.text
    assert instances.json()["returned_count"] == 2

    references = client.post(
        f"/api/v1/projects/{project_id}/query",
        json={
            "revision": 1,
            "query": {
                "type": "references_to",
                "object_id": by_label["Category"]["id"],
            },
        },
        headers=owner_headers,
    )
    assert references.status_code == 200, references.text
    assert references.json()["references"]


def test_hierarchy_cycle_and_literal_mismatch_are_atomic(client, owner_headers, project_id):
    cycle = [
        {
            "op": "create",
            "ref": "new:a-class",
            "kind": "class",
            "data": {
                "label": "Cycle A",
                "definition": "Synthetic.",
                "parent_ids": ["new:b-class"],
            },
        },
        {
            "op": "create",
            "ref": "new:b-class",
            "kind": "class",
            "data": {
                "label": "Cycle B",
                "definition": "Synthetic.",
                "parent_ids": ["new:a-class"],
            },
        },
    ]
    response = prepare(client, project_id, owner_headers, cycle)
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "invalid"
    assert any(error["code"] == "hierarchy_cycle" for error in payload["errors"])
    assert commit(client, project_id, owner_headers, payload["id"], 0, "cycle").status_code == 422
    assert _state(client, project_id, owner_headers)["objects"] == []

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
    response = prepare(client, project_id, owner_headers, literal)
    payload = response.json()
    assert payload["status"] == "invalid"
    assert any(error["code"] == "literal_type_mismatch" for error in payload["errors"])


def test_delete_dependency_is_explicit(client, owner_headers, project_id):
    _create_and_commit(
        client,
        project_id,
        owner_headers,
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
                "data": {
                    "label": "Instance",
                    "definition": "Synthetic.",
                    "class_ids": ["new:class"],
                },
            },
        ],
        0,
        "seed-delete-dependency",
    )
    state = _state(client, project_id, owner_headers, 1)
    class_id = next(obj["id"] for obj in state["objects"] if obj["kind"] == "class")
    deletion = prepare(
        client,
        project_id,
        owner_headers,
        [{"op": "delete", "id": class_id}],
        base_revision=1,
    ).json()
    assert deletion["status"] == "invalid"
    dependency_errors = [
        error for error in deletion["errors"] if error["code"] == "delete_dependency"
    ]
    assert dependency_errors
    assert dependency_errors[0]["details"]["deleted_id"] == class_id
    assert dependency_errors[0]["details"]["dependents"]
    assert commit(
        client, project_id, owner_headers, deletion["id"], 1, "delete-dependency"
    ).status_code == 422


def test_update_preserves_identity_and_reports_impact(client, owner_headers, project_id):
    _seed_rich_graph(client, project_id, owner_headers)
    state = _state(client, project_id, owner_headers, 1)
    class_obj = next(obj for obj in state["objects"] if obj["kind"] == "class" and obj["label"] == "Category")
    instance_ids = {
        obj["id"]
        for obj in state["objects"]
        if obj["kind"] == "instance"
    }

    change_set = prepare(
        client,
        project_id,
        owner_headers,
        [
            {
                "op": "update",
                "id": class_obj["id"],
                "fields": {"definition": "Updated synthetic definition."},
            }
        ],
        base_revision=1,
    ).json()
    assert change_set["status"] == "prepared", change_set
    result = commit(
        client, project_id, owner_headers, change_set["id"], 1, "update-class"
    ).json()
    assert result["revision"] == 2
    changed = result["diff"]["changed"]
    assert changed[0]["id"] == class_obj["id"]
    assert set(changed[0]["fields"]) == {"definition", "updated_at"}
    assert instance_ids <= set(change_set["impacted"]["object_ids"])

    after = _state(client, project_id, owner_headers, 2)
    updated = next(obj for obj in after["objects"] if obj["id"] == class_obj["id"])
    assert updated["id"] == class_obj["id"]
    assert updated["label"] == "Category"
    assert updated["definition"] == "Updated synthetic definition."


def test_parallel_assertions_keep_distinct_identity(client, owner_headers, project_id):
    operations = [
        {
            "op": "create",
            "ref": "new:class",
            "kind": "class",
            "data": {"label": "Class", "definition": "Synthetic."},
        },
        {
            "op": "create",
            "ref": "new:rel",
            "kind": "relation_type",
            "data": {"label": "Rel", "definition": "Synthetic."},
        },
        {
            "op": "create",
            "ref": "new:a",
            "kind": "instance",
            "data": {"label": "A", "definition": "Synthetic.", "class_ids": ["new:class"]},
        },
        {
            "op": "create",
            "ref": "new:b",
            "kind": "instance",
            "data": {"label": "B", "definition": "Synthetic.", "class_ids": ["new:class"]},
        },
        {
            "op": "create",
            "ref": "new:r1",
            "kind": "relation",
            "data": {
                "source_id": "new:a",
                "relation_type_id": "new:rel",
                "target_id": "new:b",
                "notes": "First parallel assertion.",
            },
        },
        {
            "op": "create",
            "ref": "new:r2",
            "kind": "relation",
            "data": {
                "source_id": "new:a",
                "relation_type_id": "new:rel",
                "target_id": "new:b",
                "notes": "Second parallel assertion.",
            },
        },
    ]
    _create_and_commit(client, project_id, owner_headers, operations, 0, "parallel")
    state = _state(client, project_id, owner_headers, 1)
    relations = [obj for obj in state["objects"] if obj["kind"] == "relation"]
    assert len(relations) == 2
    assert len({obj["id"] for obj in relations}) == 2
    assert {obj["notes"] for obj in relations} == {
        "First parallel assertion.",
        "Second parallel assertion.",
    }


def test_source_reference_metadata_is_preserved(client, owner_headers, project_id):
    _seed_rich_graph(client, project_id, owner_headers)
    state = _state(client, project_id, owner_headers, 1)
    source = next(obj for obj in state["objects"] if obj["kind"] == "source_ref")
    assert source["locator"] == {
        "kind": "url",
        "value": "https://example.invalid/source",
    }
    assert source["evidence_state"] == "unverified"
    instance = next(obj for obj in state["objects"] if obj.get("label") == "Alpha")
    assert source["id"] in instance["source_ref_ids"]


def test_revision_pinned_pagination(client, owner_headers, project_id):
    operations = [
        {
            "op": "create",
            "ref": f"new:c{index}",
            "kind": "class",
            "data": {"label": f"Class {index}", "definition": "Synthetic."},
        }
        for index in range(5)
    ]
    _create_and_commit(client, project_id, owner_headers, operations, 0, "pagination")

    pages = []
    cursor = None
    for _ in range(6):
        url = f"/api/v1/projects/{project_id}/objects?kind=class&limit=2"
        if cursor:
            url += f"&cursor={cursor}"
        page = client.get(url, headers=owner_headers).json()
        assert page["revision"] == 1
        pages.append(page)
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(pages) == 3
    combined = {obj["id"] for page in pages for obj in page["objects"]}
    assert len(combined) == 5
    page_one = pages[0]
    cursor = page_one["next_cursor"]

    extra = [
        {
            "op": "create",
            "ref": "new:extra",
            "kind": "class",
            "data": {"label": "Later class", "definition": "Synthetic."},
        }
    ]
    _create_and_commit(client, project_id, owner_headers, extra, 1, "pagination-later")

    pinned = client.get(
        f"/api/v1/projects/{project_id}/objects?cursor={cursor}",
        headers=owner_headers,
    ).json()
    assert pinned["revision"] == 1
    assert len(
        {obj["id"] for obj in page_one["objects"] + pinned["objects"]}
    ) == 5
    assert not any(obj.get("label") == "Later class" for obj in pinned["objects"])

    mismatch = client.get(
        f"/api/v1/projects/{project_id}/objects?cursor={cursor}&revision=2",
        headers=owner_headers,
    )
    assert mismatch.status_code == 422


def test_reader_scope_and_revocation(client, app, owner_headers, reader_headers, project_id):
    other = client.post(
        "/api/v1/projects",
        json={"name": "Other project"},
        headers=owner_headers,
    ).json()
    forbidden = client.get(
        f"/api/v1/projects/{other['id']}/state", headers=reader_headers
    )
    assert forbidden.status_code == 403

    credentials = client.get("/api/v1/credentials", headers=owner_headers).json()[
        "credentials"
    ]
    reader = next(item for item in credentials if item["role"] == "reader")
    assert client.delete(
        f"/api/v1/credentials/{reader['id']}", headers=reader_headers
    ).status_code == 403
    assert client.delete(
        f"/api/v1/credentials/{reader['id']}", headers=owner_headers
    ).status_code == 200
    revoked = client.get(
        f"/api/v1/projects/{project_id}/state", headers=reader_headers
    )
    assert revoked.status_code == 401


def test_reader_cannot_write_or_manage(client, owner_headers, reader_headers, project_id):
    assert client.post(
        "/api/v1/projects", json={"name": "Forbidden"}, headers=reader_headers
    ).status_code == 403
    assert client.post(
        f"/api/v1/projects/{project_id}/change-sets",
        json={"base_revision": 0, "reason": "", "operations": []},
        headers=reader_headers,
    ).status_code == 403
    assert client.post(
        f"/api/v1/projects/{project_id}/import-preview",
        json={},
        headers=reader_headers,
    ).status_code == 403
    assert client.post(
        f"/api/v1/projects/{project_id}/snapshots",
        json={"name": "Forbidden"},
        headers=reader_headers,
    ).status_code == 403
    assert client.put(
        f"/api/v1/projects/{project_id}/layout",
        json={"expected_version": 0, "data": {}},
        headers=reader_headers,
    ).status_code == 403
    assert client.get("/api/v1/credentials", headers=reader_headers).status_code == 403


def test_reader_openapi_excludes_owner_operations(client):
    response = client.get("/api/v1/openapi.reader.json")
    assert response.status_code == 200
    spec = response.json()
    assert spec["x-graphloom-read-only"] is True
    paths = spec["paths"]
    for forbidden in (
        "/api/v1/projects/{project_id}/change-sets",
        "/api/v1/projects/{project_id}/import-preview",
        "/api/v1/projects/{project_id}/layout",
        "/api/v1/credentials",
    ):
        assert forbidden not in paths
    project_methods = set(paths["/api/v1/projects"])
    assert project_methods == {"get"}
    assert set(paths["/api/v1/projects/{project_id}/query"]) == {"post"}
