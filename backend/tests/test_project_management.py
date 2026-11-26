from __future__ import annotations

from tests.conftest import apply


def test_rename_project(client, project_id):
    response = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "Renamed project", "description": "New description"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Renamed project"
    assert response.json()["description"] == "New description"
    assert response.json()["version"] == 0  # renaming does not advance the version

    got = client.get(f"/api/v1/projects/{project_id}").json()
    assert got["name"] == "Renamed project"


def test_rename_requires_a_field(client, project_id):
    response = client.patch(f"/api/v1/projects/{project_id}", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_updates"


def test_delete_project_removes_data_and_listing(client, project_id):
    assert apply(
        client,
        project_id,
        [{"op": "create", "ref": "new:c", "kind": "class", "data": {"label": "C", "definition": "Synthetic."}}],
    ).status_code == 200

    response = client.delete(f"/api/v1/projects/{project_id}")
    assert response.status_code == 200
    assert response.json()["deleted"] is True

    assert client.get(f"/api/v1/projects/{project_id}").status_code == 404
    projects = client.get("/api/v1/projects").json()["projects"]
    assert all(item["id"] != project_id for item in projects)


def test_delete_missing_project_is_404(client):
    response = client.delete("/api/v1/projects/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
