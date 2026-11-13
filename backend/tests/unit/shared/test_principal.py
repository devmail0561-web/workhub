from uuid import UUID

import pytest

from workhub.shared.api import PermissionDeniedError, Principal, PrincipalType


def _principal(*scopes: str) -> Principal:
    return Principal(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        type=PrincipalType.USER,
        display_name="Test",
        scopes=frozenset(scopes),
    )


def test_has_scope_exact() -> None:
    principal = _principal("skills:read")
    assert principal.has_scope("skills:read")
    assert not principal.has_scope("skills:write")


def test_has_scope_wildcards() -> None:
    assert _principal("*").has_scope("projects:write")
    assert _principal("skills:*").has_scope("skills:read")
    assert _principal("skills:*").has_scope("skills:write")
    assert not _principal("skills:*").has_scope("projects:read")


def test_require_scope_raises_permission_denied() -> None:
    with pytest.raises(PermissionDeniedError) as excinfo:
        _principal("skills:read").require_scope("skills:write")

    error = excinfo.value
    assert error.code == "permission_denied"
    assert error.details["required_scope"] == "skills:write"
    assert error.details["principal_type"] == "user"


def test_require_scope_accepts_granted_scope() -> None:
    _principal("skills:write").require_scope("skills:write")


def test_system_principal_has_all_scopes() -> None:
    system = Principal.system()
    assert system.type is PrincipalType.SYSTEM
    assert system.id == UUID(int=0)
    assert system.has_scope("anything:read")


def test_principal_is_frozen() -> None:
    principal = _principal("skills:read")
    with pytest.raises(AttributeError):
        principal.display_name = "autre"  # type: ignore[misc]
