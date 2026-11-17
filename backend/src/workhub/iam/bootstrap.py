"""Commande d'amorçage du premier administrateur WorkHub."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from workhub.iam.application.bootstrap import bootstrap_admin
from workhub.iam.application.views import UserView
from workhub.iam.infrastructure.database import create_engine, create_session_factory
from workhub.iam.infrastructure.repositories import SqlAlchemyUserRepository
from workhub.iam.infrastructure.security import Argon2PasswordHasher
from workhub.shared.api import SystemClock, WorkHubError

_PASSWORD_ENV = "WORKHUB_BOOTSTRAP_PASSWORD"


def _read_password() -> str:
    from_env = os.environ.get(_PASSWORD_ENV)
    if from_env:
        return from_env
    if sys.stdin.isatty():
        first = getpass.getpass("Mot de passe administrateur : ")
        second = getpass.getpass("Confirmation : ")
        if first != second:
            raise ValueError("Les mots de passe ne correspondent pas")
        return first
    return sys.stdin.readline().rstrip("\n")


async def _run(email: str, display_name: str, password: str) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL est requis", file=sys.stderr)
        return 1

    engine = create_engine(database_url)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            view = await _create_admin(session, email, display_name, password)
            await session.commit()
    finally:
        await engine.dispose()

    print(f"Administrateur créé : {view.email} ({view.id})")
    return 0


async def _create_admin(
    session: AsyncSession,
    email: str,
    display_name: str,
    password: str,
) -> UserView:
    return await bootstrap_admin(
        users=SqlAlchemyUserRepository(session),
        password_hasher=Argon2PasswordHasher(),
        clock=SystemClock(),
        email=email,
        display_name=display_name,
        password=password,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Point d'entrée `workhub-bootstrap`."""
    parser = argparse.ArgumentParser(
        prog="workhub-bootstrap",
        description="Crée le premier compte administrateur WorkHub.",
    )
    parser.add_argument("--email", required=True, help="Adresse e-mail de l'administrateur")
    parser.add_argument(
        "--display-name",
        help="Nom affiché (par défaut : partie locale de l'e-mail)",
    )
    args = parser.parse_args(argv)

    display_name = args.display_name or args.email.split("@", maxsplit=1)[0]
    try:
        password = _read_password()
        return asyncio.run(_run(args.email, display_name, password))
    except (ValueError, WorkHubError) as exc:
        print(f"Échec : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
