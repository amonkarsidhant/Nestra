import os
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.core.db import get_db, init_db
from app.core.security import build_access_token, decode_access_token, verify_password

app = FastAPI(title="Nestra Auth", version="0.1.0")

allowed_origin = os.getenv("CORS_ORIGIN", "https://nestra.homelabdev.space")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[allowed_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    username: str
    password: str


class ActorContext(BaseModel):
    tenant_id: str
    household_id: str
    actor_id: str
    actor_role: str = Field(pattern="^(owner|resident|guest)$")
    display_name: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    auth_mode: str
    actor_context: ActorContext


def get_bearer_token(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return authorization.split(" ", 1)[1]


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "nestra-auth"}


@app.get("/.well-known/openid-configuration")
def oidc_discovery() -> dict:
    issuer = os.getenv("AUTH_ISSUER", "https://auth.nestra.homelabdev.space")
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "userinfo_endpoint": f"{issuer}/userinfo",
        "jwks_uri": f"{issuer}/jwks.json",
        "response_types_supported": [],
        "grant_types_supported": [],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["HS256"],
        "note": "alpha-demo-auth-only: this metadata is intentionally partial and not production OIDC.",
        "alpha_demo_only": True,
    }


@app.post("/v1/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT username, password_hash, display_name, tenant_id,
                   household_id, actor_id, actor_role
            FROM demo_users
            WHERE username = ?
            """,
            (payload.username,),
        ).fetchone()

    if not row or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    claims = {
        "sub": row["username"],
        "tenant_id": row["tenant_id"],
        "household_id": row["household_id"],
        "actor_id": row["actor_id"],
        "actor_role": row["actor_role"],
        "display_name": row["display_name"],
    }
    token = build_access_token(claims)
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        auth_mode="alpha_demo",
        actor_context=ActorContext(
            tenant_id=row["tenant_id"],
            household_id=row["household_id"],
            actor_id=row["actor_id"],
            actor_role=row["actor_role"],
            display_name=row["display_name"],
        ),
    )


@app.get("/v1/me", response_model=ActorContext)
def me(token: Annotated[str, Depends(get_bearer_token)]) -> ActorContext:
    try:
        claims = decode_access_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    return ActorContext(
        tenant_id=claims["tenant_id"],
        household_id=claims["household_id"],
        actor_id=claims["actor_id"],
        actor_role=claims["actor_role"],
        display_name=claims.get("display_name", claims.get("sub", "unknown")),
    )


@app.post("/v1/logout")
def logout() -> dict:
    return {
        "status": "ok",
        "message": "Alpha logout is client-side token discard.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
