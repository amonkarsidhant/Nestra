# Nestra Demo Runbook

## Target buyer / viewer
- Home-tech decision makers evaluating premium smart-home control software
- Early design partners (residential builders, installers, and decor-tech teams)
- Technical sponsors who need confidence in guardrails, auditability, and operability

## 3-minute demo narrative
1. **Problem framing (30s):** smart homes are fragmented across Matter + vendor apps.
2. **Integration story (35s):** show Matter, Home Assistant, and energy signal integration cards.
3. **Household operations (40s):** show multi-device inventory (climate, lighting, lock, camera, sensor, blinds, EV).
4. **Action + guardrail (60s):** run EV optimization + one non-EV scenario and show policy outcomes.
5. **Audit evidence (15s):** show audit event with outcome and reason.

## Demo credentials
- Username: `owner@nestra.demo`
- Password: `nestra-alpha-owner`

## Demo household and devices
- Tenant: `default-tenant` (`Nestra Demo Tenant`)
- Household: `default-home` (`Amonkar Household`, `Europe/Amsterdam`)
- Actor: `owner-1` (`owner` role)
- Seeded devices:
  - `dev-003` — EV Charger (`plug`, `garage`)
  - `dev-001` — Living Room Thermostat (`thermostat`, `living-room`)
  - `dev-002` — Main Door Lock (`lock`, `entryway`)

## Exact steps and expected outcomes

### 1) Open app shell
- URL: `https://nestra.homelabdev.space`
- Expected: console loads directly in public demo mode using seeded demo actor context.

### 2) Verify demo context
- Expected:
  - session metadata shows seeded demo actor,
  - dashboard loads household context, devices, and audit history.

### 3) Run allowed action
- Trigger EV action with `window_start=23:00`, `window_end=05:00`, `confirm=true`.
- Expected:
  - response `status=accepted`,
  - `audit_event_id` returned,
  - audit history shows `device_intent.create` with `outcome=allowed`.

### 4) Run blocked action (guardrail)
- Trigger EV action with `window_start=12:00`, `window_end=13:00`, `confirm=true`.
- Expected:
  - response `status=blocked`,
  - clear message + next step,
  - audit history shows `outcome=blocked` and reason.

### 5) Run pending confirmation path
- Trigger EV action with `confirm=false`.
- Expected:
  - response `status=pending_confirmation`,
  - guidance to resubmit with confirmation,
  - audit history records blocked outcome for missing confirmation.

## Guardrail behavior
For `intent_type=shift_ev_charging_low_tariff_window`, Nestra applies:
1. Actor role must be `owner` or `resident` (guests blocked).
2. Explicit confirmation required (`confirm=true`).
3. Requested window must overlap low-tariff period (`22:00-07:00`).

## Audit trail behavior
- Every EV intent attempt produces an audit event.
- Allowed action -> `outcome=allowed`.
- Blocked or pending confirmation -> `outcome=blocked` with reason.
- UI surfaces recent audit history; API returns `audit_event_id` in action response.

## Known limitations
- Auth mode is alpha demo JWT, not full OIDC/OAuth production flow.
- Public demo mode bypasses sign-in wall for live demos.
- Token revocation and advanced session controls are not implemented.
- Persistence uses SQLite for demo speed and portability.
- Guardrails are route-level and policy-engine extraction is pending.

## What is real vs simulated

### Real in this demo
- Working sign-in flow (`/v1/login`) when demo auth is enabled
- Public demo mode for frictionless live walkthroughs (no login wall)
- Protected API behavior available when `DEMO_MODE_PUBLIC=false`
- Persistent tenant/household/actor/device/device_intent/audit_event data
- Guardrail evaluation and auditable outcomes

### Simulated / intentionally limited
- Production-grade identity federation and standards-compliant authorization flows
- Multi-tenant scale architecture beyond demo constraints
- Full orchestration engine, partner operations, and billing domains
