from datetime import datetime
from typing import Annotated
from typing import Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator


DeviceType = Literal["thermostat", "lock", "light", "sensor", "plug", "camera", "blind"]
ActorRole = Literal["owner", "resident", "guest"]
IntentType = Literal[
    "shift_ev_charging_low_tariff_window",
    "arm_night_security_sweep",
    "preheat_home_arrival",
]


class Tenant(BaseModel):
    id: str
    name: str


class Household(BaseModel):
    id: str
    tenant_id: str
    name: str
    timezone: str


class Actor(BaseModel):
    id: str
    tenant_id: str
    household_id: str
    name: str
    role: ActorRole


class HouseholdContextResponse(BaseModel):
    tenant: Tenant
    household: Household
    actor: Actor


class DeviceState(BaseModel):
    on_off: bool | None = None
    brightness: int | None = Field(default=None, ge=0, le=100)
    lock_state: Literal["locked", "unlocked"] | None = None
    target_temperature_c: float | None = Field(default=None, ge=5.0, le=35.0)


class Device(BaseModel):
    id: str
    name: str
    type: DeviceType
    online: bool
    room: str | None = None
    last_seen: datetime
    state: DeviceState = Field(default_factory=DeviceState)


class DeviceListResponse(BaseModel):
    tenant_id: str
    household_id: str
    items: list[Device]


class DeviceStateUpdateRequest(BaseModel):
    state: DeviceState


class DeviceUpdateResponse(BaseModel):
    device: Device
    audit_event_id: str


TimeHHMM = Annotated[str, StringConstraints(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]


class ShiftEvChargingPayload(BaseModel):
    window_start: TimeHHMM
    window_end: TimeHHMM

    @model_validator(mode="after")
    def validate_window(self) -> "ShiftEvChargingPayload":
        if self.window_start == self.window_end:
            raise ValueError("window_start and window_end must be different")
        return self


class DeviceIntentCreateRequest(BaseModel):
    intent_type: IntentType
    payload: dict
    confirm: bool = False


class DeviceIntent(BaseModel):
    id: str
    tenant_id: str
    household_id: str
    actor_id: str
    intent_type: str
    payload: dict
    status: Literal["pending_confirmation", "accepted", "blocked"]
    requires_confirmation: bool
    created_at: datetime
    confirmed_at: datetime | None = None


class DeviceIntentCreateResponse(BaseModel):
    intent: DeviceIntent
    audit_event_id: str
    status: Literal["accepted", "blocked", "pending_confirmation"]
    title: str
    message: str
    next_step: str | None = None
    guardrail: str


class AuditEvent(BaseModel):
    event_id: str
    occurred_at: datetime
    tenant_id: str
    household_id: str
    actor_id: str
    actor_role: ActorRole
    action: str
    resource_type: str
    resource_id: str
    outcome: Literal["allowed", "blocked"]
    reason: str | None = None
    metadata: dict = Field(default_factory=dict)


class AuditHistoryResponse(BaseModel):
    tenant_id: str
    household_id: str
    items: list[AuditEvent]
