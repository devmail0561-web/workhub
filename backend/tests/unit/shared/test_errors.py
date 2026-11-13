import pytest

from workhub.shared.api import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    PreconditionFailedError,
    RateLimitedError,
    ValidationError,
    WorkHubError,
)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ValidationError("x"), "validation_error"),
        (AuthenticationError("x"), "authentication_required"),
        (PermissionDeniedError("x"), "permission_denied"),
        (NotFoundError("x"), "not_found"),
        (ConflictError("x"), "conflict"),
        (PreconditionFailedError("x"), "precondition_failed"),
        (RateLimitedError("x"), "rate_limited"),
        (WorkHubError("x"), "internal_error"),
    ],
)
def test_error_codes(error: WorkHubError, code: str) -> None:
    assert error.code == code
    assert str(error) == "x"


def test_details_are_copied() -> None:
    details: dict[str, object] = {"field": "slug"}
    error = ValidationError("invalide", details=details)
    details["field"] = "name"

    assert error.details == {"field": "slug"}
    assert error.message == "invalide"


def test_details_default_to_empty_mapping() -> None:
    assert ConflictError("conflit").details == {}
