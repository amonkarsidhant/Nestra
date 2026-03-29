# Nestra

*Your home, understood.*

Nestra is a voice‑first smart home assistant that brings genuinely natural, conversational control to your home. No awkward phrases. No cloud latency. Just talk, and Nestra responds with a presence that feels alive.

---

## Why Nestra?

- **Truly conversational** – Speak naturally. No need to memorize commands.
- **On-premises by default** – Your voice stays in your home. Optional cloud LLM for intelligence, not storage.
- **One beautiful interface** – Full‑screen, immersive experience with a living, breathing avatar.
- **Privacy guardrails** – Explicit consent for actions. Full audit trail. No background snooping.
- **Enterprise-grade reliability** – Built with typed APIs, audit events, and policy‑gated device control.

---

## Experience

### Voice that feels human
Nestra listens continuously. Tap anywhere to start speaking. It understands your intent, confirms when needed, and executes with subtle animations that make the interaction feel real.

### Memory that learns
Tell Nestra what you prefer: *"Remember that I like the temperature at 22 degrees."* From then on, it factors your preference into responses and automations.

### Action tags for precision
Behind the scenes, Nestra uses structured **action tags** to execute multiple device changes in a single utterance, with full audit logging. Example:

> "Turn on kitchen lights and set brightness to 80."

Nestra parses and applies each change, then shows you exactly what happened.

---

## Tech highlights (for the curious)

- **Backend**: FastAPI + SQLite + Pydantic. Clean domain model with tenant/household/actor boundaries.
- **Frontend**: Pure HTML/CSS/JS with a procedural canvas avatar and audio‑reactive particle orb.
- **Voice pipeline**: Web Speech API for browser STT; TTS via system voices; LLM routing via OpenAI‑compatible gateway.
- **Security**: JWT auth, CORS lock‑down, CSP headers, audit events for every device action.
- **Observability**: Structured logs, health endpoints, Prometheus‑ready metrics.
- **Deployment**: Docker Compose + Traefik reverse proxy. One command to run anywhere.

---

## Quick start (homelab)

```bash
# Clone and enter
git clone https://github.com/amonkarsidhant/Nestra.git
cd Nestra

# Copy env and set a strong JWT secret
cp .env.example .env
# Edit .env: set AUTH_JWT_SECRET to a random 32‑byte value

# Ensure DNS points nestra.homelabdev.space and api.nestra.homelabdev.space to your Traefik host

# Bring up the stack
docker compose -f nestra/docker-compose.yml --env-file nestra/.env up -d --build
```

Open https://nestra.homelabdev.space in Chrome. Tap to talk.

---

## Demo credentials (alpha)

For the public demo instance:

- **Username**: `owner@nestra.demo`
- **Password**: `nestra-alpha-owner`

Or use the default demo mode (no login required) with the seeded household:
- Tenant: `default-tenant`
- Household: `default-home`
- Actor: `owner-1`

---

## What it can do today

- **Status summary** – *"What’s happening at home?"*
- **Device control** – *"Turn on kitchen lights"*, *"Set living room temperature to 22"*
- **EV charging plan** – *"Optimize EV charging for low tariff"* (with guardrails)
- **Night security** – *"Good night, arm security"* (owner‑only)
- **Preheat home** – *"I’m home, set temperature to 21"*
- **Memory** – *"Remember that my preferred temperature is 22"* (stored per actor)

---

## Roadmap

- **Confirmation flows** – Two‑step confirmation for sensitive actions
- **Compact mode** – Float a mini‑avatar while you work
- **Mobile app** – React Native wrapper for iOS/Android
- **Partner APIs** – White‑label integrations for device manufacturers
- **Cloud SaaS** – Managed offering with multi‑tenant isolation

---

## Design pillars

| Pillar | What it means |
|--------|----------------|
| **Natural** | No rigid command grammar. Free‑form language. |
| **Trustworthy** | Every action logged. Clear consent. Data stays home unless you choose otherwise. |
| **Calm** | No clutter. No pop‑ups. Just a quiet, always‑ready presence. |
| **Observable** | Built‑in audit trails and health metrics. |

---

## Screenshots

| Immersive voice interface | Device inventory | Particle orb |
|--------------------------|------------------|--------------|
| ![Avatar stage](/nestra/web/assets/avatar-front.png) | ![Devices panel](#) | ![Orb effect](#) |

---

## License

Free for personal, non‑commercial use. Commercial deployment requires a license. See [LICENSE](LICENSE) for details.

---

## Built with

- FastAPI
- SQLite
- Tailwind‑inspired custom CSS
- Canvas 2D
- Web Speech API
- Docker

---

**Nestra** – Your home, understood.
