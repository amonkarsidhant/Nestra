# Nestra API Architecture (Bootstrap Foundation)

This document describes the current backend foundation shipped in `nestra/api`.

## Purpose of this slice

The previous API shape exposed endpoints without tenant boundaries, actor context, or audit signals.
This slice adds the minimum strong foundation for SaaS credibility:

- explicit tenant and household request context derived from bearer token claims
- typed domain models for tenant, household, actor, device, device intent, and audit event
- role-aware guardrail checks for state changes and device intent writes
- persistent storage for demo-phase domain entities
- persistent audit event history

## Current module boundaries

```text
app/
  api/
    routes.py            # HTTP contract and route handlers
  core/
    context.py           # request context model
    auth.py              # alpha token verification and claim mapping
    db.py                # SQLite schema, persistence, seed data
  domain/
    models.py            # typed domain contracts
    repository.py        # domain read/write adapter (SQLite-backed)
    audit.py             # audit event emission + persistence
  main.py                # app startup and router wiring
```

## Context boundary contract

Protected routes require `Authorization: Bearer <token>`.

The API extracts:
- `tenant_id`
- `household_id`
- `actor_id`
- `actor_role`

from signed token claims and rejects missing/invalid claims with `401`.

## Guardrail behavior in this slice

- Guests cannot change lock state.
- Guests cannot create EV charging shift intents.
- EV charging shift intent requires explicit confirmation (`confirm=true`) to be accepted.
- EV charging shift window must overlap low-tariff hours (`22:00-07:00`) or it is blocked.
- Guardrail blocks are recorded as audit events with outcome `blocked`.
- Successful state changes emit audit events with outcome `allowed`.

## Persistence choice

Nestra API uses SQLite for demo phase persistence.

Why this is enough now:
- Works with current Docker Compose deployment model.
- Gives real persistent data (not mock JSON) for end-to-end demo credibility.
- Supports relational domain boundaries with minimal operational overhead.

Why this is not the final state:
- SQLite is not sufficient for higher-scale multi-tenant SaaS workloads.
- Future phase should migrate to a managed relational backend with migration tooling.

## Known constraints

- Token verification is alpha-grade (shared-secret JWT) and not yet production OIDC.
- Write actions are context-safe, but auth-hardening is required for production.
- Data model is demo-focused (no billing/partner domains in this slice).

## Next backend upgrades (priority)

1. Introduce policy engine module beyond route-level checks.
2. Add migration tooling for SQLite schema evolution.
3. Move from alpha shared-secret JWT to standards-based OIDC/JWKS.
4. Plan and execute relational backend migration for managed SaaS scale.
