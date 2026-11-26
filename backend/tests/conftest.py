from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(
        data_dir=tmp_path / "projects",
        frontend_dist=tmp_path / "dist",
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def project_id(client):
    response = client.post(
        "/api/v1/projects",
        json={"name": "Synthetic test project", "description": "Technical fixture"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def apply(client, project_id, operations):
    return client.post(
        f"/api/v1/projects/{project_id}/batch",
        json={"operations": operations},
    )
