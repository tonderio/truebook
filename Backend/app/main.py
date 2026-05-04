import logging
import os
import sys

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import (
    auth, processes, files, results, classifications,
    adjustments, alerts, bitso, warren, sftp, banregio_report,
)

# ── Logging ────────────────────────────────────────────────────────────
# Ensure all logs (uvicorn + our own) go to stdout so Railway captures them
# and include tracebacks from our `logger.exception(...)` calls.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TrueBook — FinOps Reconciliation API",
    version="2.0.0",
    description="Plataforma de conciliación financiera de Tonder — TrueBook v2",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Catch every unhandled exception, log the full traceback to stdout
    (visible via `railway logs --service truebook`), and return a 500
    JSON response with the exception class + message in `detail` so the
    frontend error box can show something actionable without requiring
    log access.
    """
    logger.exception(
        "Unhandled %s on %s %s — %s",
        type(exc).__name__,
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )


app.include_router(auth.router)
app.include_router(processes.router)
app.include_router(files.router)
app.include_router(results.router)
app.include_router(classifications.router)
app.include_router(adjustments.router)
app.include_router(alerts.router)
app.include_router(bitso.router)
app.include_router(warren.router)
app.include_router(sftp.router)
app.include_router(banregio_report.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "TrueBook API v2"}
