import os
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException

from app.core.context import RequestContext


def _jwt_secret() -> str:
    return os.getenv("AUTH_JWT_SECRET", "change-me")


def get_bearer_token(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return authorization.split(" ", 1)[1]


def _demo_mode_enabled() -> bool:
    return os.getenv("DEMO_MODE_PUBLIC", "true").lower() == "true"


def _demo_context() -> RequestContext:
    return RequestContext(
        tenant_id=os.getenv("DEMO_TENANT_ID", "default-tenant"),
        household_id=os.getenv("DEMO_HOUSEHOLD_ID", "default-home"),
        actor_id=os.getenv("DEMO_ACTOR_ID", "owner-1"),
        actor_role=os.getenv("DEMO_ACTOR_ROLE", "owner"),
    )


def get_authenticated_context(token: Annotated[str, Depends(get_bearer_token)]) -> RequestContext:
    try:
        claims = jwt.decode(token, _jwt_secret(), algorithms=["HS256"], audience="nestra-api")
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    required = ["tenant_id", "household_id", "actor_id", "actor_role"]
    missing = [key for key in required if key not in claims]
    if missing:
        raise HTTPException(status_code=401, detail=f"Token missing required claims: {missing}")

    return RequestContext(
        tenant_id=claims["tenant_id"],
        household_id=claims["household_id"],
        actor_id=claims["actor_id"],
        actor_role=claims["actor_role"],
    )


def get_demo_or_authenticated_context(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> RequestContext:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        return get_authenticated_context(token)

    if _demo_mode_enabled():
        return _demo_context()

    raise HTTPException(status_code=401, detail="Missing bearer token")
