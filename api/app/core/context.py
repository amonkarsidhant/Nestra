from typing import Annotated

from fastapi import Header, HTTPException
from pydantic import BaseModel, Field


class RequestContext(BaseModel):
    tenant_id: str = Field(min_length=2, max_length=64)
    household_id: str = Field(min_length=2, max_length=64)
    actor_id: str = Field(min_length=2, max_length=64)
    actor_role: str = Field(default="resident", pattern="^(owner|resident|guest)$")


def get_request_context(
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
    x_household_id: Annotated[str | None, Header(alias="X-Household-Id")] = None,
    x_actor_id: Annotated[str | None, Header(alias="X-Actor-Id")] = None,
    x_actor_role: Annotated[str | None, Header(alias="X-Actor-Role")] = None,
) -> RequestContext:
    if not x_tenant_id or not x_household_id or not x_actor_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Missing required context headers: X-Tenant-Id, X-Household-Id, X-Actor-Id"
            ),
        )

    role = x_actor_role or "resident"
    return RequestContext(
        tenant_id=x_tenant_id,
        household_id=x_household_id,
        actor_id=x_actor_id,
        actor_role=role,
    )
