from datetime import datetime, timezone
import json
import logging
import os
import re
import time
from typing import Annotated
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.core.auth import get_demo_or_authenticated_context
from app.core.context import RequestContext
from app.core.voice import transcribe_audio_with_telemetry
from app.domain.audit import emit_audit_event
from app.domain.models import (
    AssistantAction,
    AssistantTurnRequest,
    AssistantTurnResponse,
    AuditHistoryResponse,
    DeviceIntentCreateRequest,
    DeviceIntentCreateResponse,
    DeviceListResponse,
    DeviceStateUpdateRequest,
    DeviceUpdateResponse,
    ExecutedAction,
    HouseholdContextResponse,
    Memory,
    MemoryCreateRequest,
    MemorySearchResponse,
    VoiceTranscriptionResponse,
)
from app.domain.repository import domain_repository

router = APIRouter(tags=["nestra-demo"])
logger = logging.getLogger("uvicorn.error")

SUPPORTED_INTENTS = {
    "shift_ev_charging_low_tariff_window",
    "arm_night_security_sweep",
    "preheat_home_arrival",
    "remember_fact",
}

def _sanitize_assistant_reply(text: str) -> str:
    sanitized = text or ""
    sensitive_terms = [
        "nvidia",
        "nim",
        "litellm",
        "model",
        "step-3.5",
        "qwen",
        "deepseek",
        "llama",
    ]
    lowered = sanitized.lower()
    if any(term in lowered for term in sensitive_terms):
        return "I completed that request using my assistant backend."
    return sanitized


# Action tag parsing: [DEVICE:<device_id>:<action>[:<value>]]
ACTION_TAG_RE = re.compile(r"\[DEVICE:([a-zA-Z0-9_-]+):([a-zA-Z0-9_]+)(?::([^\]]+))?\]")


def _parse_action_tags(text: str) -> list[dict]:
    actions = []
    for match in ACTION_TAG_RE.finditer(text):
        device_id = match.group(1)
        action = match.group(2).lower()
        raw_value = match.group(3)
        value = None
        if raw_value:
            try:
                if raw_value.replace(".", "", 1).isdigit():
                    value = float(raw_value) if "." in raw_value else int(raw_value)
                elif raw_value.lower() in ("true", "false"):
                    value = raw_value.lower() == "true"  # type: ignore[assignment]
                else:
                    value = raw_value
            except Exception:
                value = raw_value
        actions.append({
            "device_id": device_id,
            "action": action,
            "value": value,
            "raw": match.group(0),
        })
    return actions


def _execute_action_tags(
    context: RequestContext, actions: list[dict], reply_text: str
) -> list[ExecutedAction]:
    executed: list[ExecutedAction] = []
    for act in actions:
        device_id = act["device_id"]
        action = act["action"]
        value = act["value"]
        try:
            device = domain_repository.get_device(context, device_id)
            updates = {}
            if action in ("on", "off"):
                updates["on_off"] = action == "on"
            elif action == "toggle":
                updates["on_off"] = not device.state.on_off
            elif action == "brightness":
                if isinstance(value, (int, float)):
                    pct = max(0, min(100, int(value)))
                    updates["brightness"] = pct
                else:
                    raise ValueError("Brightness requires numeric value")
            elif action == "lock":
                if value in ("locked", "unlocked"):
                    updates["lock_state"] = value  # type: ignore[assignment]
                else:
                    raise ValueError("Lock state must be 'locked' or 'unlocked'")
            elif action == "temperature":
                if isinstance(value, (int, float)):
                    updates["target_temperature_c"] = float(value)
                else:
                    raise ValueError("Temperature requires numeric value")
            else:
                executed.append(ExecutedAction(
                    type="device",
                    device_id=device_id,
                    action=action,
                    value=value,
                    status="skipped",
                    message=f"Unsupported action: {action}"
                ))
                continue

            from app.domain.models import DeviceState
            new_state = DeviceState(**updates)
            updated = domain_repository.update_state(context, device_id, new_state)
            audit = AuditEvent(
                event_id=f"evt_{uuid4().hex}",
                occurred_at=datetime.utcnow(),
                tenant_id=context.tenant_id,
                household_id=context.household_id,
                actor_id=context.actor_id,
                actor_role=context.actor_role,
                action=f"device.{action}",
                resource_type="device",
                resource_id=device_id,
                outcome="allowed",
                reason=None,
                metadata={"state": updated.state.model_dump()},
            )
            domain_repository.write_audit_event(audit)
            executed.append(ExecutedAction(
                type="device",
                device_id=device_id,
                action=action,
                value=value,
                status="completed",
                message=f"{device.name}: {action} applied."
            ))
        except HTTPException as e:
            executed.append(ExecutedAction(
                type="device",
                device_id=device_id,
                action=action,
                value=value,
                status="failed",
                message=e.detail if hasattr(e, "detail") else "Device not found or unauthorized"
            ))
        except Exception as e:
            executed.append(ExecutedAction(
                type="device",
                device_id=device_id,
                action=action,
                value=value,
                status="failed",
                message=str(e)
            ))
    return executed


def _handle_remember_fact(text: str, context: RequestContext) -> AssistantTurnResponse:
    cleaned = re.sub(r"^remember\s+(that\s+)?", "", text.strip(), flags=re.I).strip()
    if "=" in cleaned:
        key, value = cleaned.split("=", 1)
    elif " is " in cleaned:
        parts = cleaned.split(" is ", 1)
        key, value = parts[0], parts[1]
    elif " are " in cleaned:
        parts = cleaned.split(" are ", 1)
        key, value = parts[0], parts[1]
    else:
        return AssistantTurnResponse(
            input_text=text,
            reply_text="I couldn't understand what to remember. Try 'remember that the preferred temperature is 22 degrees'.",
            action=AssistantAction(type="remember_fact", status="none"),
        )
    key = key.strip().lower().replace(" ", "_")
    value = value.strip().strip(" .")
    memory = domain_repository.create_memory(context.actor_id, key, value)
    return AssistantTurnResponse(
        input_text=text,
        reply_text=f"Got it. I'll remember that {key.replace('_', ' ')} is {value}.",
        action=AssistantAction(type="remember_fact", status="completed"),
        executed_actions=[],
    )


# Action tag parsing: [DEVICE:<device_id>:<action>[:<value>]]
ACTION_TAG_RE = re.compile(r"\[DEVICE:([a-zA-Z0-9_-]+):([a-zA-Z0-9_]+)(?::([^\]]+))?\]")


def _parse_action_tags(text: str) -> list[dict]:
    actions = []
    for match in ACTION_TAG_RE.finditer(text):
        device_id = match.group(1)
        action = match.group(2).lower()
        raw_value = match.group(3)
        value = None
        if raw_value:
            try:
                if raw_value.replace(".", "", 1).isdigit():
                    value = float(raw_value) if "." in raw_value else int(raw_value)
                elif raw_value.lower() in ("true", "false"):
                    value = raw_value.lower() == "true"
                else:
                    value = raw_value
            except Exception:
                value = raw_value
        actions.append({
            "device_id": device_id,
            "action": action,
            "value": value,
            "raw": match.group(0),
        })
    return actions


def _execute_action_tags(
    context: RequestContext, actions: list[dict], reply_text: str
) -> list[ExecutedAction]:
    executed: list[ExecutedAction] = []
    for act in actions:
        device_id = act["device_id"]
        action = act["action"]
        value = act["value"]
        try:
            # Verify device belongs to household
            device = domain_repository.get_device(context, device_id)
            # Determine state changes
            updates = {}
            if action in ("on", "off"):
                updates["on_off"] = action == "on"
            elif action == "toggle":
                updates["on_off"] = not device.state.on_off
            elif action == "brightness":
                if isinstance(value, (int, float)):
                    pct = max(0, min(100, int(value)))
                    updates["brightness"] = pct
                else:
                    raise ValueError("Brightness requires numeric value")
            elif action == "lock":
                if value in ("locked", "unlocked"):
                    updates["lock_state"] = value
                else:
                    raise ValueError("Lock state must be 'locked' or 'unlocked'")
            elif action == "temperature":
                if isinstance(value, (int, float)):
                    updates["target_temperature_c"] = float(value)
                else:
                    raise ValueError("Temperature requires numeric value")
            else:
                # Unknown action; skip
                executed.append(ExecutedAction(
                    type="device",
                    device_id=device_id,
                    action=action,
                    value=value,
                    status="skipped",
                    message=f"Unsupported action: {action}"
                ))
                continue

            # Apply state update
            from app.domain.models import DeviceState
            new_state = DeviceState(**updates)
            updated = domain_repository.update_state(context, device_id, new_state)
            # Emit audit event
            audit = AuditEvent(
                event_id=f"evt_{uuid4().hex}",
                occurred_at=datetime.utcnow(),
                tenant_id=context.tenant_id,
                household_id=context.household_id,
                actor_id=context.actor_id,
                actor_role=context.actor_role,
                action=f"device.{action}",
                resource_type="device",
                resource_id=device_id,
                outcome="allowed",
                reason=None,
                metadata={"state": updated.state.model_dump()},
            )
            domain_repository.write_audit_event(audit)
            executed.append(ExecutedAction(
                type="device",
                device_id=device_id,
                action=action,
                value=value,
                status="completed",
                message=f"{device.name}: {action} applied."
            ))
        except HTTPException as e:
            executed.append(ExecutedAction(
                type="device",
                device_id=device_id,
                action=action,
                value=value,
                status="failed",
                message=e.detail if hasattr(e, "detail") else "Device not found or unauthorized"
            ))
        except Exception as e:
            executed.append(ExecutedAction(
                type="device",
                device_id=device_id,
                action=action,
                value=value,
                status="failed",
                message=str(e)
            ))
    return executed


def _handle_remember_fact(text: str, context: RequestContext) -> AssistantTurnResponse:
    # Expect format: "remember <key> = <value>" or "remember that <key> is <value>"
    # Simple heuristic: extract after "remember" until period
    cleaned = re.sub(r"^remember\s+(that\s+)?", "", text, flags=re.I).strip()
    # If contains '=', split; else split on ' is ' or ' are '
    if "=" in cleaned:
        key, value = cleaned.split("=", 1)
    elif " is " in cleaned:
        parts = cleaned.split(" is ", 1)
        key, value = parts[0], parts[1]
    elif " are " in cleaned:
        parts = cleaned.split(" are ", 1)
        key, value = parts[0], parts[1]
    else:
        # Cannot parse
        return AssistantTurnResponse(
            input_text=text,
            reply_text="I couldn't understand what to remember. Try 'remember that the preferred temperature is 22 degrees'.",
            action=AssistantAction(type="remember_fact", status="none"),
        )
    key = key.strip().lower().replace(" ", "_")
    value = value.strip().strip(" .")
    memory = domain_repository.create_memory(context.actor_id, key, value)
    return AssistantTurnResponse(
        input_text=text,
        reply_text=f"Got it. I'll remember that {key.replace('_', ' ')} is {value}.",
        action=AssistantAction(type="remember_fact", status="completed"),
        executed_actions=[],
    )


def _llm_base_url() -> str:
    return os.getenv("LLM_GATEWAY_BASE_URL", "http://litellm:4000/v1").rstrip("/")


def _llm_timeout_seconds() -> float:
    raw = os.getenv("LLM_GATEWAY_TIMEOUT_SECONDS", "12")
    try:
        timeout = float(raw)
    except ValueError:
        return 12.0
    return timeout if timeout > 0 else 12.0


def _call_llm_router(text: str, context: RequestContext) -> dict | None:
    api_key = os.getenv("LLM_GATEWAY_API_KEY", "").strip()
    if not api_key:
        return None

    system_prompt = (
        "You are Nestra's internal intent router. "
        "Never mention model names, providers, or backend infrastructure. "
        "Classify the user turn into exactly one task and return strict JSON only. "
        "Allowed task values: status_summary, device_intent, clarification, unsupported, remember_fact. "
        "Allowed intent_type values for device_intent: "
        "shift_ev_charging_low_tariff_window, arm_night_security_sweep, preheat_home_arrival. "
        "Payload rules: "
        "EV requires window_start and window_end (HH:MM); "
        "night security requires arm_time (HH:MM) and optional zones list; "
        "preheat requires arrival_time (HH:MM) and target_temperature_c (number). "
        "For device_intent replies, include action tags in reply_text for each state change: "
        "[DEVICE:<device_id>:<action>[:<value>]]. Supported actions: on, off, toggle, brightness (0-100), lock (locked/unlocked), temperature (celsius). "
        "Example reply: 'Turning on kitchen lights. [DEVICE:dev-004:on] Also setting brightness to 80. [DEVICE:dev-004:brightness:80]'. "
        "Always include reply_text as one concise sentence.")

    payload = {
        "model": os.getenv("LLM_GATEWAY_MODEL_ALIAS", "nvidia-fast"),
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "text": text,
                        "actor_role": context.actor_role,
                        "tenant_id": context.tenant_id,
                        "household_id": context.household_id,
                    }
                ),
            },
        ],
    }

    req = urllib_request.Request(
        url=f"{_llm_base_url()}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib_request.urlopen(req, timeout=_llm_timeout_seconds()) as response:
            body = response.read().decode("utf-8")
    except (urllib_error.URLError, TimeoutError, ValueError):
        return None

    try:
        parsed = json.loads(body)
        message = parsed["choices"][0]["message"]
        content = message.get("content")
        if not content:
            content = message.get("reasoning_content")
        if not content:
            content = (message.get("provider_specific_fields") or {}).get("reasoning_content")
        if not content:
            content = (message.get("provider_specific_fields") or {}).get("reasoning")
        if not content:
            return None
        return json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None


def _assistant_status_summary(text: str, context: RequestContext) -> AssistantTurnResponse:
    devices = domain_repository.list_devices(context)
    audits = domain_repository.list_audit_events(context, limit=25)
    online = len([item for item in devices if item.online])
    blocked = len([item for item in audits if item.outcome != "allowed"])
    reply = (
        f"Home status: {online} of {len(devices)} devices online, "
        f"{blocked} blocked unsafe actions in recent logs."
    )
    return AssistantTurnResponse(
        input_text=text,
        reply_text=reply,
        action=AssistantAction(type="status_summary", status="completed"),
    )


def _process_device_intent(
    payload: DeviceIntentCreateRequest,
    context: RequestContext,
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


def _map_text_to_intent(text: str) -> DeviceIntentCreateRequest | None:
    normalized = text.lower().strip()
    if not normalized:
        return None

    if any(keyword in normalized for keyword in ["good night", "security", "arm"]):
        return DeviceIntentCreateRequest(
            intent_type="arm_night_security_sweep",
            payload={"arm_time": "22:30", "zones": ["entryway", "garage", "living-room"]},
            confirm=True,
        )

    if any(keyword in normalized for keyword in ["preheat", "i am home", "i'm home", "arriving"]):
        return DeviceIntentCreateRequest(
            intent_type="preheat_home_arrival",
            payload={"arrival_time": "18:00", "target_temperature_c": 21.5},
            confirm=True,
        )

    if any(keyword in normalized for keyword in ["ev", "charge", "tariff"]):
        return DeviceIntentCreateRequest(
            intent_type="shift_ev_charging_low_tariff_window",
            payload={"window_start": "23:00", "window_end": "05:00"},
            confirm=True,
        )

    return None


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


# Memory endpoints
@router.post("/memory", response_model=Memory)
def create_memory_endpoint(
    payload: MemoryCreateRequest,
    context: Annotated[RequestContext, Depends(get_demo_or_authenticated_context)],
) -> Memory:
    memory = domain_repository.create_memory(context.actor_id, payload.key, payload.value)
    return memory


@router.get("/memory", response_model=MemorySearchResponse)
def search_memory(
    context: Annotated[RequestContext, Depends(get_demo_or_authenticated_context)],
    query: Annotated[str, Query(min_length=1, max_length=100)] = ...,
) -> MemorySearchResponse:
    items = domain_repository.search_memories(context.actor_id, query)
    return MemorySearchResponse(items=items)


@router.delete("/memory/{memory_id}")
def delete_memory(
    memory_id: str,
    context: Annotated[RequestContext, Depends(get_demo_or_authenticated_context)],
) -> dict:
    success = domain_repository.delete_memory(context.actor_id, memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": True}


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
    return _process_device_intent(payload, context)


@router.post("/assistant/turn", response_model=AssistantTurnResponse)
def assistant_turn(
    payload: AssistantTurnRequest,
    context: Annotated[RequestContext, Depends(get_demo_or_authenticated_context)],
) -> AssistantTurnResponse:
    turn_started = time.perf_counter()
    text = payload.text.strip()
    normalized = text.lower()

    llm_started = time.perf_counter()
    llm_route = _call_llm_router(text, context)
    llm_duration_ms = int((time.perf_counter() - llm_started) * 1000)
    logger.info("assistant_turn stage=llm_router duration_ms=%s hit=%s", llm_duration_ms, bool(llm_route))

    executed_actions: list[ExecutedAction] = []
    clarifying_question: str | None = None

    if llm_route:
        task = str(llm_route.get("task", "")).strip().lower()
        llm_reply = _sanitize_assistant_reply(str(llm_route.get("reply_text", "")).strip())

        if task == "status_summary":
            return _assistant_status_summary(text, context)

        if task == "remember_fact":
            return _handle_remember_fact(text, context)

        if task == "device_intent":
            intent_type = str(llm_route.get("intent_type", "")).strip()
            intent_payload = llm_route.get("payload") if isinstance(llm_route.get("payload"), dict) else {}
            confirm = bool(llm_route.get("confirm", True))
            if intent_type in SUPPORTED_INTENTS:
                mapped = DeviceIntentCreateRequest(
                    intent_type=intent_type,
                    payload=intent_payload,
                    confirm=confirm,
                )
                try:
                    intent_started = time.perf_counter()
                    intent_result = _process_device_intent(mapped, context)
                    logger.info(
                        "assistant_turn stage=intent_apply duration_ms=%s intent=%s status=%s",
                        int((time.perf_counter() - intent_started) * 1000),
                        intent_result.intent.intent_type,
                        intent_result.status,
                    )
                    action_type = "device_intent"
                    if intent_result.status == "accepted":
                        reply = llm_reply or f"Done. {intent_result.message}"
                    elif intent_result.status == "pending_confirmation":
                        reply = llm_reply or f"I need your confirmation. {intent_result.message}"
                        clarifying_question = "Would you like to proceed?"
                    elif intent_result.status == "blocked":
                        reply = llm_reply or f"I blocked that request. {intent_result.message}"
                    else:
                        reply = llm_reply or intent_result.message

                    # Parse and execute action tags only when accepted
                    if intent_result.status == "accepted":
                        tags = _parse_action_tags(llm_reply)
                        if tags:
                            executed_actions = _execute_action_tags(context, tags, llm_reply)
                            # Optionally inform user; we purposely keep reply text unmodified for now

                    return AssistantTurnResponse(
                        input_text=text,
                        reply_text=reply,
                        action=AssistantAction(
                            type=action_type,
                            intent_type=intent_result.intent.intent_type,
                            status=intent_result.status,
                            audit_event_id=intent_result.audit_event_id,
                        ),
                        executed_actions=executed_actions,
                        clarifying_question=clarifying_question,
                        next_step=intent_result.next_step,
                        guardrail=intent_result.guardrail,
                    )
                except HTTPException:
                    pass  # fall through to general handling

        if task == "clarification":
            return AssistantTurnResponse(
                input_text=text,
                reply_text=llm_reply or "Please tell me what you want me to do at home.",
                action=AssistantAction(type="clarification", status="none"),
                clarifying_question=None,
            )

        if task == "unsupported":
            return AssistantTurnResponse(
                input_text=text,
                reply_text=llm_reply or "I can help with home status, EV charging, night security, or preheat.",
                action=AssistantAction(type="unsupported", status="none"),
            )

    # Fallback: keyword status summary
    if any(keyword in normalized for keyword in ["status", "summary", "home status", "what's happening"]):
        logger.info(
            "assistant_turn stage=done duration_ms=%s action=status_summary",
            int((time.perf_counter() - turn_started) * 1000),
        )
        return _assistant_status_summary(text, context)

    # Fallback: map text to known intent
    mapped = _map_text_to_intent(text)
    if not mapped:
        logger.info(
            "assistant_turn stage=done duration_ms=%s action=unsupported",
            int((time.perf_counter() - turn_started) * 1000),
        )
        return AssistantTurnResponse(
            input_text=text,
            reply_text=(
                "In this MVP I can optimize EV charging, arm night security sweep, "
                "preheat home for arrival, or provide home status summary."
            ),
            action=AssistantAction(type="unsupported", status="none"),
            next_step="Try: 'good night', 'preheat home', 'optimize EV charging', or 'home status'.",
        )

    # Process mapped intent
    intent_result = _process_device_intent(mapped, context)
    action_type = "device_intent"
    if intent_result.status == "accepted":
        reply = f"Done. {intent_result.message}"
    elif intent_result.status == "pending_confirmation":
        reply = f"I need your confirmation. {intent_result.message}"
        clarifying_question = "Do you confirm?"
    elif intent_result.status == "blocked":
        reply = f"I blocked that request. {intent_result.message}"
    else:
        reply = intent_result.message

    response = AssistantTurnResponse(
        input_text=text,
        reply_text=reply,
        action=AssistantAction(
            type=action_type,
            intent_type=intent_result.intent.intent_type,
            status=intent_result.status,
            audit_event_id=intent_result.audit_event_id,
        ),
        executed_actions=[],
        clarifying_question=clarifying_question,
        next_step=intent_result.next_step,
        guardrail=intent_result.guardrail,
    )
    logger.info(
        "assistant_turn stage=done duration_ms=%s action=device_intent status=%s",
        int((time.perf_counter() - turn_started) * 1000),
        intent_result.status,
    )
    return response


@router.post("/voice/transcribe", response_model=VoiceTranscriptionResponse)
async def voice_transcribe(
    context: Annotated[RequestContext, Depends(get_demo_or_authenticated_context)],
    file: UploadFile = File(...),
) -> VoiceTranscriptionResponse:
    _ = context
    started = time.perf_counter()
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Audio file is empty")

    result = transcribe_audio_with_telemetry(raw, file.filename or "voice.webm", file.content_type or "audio/webm")
    if not result:
        logger.warning(
            "voice_transcribe stage=done ok=false duration_ms=%s bytes=%s",
            int((time.perf_counter() - started) * 1000),
            len(raw),
        )
        raise HTTPException(
            status_code=503,
            detail="Speech transcription backend unavailable. Verify STT gateway settings.",
        )

    logger.info(
        "voice_transcribe stage=done ok=true backend=%s duration_ms=%s total_ms=%s bytes=%s",
        result.backend,
        result.duration_ms,
        int((time.perf_counter() - started) * 1000),
        len(raw),
    )
    return VoiceTranscriptionResponse(text=result.text)
