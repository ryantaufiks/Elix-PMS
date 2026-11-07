# Elix-PMS

Visitor Management & Access Control System for Singapore condominiums: multi-site, LPR (Dahua),
gate relays (Sonoff eWeLink / Shelly) and LiveKit video intercom.
Full architecture notes: [readme-smartpms(helix).md](readme-smartpms(helix).md).

## Quick start (development)

```bash
cp .env.example .env          # fill in DJANGO_SECRET_KEY, FIELD_ENCRYPTION_KEY, DB password
docker compose up -d --build  # db, redis, web (runserver), worker, beat
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py test core
```

| URL | |
|---|---|
| http://127.0.0.1:8000/v1/admin/ | Django admin (sites, gates, relays, cameras, kiosks, credentials) |
| http://127.0.0.1:8000/v1/docs/ | Swagger API docs |
| http://127.0.0.1:8000/v1/auth/token/ | JWT login |
| `POST /v1/lpr-webhook/` | Dahua LPR events (Basic Auth per camera) |
| `POST /v1/gates/{id}/open/` | Manual gate opening (security / condo admin) |
| `ws://…/ws/events/?token=<JWT>` | Live access events for the user's condos and units |

Set `DEV_BIND` in `.env` to the server's Tailscale IP to reach the dev API remotely.

## Gate relays

Configure under **Admin → Integration accounts** (cloud credentials, per site) and **Relay controllers**
(per gate). Select relays and run **"Test: pulse relay now"** or **"Check relay status"** to verify.

| Provider | Local LAN | Cloud |
|---|---|---|
| Shelly Gen2/Gen3 | JSON-RPC `Switch.Set` + `toggle_after`, Digest SHA-256 (user `admin`); Gen1 `/relay/N?turn=on&timer=` fallback | Cloud Control API v2 (`/v2/devices/api/set/switch`), server URI + auth key |
| Sonoff (eWeLink) | DIY mode `:8081/zeroconf/switch` | CoolKit API v2, auto token refresh (not yet verified on a real device) |

Shelly pulses for `pulse_seconds` via `toggle_after`; Sonoff relies on the device's Inching / Auto-Off.
**Local LAN only works if this server can reach the site network** (e.g. a Tailscale subnet router at
the site plus `tailscale set --accept-routes` here). Otherwise use cloud, or "local, fall back to cloud".

## LPR cameras

1. Admin → Condominium: **LPR enabled** is off by default. While off, camera posts are only stored
   (Admin → LPR camera → *Last payload*) so you can inspect the real payload first.
2. Admin → LPR camera: set Dahua device ID, webhook username/password, and optionally **Plate field**
   (dotted path such as `Picture.Plate.PlateNumber`; blank = auto-detect).
3. Camera Web GUI → HTTP Post: `https://<domain>/v1/lpr-webhook/` with those credentials.

When enabled: a registered resident plate opens the gate; a plate on a valid invitation opens it and
counts an entry (unless the invitation requires face verification); anything else is logged as denied.
Repeat reads of the same plate within `LPR_DEBOUNCE_SECONDS` (20 s) are ignored.

## Production

```bash
cp .env.example .env.prod     # DJANGO_DEBUG=false, real domain, new secrets
ENV_FILE=.env.prod docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Dev and prod use separate Compose project names (`elix-vms-dev`, `elix-vms-prod`), so their
databases and volumes never mix.

## Access model

| Role | Sees | Writes |
|---|---|---|
| Superuser | everything | everything |
| Condo admin | own condominium | own condominium, incl. device credentials |
| Security | own condominium, except relays/cameras/kiosks/credentials | visitors |
| Resident | own units, condo gates/blocks | own vehicles and invitations |

Third-party secrets (eWeLink, Shelly, camera, relay LAN passwords) are encrypted at rest with
`FIELD_ENCRYPTION_KEY` and are write-only in the API and admin. Back the key up: without it the
stored credentials cannot be read.
