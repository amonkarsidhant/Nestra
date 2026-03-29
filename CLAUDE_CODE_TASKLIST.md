# Nestra Build Tasklist (Claude Code / OpenClaw)

Use this list to implement in small, reviewable slices.

## Slice 1: Platform Baseline
- Confirm clean project structure for web/api/auth boundaries
- Add health checks and startup validation paths
- Ensure local run + compose run parity

## Slice 2: Home Adapter Boundary
- Introduce adapter interface for external home-control providers
- Keep Home Assistant as first supported adapter
- Add clear fallback behavior when adapter unavailable

## Slice 3: Intent Pipeline
- Normalize intent contracts
- Enforce policy checks before execution
- Persist auditable action outcomes

## Slice 4: Trust-first UX
- Keep premium ambient UI
- Maintain explicit simulation labels where needed
- Add clearer failure and blocked-action affordances

## Slice 5: Voice Interaction Skeleton
- Add command intake endpoint (text first, voice-ready)
- Add response style profiles (brief, confirmation-focused)
- Stub TTS provider abstraction without overbuilding

## Slice 6: Quality + Review
- Run syntax/build checks
- Add focused tests for policy and audit paths
- Produce release note with known limitations

## Required Guardrails
- No fabricated metrics
- No hidden destructive actions
- No un-audited critical operations
- No claims of capabilities not implemented
