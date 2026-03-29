# Nestra Master Project (Opencode Execution)

## Goal
Build a premium, Jarvis-style, voice-first assistant experience on top of Home Assistant without rebuilding home automation infrastructure.

## Repository inspirations and decision

### 1) `SEPIA-Framework/sepia-html-client-app`
- **Use for:** interaction model, voice+text UX patterns, always-on assistant behavior.
- **Decision:** primary UX inspiration.

### 2) `rhasspy/rhasspy`
- **Use for:** reliable STT/NLU pipeline and Home Assistant integration via MQTT/HTTP/WebSocket.
- **Decision:** primary voice pipeline candidate for v1.

### 3) `OpenVoiceOS/ovos-core`
- **Use for:** persona and extensible assistant architecture ideas.
- **Decision:** optional phase-2 reference if we need richer persona orchestration.

### 4) `guansss/pixi-live2d-display`
- **Use for:** expressive virtual human agent rendering in web UI.
- **Decision:** use for visual agent phase once model licensing is finalized.

### 5) `leon-ai/leon`
- **Use for:** skills/actions/tools/memory architecture patterns.
- **Decision:** architecture reference only, not direct adoption in v1 due active preview churn.

### 6) `MycroftAI/mycroft-core`
- **Use for:** historical reference only.
- **Decision:** do not adopt (project not actively maintained).

## What fits Nestra codebase now

Current code is lightweight (`web` + FastAPI `api/auth`).

Best fit in current architecture:
1. Add a voice-orchestration service boundary (can start as FastAPI module).
2. Integrate Rhasspy (or compatible STT/NLU service) over HTTP/MQTT.
3. Keep Home Assistant as execution backend (adapter model).
4. Upgrade frontend from static shell to assistant stage with real speech loop + emotional state machine.

## Non-goals for this master project
- No full replacement of Home Assistant integrations.
- No broad multi-provider abstraction in v1.
- No 3D avatar stack in v1.

## Opencode execution slices

### Slice 1: Voice backend contract
- Define `/v1/assistant/turn` contract (text in, action+reply out)
- Add deterministic policy checks + audit event links

### Slice 2: Rhasspy bridge
- Add adapter for STT/NLU events
- Map intents to existing Nestra intents

### Slice 3: Assistant UX
- Keep single-stage interface (no dashboard clutter)
- Add conversational memory panel + transparent fail states

### Slice 4: Live avatar layer
- Integrate Live2D rendering (or fallback expressive 2D model)
- Map emotional states: idle/listening/thinking/speaking/error

### Slice 5: Buyer proof
- Show measurable trust evidence: blocked actions, execution latency, pass-rate trends, last sync

## Success criteria
- User can speak natural command and receive a voice response.
- Command execution is policy-gated and auditable.
- UI feels like one assistant presence, not a dashboard collection.
- Product can be demoed as a clear complement to Home Assistant.
