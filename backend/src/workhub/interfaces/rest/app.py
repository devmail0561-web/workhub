"""Application FastAPI — point d'entrée HTTP."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from workhub import __version__
from workhub.interfaces.rest.auth import router as auth_router
from workhub.interfaces.rest.errors import ERROR_RESPONSES, install_error_handlers
from workhub.interfaces.rest.logging import configure_logging
from workhub.interfaces.rest.middleware import RequestContextMiddleware

configure_logging()

app = FastAPI(title="WorkHub API", version=__version__, responses=ERROR_RESPONSES)
install_error_handlers(app)
app.add_middleware(RequestContextMiddleware)
app.include_router(auth_router)


class HealthResponse(BaseModel):
    """Réponse de la sonde de santé."""

    status: Literal["ok"]
    version: str


@app.get("/api/v1/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Sonde de santé utilisée par Docker et la CI."""
    return HealthResponse(status="ok", version=__version__)
