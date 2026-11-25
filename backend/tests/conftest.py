from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth import create_credential
from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(
        db_path=tmp_path / "graphloom.db",
        frontend_dist=tmp_path / "dist",
        rate_limit_per_minute=100000,
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def owner_headers(app, client):
    with app.state.session_factory() as session:
        _, token = create_credential(session, role="owner", label="owner")
        session.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def project_id(client, owner_headers):
    response = client.post(
        "/api/v1/projects",
        json={"name": "Synthetic test project", "description": "Technical fixture"},
        headers=owner_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def reader_headers(app, client, project_id):
    with app.state.session_factory() as session:
        _, token = create_credential(
            session, role="reader", label="reader", project_ids=[project_id]
        )
        session.commit()
    return {"Authorization": f"Bearer {token}"}


def prepare(client, project_id, headers, operations, base_revision=0, reason="test batch"):
    return client.post(
        f"/api/v1/projects/{project_id}/change-sets",
        json={
            "base_revision": base_revision,
            "reason": reason,
            "operations": operations,
        },
        headers=headers,
    )


def commit(client, project_id, headers, change_set_id, expected_revision, key):
    return client.post(
        f"/api/v1/projects/{project_id}/change-sets/{change_set_id}/commit",
        json={"expected_revision": expected_revision},
        headers={**headers, "Idempotency-Key": key},
    )
