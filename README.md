# Nestra Home OS SaaS Bootstrap

This directory contains the first deployable Nestra SaaS stack.

## Services
- `nestra-web` -> `https://nestra.homelabdev.space`
- `nestra-api` -> `https://api.nestra.homelabdev.space`
- `nestra-auth` -> `https://auth.nestra.homelabdev.space`

## Quick start
1. Copy `.env.example` to `.env` and set `AUTH_JWT_SECRET`.
2. Ensure DNS A records for all three hosts point to Traefik VM IP.
3. Start stack:

```bash
docker compose -f nestra/docker-compose.yml --env-file nestra/.env up -d --build
```

## Verification
```bash
curl -sS https://api.nestra.homelabdev.space/health
curl -sS https://auth.nestra.homelabdev.space/health
```

## Alpha authentication (demo)

Nestra now uses an **alpha demo auth flow** for the first end-to-end customer demo.

1. Sign in via `POST /v1/login` on `nestra-auth`
2. Receive bearer token and actor context
3. Use `Authorization: Bearer <token>` for protected API routes

### Demo credentials

- Username: `owner@nestra.demo`
- Password: `nestra-alpha-owner`

You can override these in `nestra/.env`:
- `DEMO_OWNER_USERNAME`
- `DEMO_OWNER_PASSWORD`

### Login example

```bash
TOKEN=$(curl -sS https://auth.nestra.homelabdev.space/v1/login \
  -H "Content-Type: application/json" \
  -d '{"username":"owner@nestra.demo","password":"nestra-alpha-owner"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

curl -sS https://api.nestra.homelabdev.space/v1/household/context \
  -H "Authorization: Bearer ${TOKEN}"
```

### What this is (and is not)

- This is **honest alpha auth** for demo credibility.
- It protects the app shell and protected API routes used by the demo.
- It is **not** full production OIDC/OAuth implementation.
- `/.well-known/openid-configuration` remains partial and clearly marked for alpha.

## Public demo mode (current)

For easier live demos, API routes can run without login wall in **public demo mode**.

- Enabled by default: `DEMO_MODE_PUBLIC=true`
- Demo context used when no bearer token is present:
  - `DEMO_TENANT_ID=default-tenant`
  - `DEMO_HOUSEHOLD_ID=default-home`
  - `DEMO_ACTOR_ID=owner-1`
  - `DEMO_ACTOR_ROLE=owner`

Set `DEMO_MODE_PUBLIC=false` to require bearer token auth on protected routes.

## Current limits

- Demo storage is SQLite (`/data/nestra_demo.db`) mounted as a Docker volume
- Auth is alpha-demo JWT with one seeded owner login
- Audit events are persisted in SQLite and can be queried via `/v1/audit-events`

## Demo-phase storage decision

Nestra uses SQLite for the first end-to-end demo because it is the simplest strong foundation that is:
- persistent across container restarts,
- easy to run in homelab Docker Compose,
- explicit enough to model tenant, household, actor, device, device intent, and audit event domains.

This is enough for alpha demo credibility. It is not the long-term multi-tenant production data layer.

## Auth upgrade path (post-demo)

Planned migration from alpha auth to standards-based token auth:

1. Replace demo user table with proper identity provider model.
2. Move to standards-compliant OIDC authorization code + refresh token flow.
3. Publish stable JWKS and key rotation policy for token verification.
4. Add session revocation + device/session management.
5. Move from shared-secret HS256 to asymmetric key signing.

## Seeded demo context

- Tenant: `default-tenant` (`Nestra Demo Tenant`)
- Household: `default-home` (`Amonkar Household`)
- Actors:
  - `owner-1` (owner)
  - `resident-1` (resident)
  - `guest-1` (guest)

## Demo API contracts

- `GET /v1/household/context` -> tenant + household + actor context
- `GET /v1/devices` -> typed device inventory
- `GET /v1/audit-events` -> persistent audit history
- `POST /v1/device-intents` -> create the EV charging intent action with premium feedback fields

## Guardrail rule for EV charging demo action

For `intent_type=shift_ev_charging_low_tariff_window`, Nestra evaluates this guardrail before acceptance:

1. Actor must be `owner` or `resident` (guests are blocked).
2. Explicit confirmation is required (`confirm=true`).
3. Requested time window must overlap the low-tariff period (`22:00-07:00`).

Behavior:
- Allowed -> writes `device_intents` + `audit_events` (outcome `allowed`).
- Blocked/pending confirmation -> still writes `audit_events` (outcome `blocked`).

Additional demo intents:
- `arm_night_security_sweep` (owner-only + confirmation)
- `preheat_home_arrival` (owner/resident + confirmation + safe temp range)

## Agent workflow for future slices

Nestra now includes a superpowers-inspired delivery loop for consistent execution:

- Workflow guide: `nestra/WORKFLOW_SUPERPOWERS.md`
- Plan command: `.opencode/commands/nestra-plan.md`
- Build command: `.opencode/commands/nestra-feature.md`
- Build with explicit execution checklist: `.opencode/commands/nestra-execute.md`
