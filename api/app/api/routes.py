from datetime import datetime, timezone
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_demo_or_authenticated_context
from app.core.context import RequestContext
from app.domain.audit import emit_audit_event
from app.domain.models import (
    AuditHistoryResponse,
    DeviceIntentCreateRequest,
    DeviceIntentCreateResponse,
    DeviceListResponse,
    DeviceStateUpdateRequest,
    DeviceUpdateResponse,
    HouseholdContextResponse,
)
from app.domain.repository import domain_repository

router = APIRouter(tags=["nestra-demo"])


@router.get("/household/context", response_model=HouseholdContextResponse)
def get_household_context(
    context: Annotated[RequestContext, Depends(get_demo_or_authenticated_context)],
) -> HouseholdContextResponse:
    tenant, household, actor = domain_repository.get_household_context(context)
    return HouseholdContextResponse(tenant=tenant, household=household, actor=actor)


@router.get("/devices", response_model=DeviceListResponse)
def list_devices(
    context: Annotated[RequestContext, Depends(get_demo_or_authenticated_context)],
) -> DeviceListResponse:
    items = domain_repository.list_devices(context)
    return DeviceListResponse(
        tenant_id=context.tenant_id,
        household_id=context.household_id,
        items=items,
    )


@router.get("/audit-events", response_model=AuditHistoryResponse)
def list_audit_events(
    context: Annotated[RequestContext, Depends(get_demo_or_authenticated_context)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AuditHistoryResponse:
    items = domain_repository.list_audit_events(context, limit)
    return AuditHistoryResponse(
        tenant_id=context.tenant_id,
        household_id=context.household_id,
        items=items,
    )


@router.patch("/devices/{device_id}/state", response_model=DeviceUpdateResponse)
def update_device_state(
    device_id: str,
    payload: DeviceStateUpdateRequest,
    context: Annotated[RequestContext, Depends(get_demo_or_authenticated_context)],
) -> DeviceUpdateResponse:
    device = domain_repository.get_device(context, device_id)
    requested = payload.state.model_dump(exclude_none=True)

    if context.actor_role == "guest" and ("lock_state" in requested or device.type == "lock"):
        blocked = emit_audit_event(
            context=context,
            action="device.state.update",
            resource_type="device",
            resource_id=device_id,
            outcome="blocked",
            reason="guest-cannot-control-locks",
            metadata={"requested": requested},
        )
        raise HTTPException(
            status_code=403,
            detail={
                "code": "forbidden",
                "message": "Guest actors cannot modify lock state.",
                "audit_event_id": blocked.event_id,
            },
        )

    updated = domain_repository.update_state(context, device_id, payload.state)
    event = emit_audit_event(
        context=context,
        action="device.state.update",
        resource_type="device",
        resource_id=device_id,
        outcome="allowed",
        metadata={"requested": requested},
    )
    return DeviceUpdateResponse(device=updated, audit_event_id=event.event_id)


@router.post("/device-intents", response_model=DeviceIntentCreateResponse)
def create_device_intent(
    payload: DeviceIntentCreateRequest,
    context: Annotated[RequestContext, Depends(get_demo_or_authenticated_context)],
) -> DeviceIntentCreateResponse:
    _, _, actor = domain_repository.get_household_context(context)

    requires_confirmation = True
    status = "accepted"
    reason: str | None = None
    title = "Action accepted"
    message = "Nestra accepted the requested automation action."
    next_step: str | None = None
    guardrail_rule = "Action-specific guardrail policy"

    if payload.intent_type == "shift_ev_charging_low_tariff_window":
        start = payload.payload.get("window_start")
        end = payload.payload.get("window_end")
        if not start or not end:
            raise HTTPException(
                status_code=422,
                detail="EV intent requires payload.window_start and payload.window_end",
            )
        if not re.match(r"^([01][0-9]|2[0-3]):[0-5][0-9]$", str(start)) or not re.match(
            r"^([01][0-9]|2[0-3]):[0-5][0-9]$", str(end)
        ):
            raise HTTPException(status_code=422, detail="EV time values must be HH:MM")

        guardrail_rule = (
            "Only owner/resident can schedule EV charging, explicit confirmation is required, "
            "and window must overlap low-tariff period (22:00-07:00)."
        )
        start_hour = int(str(start).split(":", 1)[0])
        end_hour = int(str(end).split(":", 1)[0])
        overlaps_low_tariff = start_hour >= 22 or end_hour <= 7

        title = "EV charging plan accepted"
        message = "Nestra scheduled EV charging for low-tariff hours."
        if actor.role == "guest":
            status = "blocked"
            reason = "guest-cannot-schedule-ev-charging"
            title = "Action blocked"
            message = "Guest actors cannot schedule EV charging windows."
        elif not payload.confirm:
            status = "pending_confirmation"
            reason = "confirmation-required-for-ev-tariff-shift"
            title = "Confirmation required"
            message = "Confirm this EV charging shift before Nestra applies it."
            next_step = "Resubmit with confirm=true."
        elif not overlaps_low_tariff:
            status = "blocked"
            reason = "window-outside-low-tariff-period"
            title = "Action blocked"
            message = "Requested window does not overlap low-tariff period."
            next_step = "Choose a window between 22:00 and 07:00."

    elif payload.intent_type == "arm_night_security_sweep":
        arm_time = payload.payload.get("arm_time")
        zones = payload.payload.get("zones")
        if not arm_time or not re.match(r"^([01][0-9]|2[0-3]):[0-5][0-9]$", str(arm_time)):
            raise HTTPException(status_code=422, detail="Security sweep requires payload.arm_time HH:MM")
        if zones is not None and not isinstance(zones, list):
            raise HTTPException(status_code=422, detail="payload.zones must be a list of zone names")

        guardrail_rule = (
            "Security sweep requires owner role and explicit confirmation. "
            "Guests and residents cannot arm whole-home night sweep."
        )
        title = "Night security sweep accepted"
        message = "Nestra scheduled the home security sweep and door lock verification."
        if actor.role != "owner":
            status = "blocked"
            reason = "only-owner-can-arm-night-security-sweep"
            title = "Action blocked"
            message = "Only owner role can arm full-night security sweep."
        elif not payload.confirm:
            status = "pending_confirmation"
            reason = "confirmation-required-for-night-security-sweep"
            title = "Confirmation required"
            message = "Confirm this security sweep to arm all selected zones."
            next_step = "Resubmit with confirm=true."

    elif payload.intent_type == "preheat_home_arrival":
        arrival_time = payload.payload.get("arrival_time")
        target_temp = payload.payload.get("target_temperature_c")
        if not arrival_time or not re.match(r"^([01][0-9]|2[0-3]):[0-5][0-9]$", str(arrival_time)):
            raise HTTPException(status_code=422, detail="Preheat intent requires payload.arrival_time HH:MM")
        if target_temp is None:
            raise HTTPException(status_code=422, detail="Preheat intent requires payload.target_temperature_c")
        try:
            temp = float(target_temp)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="target_temperature_c must be numeric") from exc

        guardrail_rule = (
            "Preheat is allowed for owner/resident with explicit confirmation and safe target range "
            "between 18C and 24C."
        )
        title = "Arrival preheat accepted"
        message = "Nestra scheduled climate preheat before household arrival."
        if actor.role == "guest":
            status = "blocked"
            reason = "guest-cannot-preheat-home-arrival"
            title = "Action blocked"
            message = "Guest actors cannot schedule whole-home climate preheat."
        elif not payload.confirm:
            status = "pending_confirmation"
            reason = "confirmation-required-for-preheat"
            title = "Confirmation required"
            message = "Confirm preheat to apply this comfort plan."
            next_step = "Resubmit with confirm=true."
        elif not (18.0 <= temp <= 24.0):
            status = "blocked"
            reason = "target-temperature-outside-safe-range"
            title = "Action blocked"
            message = "Target temperature must be within 18C to 24C safety range."
            next_step = "Choose a value between 18 and 24C."

    else:
        raise HTTPException(status_code=400, detail="Unsupported intent type")

    confirmed_at = datetime.now(timezone.utc).isoformat() if status == "accepted" else None
    intent = domain_repository.create_intent(
        context=context,
        intent_type=payload.intent_type,
        payload=payload.payload,
        status=status,
        requires_confirmation=requires_confirmation,
        confirmed_at=confirmed_at,
    )

    event = emit_audit_event(
        context=context,
        action="device_intent.create",
        resource_type="device_intent",
        resource_id=intent.id,
        outcome="allowed" if status == "accepted" else "blocked",
        reason=reason,
        metadata={"intent_type": payload.intent_type, "status": status},
    )

    return DeviceIntentCreateResponse(
        intent=intent,
        audit_event_id=event.event_id,
        status=status,
        title=title,
        message=message,
        next_step=next_step,
        guardrail=guardrail_rule,
    )
