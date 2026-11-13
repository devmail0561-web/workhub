"""Application FastAPI — point d'entrée HTTP."""

from fastapi import FastAPI

from workhub import __version__
from workhub.interfaces.rest.errors import install_error_handlers
from workhub.interfaces.rest.logging import configure_logging
from workhub.interfaces.rest.middleware import RequestContextMiddleware

configure_logging()

app = FastAPI(title="WorkHub API", version=__version__)
install_error_handlers(app)
app.add_middleware(RequestContextMiddleware)


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    """Sonde de santé utilisée par Docker et la CI."""
    return {"status": "ok", "version": __version__}
