import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.core.context import RequestContext
from app.domain.models import AuditEvent
from app.domain.repository import domain_repository

logger = logging.getLogger("uvicorn.error")


def emit_audit_event(
    *,
    context: RequestContext,
    action: str,
    resource_type: str,
    resource_id: str,
    outcome: str,
    reason: str | None = None,
    metadata: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        event_id=f"evt_{uuid4().hex}",
        occurred_at=datetime.now(timezone.utc),
        tenant_id=context.tenant_id,
        household_id=context.household_id,
        actor_id=context.actor_id,
        actor_role=context.actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        reason=reason,
        metadata=metadata or {},
    )
    logger.info("audit_event=%s", event.model_dump_json())
    domain_repository.write_audit_event(event)
    return event
