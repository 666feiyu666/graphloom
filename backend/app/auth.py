from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import Credential


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_token(role: str) -> str:
    return f"gl_{role}_{secrets.token_urlsafe(32)}"


def create_credential(
    session: Session,
    *,
    role: str,
    label: str,
    project_ids: list[str] | None = None,
) -> tuple[Credential, str]:
    if role not in {"owner", "reader"}:
        raise ValueError("role must be owner or reader")
    if role == "owner" and project_ids:
        raise ValueError("owner credentials are not project-scoped")
    token = generate_token(role)
    credential = Credential(
        id=str(uuid4()),
        role=role,
        label=label,
        token_hash=hash_token(token),
        project_ids_json=json.dumps(sorted(set(project_ids or [])), ensure_ascii=False),
        created_at=datetime.now(timezone.utc),
    )
    session.add(credential)
    session.flush()
    return credential, token


def resolve_token(session: Session, token: str) -> Credential | None:
    token_hash = hash_token(token)
    credential = session.scalar(select(Credential).where(Credential.token_hash == token_hash))
    if credential is None or credential.revoked_at is not None:
        return None
    return credential


def credential_project_ids(credential: Credential) -> set[str]:
    return set(json.loads(credential.project_ids_json or "[]"))


def revoke_credential(session: Session, credential: Credential) -> None:
    credential.revoked_at = datetime.now(timezone.utc)
    session.flush()
