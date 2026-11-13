import httpx
import pytest
from fastapi import FastAPI

from workhub.interfaces.rest.errors import install_error_handlers, status_for
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

app = FastAPI()
install_error_handlers(app)


@app.get("/not-found")
async def _not_found() -> None:
    raise NotFoundError("Skill absente", details={"slug": "inconnue"})


@app.get("/internal")
async def _internal() -> None:
    raise WorkHubError("échec interne")


@app.get("/items/{item_id}")
async def _item(item_id: int) -> dict[str, int]:
    return {"item_id": item_id}


async def _get(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


async def test_workhub_error_envelope() -> None:
    response = await _get("/not-found")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Skill absente",
            "details": {"slug": "inconnue"},
            "request_id": None,
        }
    }


async def test_internal_error_envelope() -> None:
    response = await _get("/internal")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"


async def test_request_validation_envelope() -> None:
    response = await _get("/items/abc")

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]["errors"]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ValidationError("x"), 422),
        (AuthenticationError("x"), 401),
        (PermissionDeniedError("x"), 403),
        (NotFoundError("x"), 404),
        (ConflictError("x"), 409),
        (PreconditionFailedError("x"), 412),
        (RateLimitedError("x"), 429),
        (WorkHubError("x"), 500),
    ],
)
def test_status_for(error: WorkHubError, expected: int) -> None:
    assert status_for(error) == expected
