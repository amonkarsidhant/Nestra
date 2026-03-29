import json
from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException

from app.core.context import RequestContext
from app.core.db import get_db
from app.domain.models import (
    Actor,
    AuditEvent,
    Device,
    DeviceIntent,
    DeviceState,
    Household,
    Tenant,
)


class DomainRepository:
    def get_household_context(self, context: RequestContext) -> tuple[Tenant, Household, Actor]:
        with get_db() as conn:
            tenant_row = conn.execute(
                "SELECT id, name FROM tenants WHERE id = ?",
                (context.tenant_id,),
            ).fetchone()
            household_row = conn.execute(
                "SELECT id, tenant_id, name, timezone FROM households WHERE id = ? AND tenant_id = ?",
                (context.household_id, context.tenant_id),
            ).fetchone()
            actor_row = conn.execute(
                "SELECT id, tenant_id, household_id, name, role FROM actors WHERE id = ? AND tenant_id = ? AND household_id = ?",
                (context.actor_id, context.tenant_id, context.household_id),
            ).fetchone()

        if not tenant_row or not household_row or not actor_row:
            raise HTTPException(status_code=404, detail="Tenant, household, or actor not found")

        return (
            Tenant(**dict(tenant_row)),
            Household(**dict(household_row)),
            Actor(**dict(actor_row)),
        )

    def list_devices(self, context: RequestContext) -> list[Device]:
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT id, name, type, online, room, last_seen, state_json
                FROM devices
                WHERE tenant_id = ? AND household_id = ?
                ORDER BY name
                """,
                (context.tenant_id, context.household_id),
            ).fetchall()

        devices: list[Device] = []
        for row in rows:
            payload = dict(row)
            payload["online"] = bool(payload["online"])
            payload["state"] = DeviceState(**json.loads(payload.pop("state_json")))
            payload["last_seen"] = datetime.fromisoformat(payload["last_seen"])
            devices.append(Device(**payload))
        return devices

    def get_device(self, context: RequestContext, device_id: str) -> Device:
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT id, name, type, online, room, last_seen, state_json
                FROM devices
                WHERE id = ? AND tenant_id = ? AND household_id = ?
                """,
                (device_id, context.tenant_id, context.household_id),
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")

        payload = dict(row)
        payload["online"] = bool(payload["online"])
        payload["state"] = DeviceState(**json.loads(payload.pop("state_json")))
        payload["last_seen"] = datetime.fromisoformat(payload["last_seen"])
        return Device(**payload)

    def update_state(self, context: RequestContext, device_id: str, new_state: DeviceState) -> Device:
        current = self.get_device(context, device_id)
        updates = new_state.model_dump(exclude_none=True)
        state_data = current.state.model_dump()
        state_data.update(updates)
        last_seen = datetime.utcnow().isoformat()

        with get_db() as conn:
            conn.execute(
                """
                UPDATE devices
                SET state_json = ?, last_seen = ?
                WHERE id = ? AND tenant_id = ? AND household_id = ?
                """,
                (
                    json.dumps(state_data),
                    last_seen,
                    device_id,
                    context.tenant_id,
                    context.household_id,
                ),
            )
        return self.get_device(context, device_id)

    def create_intent(
        self,
        *,
        context: RequestContext,
        intent_type: str,
        payload: dict,
        status: str,
        requires_confirmation: bool,
        confirmed_at: str | None,
    ) -> DeviceIntent:
        intent_id = f"int_{uuid4().hex}"
        created_at = datetime.utcnow().isoformat()
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO device_intents (
                  id, tenant_id, household_id, actor_id, intent_type, payload_json,
                  status, requires_confirmation, created_at, confirmed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent_id,
                    context.tenant_id,
                    context.household_id,
                    context.actor_id,
                    intent_type,
                    json.dumps(payload),
                    status,
                    1 if requires_confirmation else 0,
                    created_at,
                    confirmed_at,
                ),
            )
        return DeviceIntent(
            id=intent_id,
            tenant_id=context.tenant_id,
            household_id=context.household_id,
            actor_id=context.actor_id,
            intent_type=intent_type,
            payload=payload,
            status=status,
            requires_confirmation=requires_confirmation,
            created_at=datetime.fromisoformat(created_at),
            confirmed_at=datetime.fromisoformat(confirmed_at) if confirmed_at else None,
        )

    def write_audit_event(self, event: AuditEvent) -> None:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO audit_events (
                  event_id, occurred_at, tenant_id, household_id, actor_id, actor_role,
                  action, resource_type, resource_id, outcome, reason, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.occurred_at.isoformat(),
                    event.tenant_id,
                    event.household_id,
                    event.actor_id,
                    event.actor_role,
                    event.action,
                    event.resource_type,
                    event.resource_id,
                    event.outcome,
                    event.reason,
                    json.dumps(event.metadata),
                ),
            )

    def list_audit_events(self, context: RequestContext, limit: int = 25) -> list[AuditEvent]:
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT event_id, occurred_at, tenant_id, household_id, actor_id, actor_role,
                       action, resource_type, resource_id, outcome, reason, metadata_json
                FROM audit_events
                WHERE tenant_id = ? AND household_id = ?
                ORDER BY occurred_at DESC
                LIMIT ?
                """,
                (context.tenant_id, context.household_id, limit),
            ).fetchall()

        events: list[AuditEvent] = []
        for row in rows:
            payload = dict(row)
            payload["occurred_at"] = datetime.fromisoformat(payload["occurred_at"])
            payload["metadata"] = json.loads(payload.pop("metadata_json"))
            events.append(AuditEvent(**payload))
        return events


domain_repository = DomainRepository()
