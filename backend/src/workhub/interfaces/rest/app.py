"""Application FastAPI — point d'entrée HTTP."""

from fastapi import FastAPI

from workhub import __version__

app = FastAPI(title="WorkHub API", version=__version__)


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    """Sonde de santé utilisée par Docker et la CI."""
    return {"status": "ok", "version": __version__}
