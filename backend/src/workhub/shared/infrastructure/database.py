"""Moteur et session SQLAlchemy (infrastructure partagée)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base déclarative des modèles SQLAlchemy."""


def create_engine(database_url: str) -> AsyncEngine:
    """Crée un moteur asynchrone avec vérification de connexion."""
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Fabrique de sessions asynchrones (objets expirés non rechargés après commit)."""
    return async_sessionmaker(engine, expire_on_commit=False)
