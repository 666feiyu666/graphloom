from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from app.auth import create_credential, revoke_credential
from app.config import Settings
from app.storage.db import make_engine, make_session_factory, run_migrations
from app.storage.models import Credential, Project


def _prepare(settings: Settings):
    run_migrations(settings.db_path)
    engine = make_engine(settings.db_path)
    return engine, make_session_factory(engine)


def _print_credential(credential: Credential, token: str | None = None) -> None:
    payload = {
        "id": credential.id,
        "role": credential.role,
        "label": credential.label,
        "project_ids": json.loads(credential.project_ids_json or "[]"),
        "created_at": credential.created_at.isoformat() if credential.created_at else None,
    }
    if token is not None:
        payload["token"] = token
        payload["notice"] = "Store this token now; it is not shown again."
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def init_owner(args: argparse.Namespace, settings: Settings) -> int:
    engine, factory = _prepare(settings)
    try:
        with factory() as session:
            existing = session.scalars(
                select(Credential).where(
                    Credential.role == "owner", Credential.revoked_at.is_(None)
                )
            ).all()
            if existing and not args.rotate:
                print(
                    "An owner credential already exists. Use --rotate to revoke it and issue a new token.",
                    file=sys.stderr,
                )
                return 2
            if args.rotate:
                for row in existing:
                    revoke_credential(session, row)
            credential, token = create_credential(
                session, role="owner", label=args.label
            )
            session.commit()
            _print_credential(credential, token)
        return 0
    finally:
        engine.dispose()


def create_reader(args: argparse.Namespace, settings: Settings) -> int:
    engine, factory = _prepare(settings)
    try:
        with factory() as session:
            project_ids = args.project_id or []
            known = set(
                session.scalars(select(Project.id).where(Project.id.in_(project_ids))).all()
            )
            missing = sorted(set(project_ids) - known)
            if missing:
                print(f"Unknown project ids: {', '.join(missing)}", file=sys.stderr)
                return 2
            credential, token = create_credential(
                session,
                role="reader",
                label=args.label,
                project_ids=project_ids,
            )
            session.commit()
            _print_credential(credential, token)
        return 0
    finally:
        engine.dispose()


def list_credentials(args: argparse.Namespace, settings: Settings) -> int:
    engine, factory = _prepare(settings)
    try:
        with factory() as session:
            rows = session.scalars(select(Credential).order_by(Credential.created_at)).all()
            print(
                json.dumps(
                    [
                        {
                            "id": row.id,
                            "role": row.role,
                            "label": row.label,
                            "project_ids": json.loads(row.project_ids_json or "[]"),
                            "created_at": row.created_at.isoformat()
                            if row.created_at
                            else None,
                            "revoked_at": row.revoked_at.isoformat()
                            if row.revoked_at
                            else None,
                        }
                        for row in rows
                    ],
                    indent=2,
                    ensure_ascii=False,
                )
            )
        return 0
    finally:
        engine.dispose()


def revoke(args: argparse.Namespace, settings: Settings) -> int:
    engine, factory = _prepare(settings)
    try:
        with factory() as session:
            credential = session.get(Credential, args.credential_id)
            if credential is None:
                print("Credential not found", file=sys.stderr)
                return 2
            revoke_credential(session, credential)
            session.commit()
            print(f"Revoked credential {credential.id}")
        return 0
    finally:
        engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="graphloom", description="Graphloom local administration")
    sub = parser.add_subparsers(dest="command", required=True)

    owner = sub.add_parser("init-owner", help="Create the local owner credential")
    owner.add_argument("--label", default="owner")
    owner.add_argument("--rotate", action="store_true", help="Revoke existing owner tokens first")
    owner.set_defaults(handler=init_owner)

    reader = sub.add_parser("create-reader", help="Create a project-scoped reader credential")
    reader.add_argument("--label", required=True)
    reader.add_argument("--project-id", action="append", default=[])
    reader.set_defaults(handler=create_reader)

    listing = sub.add_parser("list-credentials", help="List owner and reader credentials")
    listing.set_defaults(handler=list_credentials)

    revoker = sub.add_parser("revoke", help="Revoke a credential by id")
    revoker.add_argument("--credential-id", required=True)
    revoker.set_defaults(handler=revoke)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args, Settings())


if __name__ == "__main__":
    raise SystemExit(main())
