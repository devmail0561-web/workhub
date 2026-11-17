"""Amorçage du premier administrateur, sans compte par défaut."""

from __future__ import annotations

from workhub.iam.application.ports import PasswordHasher, UserRepository
from workhub.iam.application.views import UserView
from workhub.iam.domain.user import User, normalize_email, validate_password
from workhub.shared.api import Clock, ConflictError, IdFactory, ValidationError, new_id


async def bootstrap_admin(
    *,
    users: UserRepository,
    password_hasher: PasswordHasher,
    clock: Clock,
    email: str,
    display_name: str,
    password: str,
    id_factory: IdFactory = new_id,
) -> UserView:
    """Crée un administrateur si l'e-mail est libre.

    La commande est volontairement non interactive par défaut : le mot de passe doit venir
    d'une entrée dédiée, jamais d'un argument de ligne de commande visible dans `ps`.
    """
    normalized_email = normalize_email(email)
    normalized_name = display_name.strip()
    if not normalized_name or len(normalized_name) > 200:
        raise ValidationError("Le nom affiché doit contenir entre 1 et 200 caractères")
    validate_password(password)

    if await users.find_by_email(normalized_email) is not None:
        raise ConflictError("Un compte utilise déjà cette adresse e-mail")

    now = clock.now()
    user = User(
        id=id_factory(),
        email=normalized_email,
        password_hash=password_hasher.hash(password),
        display_name=normalized_name,
        is_active=True,
        is_admin=True,
        created_at=now,
        updated_at=now,
    )
    await users.add(user)
    return UserView.from_user(user)
