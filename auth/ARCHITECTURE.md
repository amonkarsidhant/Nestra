# Nestra Auth Architecture (Alpha Demo)

This service implements **alpha demo authentication** for Nestra's first end-to-end customer demo.

## What exists now

- Seeded owner credential in local SQLite
- `POST /v1/login` returns bearer token + actor context
- `GET /v1/me` validates token and returns actor context
- Tokens include tenant and household claims used by `nestra-api`

## What this is not

- Not full OAuth2/OIDC authorization code flow
- Not production session management/revocation
- Not production key management/JWKS rotation

## Why this is acceptable for alpha demo

- Protects app shell and API demo routes
- Removes anonymous access to household and audit surfaces
- Provides explicit actor/tenant/household context from signed claims

## Upgrade path to standards-based auth

1. Add standards-compliant OIDC endpoints and code+PKCE flow.
2. Move signing from shared secret to asymmetric keys with JWKS.
3. Add refresh token rotation and revocation lists.
4. Introduce tenant-bound client registrations and scopes.
5. Add hardened session/device management and audit policy.
