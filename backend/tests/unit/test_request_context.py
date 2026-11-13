from uuid import UUID

import httpx
from fastapi import FastAPI
from structlog.testing import capture_logs

from workhub.interfaces.rest.errors import install_error_handlers
from workhub.interfaces.rest.middleware import RequestContextMiddleware
from workhub.shared.api import NotFoundError

app = FastAPI()
install_error_handlers(app)
app.add_middleware(RequestContextMiddleware)


@app.get("/ok")
async def _ok() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/missing")
async def _missing() -> None:
    raise NotFoundError("absente")


@app.get("/boom")
async def _boom() -> None:
    raise RuntimeError("boom")


async def _get(
    path: str,
    *,
    headers: dict[str, str] | None = None,
    raise_app_exceptions: bool = True,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers=headers)


async def test_request_id_is_generated() -> None:
    response = await _get("/ok")

    request_id = response.headers["X-Request-ID"]
    assert UUID(request_id).version == 4


async def test_request_id_is_propagated_when_valid() -> None:
    response = await _get("/ok", headers={"X-Request-ID": "req-42"})

    assert response.headers["X-Request-ID"] == "req-42"


async def test_invalid_request_id_is_replaced() -> None:
    response = await _get("/ok", headers={"X-Request-ID": "bad id!"})

    assert response.headers["X-Request-ID"] != "bad id!"
    UUID(response.headers["X-Request-ID"])


async def test_error_envelope_contains_request_id() -> None:
    response = await _get("/missing", headers={"X-Request-ID": "req-42"})

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "req-42"
    assert response.json()["error"]["request_id"] == "req-42"


async def test_successful_request_is_logged() -> None:
    with capture_logs() as logs:
        response = await _get("/ok", headers={"X-Request-ID": "req-42"})

    assert response.status_code == 200
    entry = next(item for item in logs if item["event"] == "http.request")
    assert entry["request_id"] == "req-42"
    assert entry["method"] == "GET"
    assert entry["path"] == "/ok"
    assert entry["status_code"] == 200
    assert isinstance(entry["duration_ms"], float)
    assert entry["log_level"] == "info"


async def test_unhandled_error_is_logged() -> None:
    with capture_logs() as logs:
        response = await _get("/boom", raise_app_exceptions=False)

    assert response.status_code == 500
    entry = next(item for item in logs if item["event"] == "http.request")
    assert entry["status_code"] == 500
    assert entry["log_level"] == "error"
    assert entry["request_id"]
