import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, processes, files, results, classifications, adjustments, alerts, bitso, warren, sftp

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


@app.get("/health")
def health():
    return {"status": "ok", "service": "TrueBook API v2"}
