from datetime import datetime, timezone
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as v1_router
from app.core.db import init_db

app = FastAPI(
    title="Nestra API",
    version="0.2.0",
    description=(
        "Nestra control-plane API bootstrap with explicit tenant and household boundaries, "
        "typed contracts, and audit event hooks."
    ),
)

allowed_origin = os.getenv("CORS_ORIGIN", "https://nestra.homelabdev.space")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[allowed_origin],
    allow_credentials=False,
    allow_methods=["GET", "PATCH", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "service": "nestra-api"}


@app.get("/v1/status", tags=["system"])
def status() -> dict:
    return {
        "name": "nestra-api",
        "version": "0.2.0",
        "environment": "production",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "capabilities": {
            "tenant_context": True,
            "household_context": True,
            "audit_events": True,
            "persistent_storage": True,
            "alpha_token_auth": True,
        },
    }


@app.on_event("startup")
def startup() -> None:
    init_db()


app.include_router(v1_router, prefix="/v1")
