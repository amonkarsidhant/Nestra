# Nestra MVP Spec

## Scope
Build an AI-first interaction layer over existing home control systems, starting with Home Assistant compatibility and policy-aware intent execution.

## MVP Capabilities
1. **Household Context**
   - actor identity (demo mode or authenticated)
   - household and device context retrieval

2. **Intent Execution**
   - user submits intent (voice or touch path)
   - policy checks gate execution
   - explicit accepted / blocked / pending-confirmation response

3. **Audit Feed**
   - each critical action generates an audit event
   - feed exposes action, actor, time, outcome, reason

4. **Premium Demo UX**
   - calm ambient layout
   - scenario controls
   - trust panel (honest value positioning)

## Required User Flows
1. View household context and connected devices
2. Run EV tariff optimization with guardrail confirmation
3. Run security or comfort scenario and review audit output
4. Run skeptical buyer check and see transparent product strengths/gaps

## Acceptance Criteria
- Action response always includes status and human-readable reason
- Guardrail-blocked actions are visible and auditable
- API failure states are explicit in UI (no silent failure)
- No fabricated operational metrics in default UI
- Integration labels must reflect reality or explicit simulation status

## Out of Scope (MVP)
- Advanced automation graph builder
- Full partner admin console
- Native mobile apps (web-first demo still acceptable in MVP)
- Broad multi-platform direct connectors beyond initial adapter approach
