# Elix-PMS

Visitor Management & Access Control System for Singapore condominiums: multi-site, LPR (Dahua),
gate relays (Sonoff eWeLink / Shelly), LiveKit video intercom and a staff dashboard.
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
| http://127.0.0.1:8001/v1/admin/ | Django admin (sites, gates, relays, cameras, kiosks, credentials) |
| http://127.0.0.1:8001/v1/docs/ | Swagger API docs |
| http://127.0.0.1:8001/v1/auth/token/ | JWT login |
| `POST /v1/lpr-webhook/` | Dahua LPR events (Basic Auth per camera) |
| `POST /v1/gates/{id}/open/` | Manual gate opening (security / condo admin) |
| `ws://…/ws/events/?token=<JWT>` | Live events (access logs, intercom calls) for the user's condos and units |
| `ws://…/ws/events/?kiosk_token=<token>` | Live state of the kiosk's own calls |

The dev API listens on `127.0.0.1:8001` (`DEV_PORT`); port 8000 belongs to production. Set `DEV_BIND`
in `.env` to the server's Tailscale IP to reach the dev API remotely.

## Dashboard (staff)

`frontend/` is a Next.js + TypeScript + Tailwind app for condo admins and security guards, exported
as static files and served by the **gateway** (nginx), which also proxies `/v1`, `/ws` and `/static`
to Django. Everything runs on one origin, so there is no CORS and the browser keeps one JWT session.

| Page | Who | What |
|---|---|---|
| Overview | all staff | Today's counters, device issues, latest access (live), one-click gate opening |
| Access log | all staff | Filter by gate, method, result, plate, date; camera snapshots; live updates |
| Intercom | all staff | Ringing kiosk calls (ringtone + banner on every page), answer with video, swipe to open, reject; history |
| Gates | all staff | Manual opening with reason (logged under the user) |
| Invitations | all staff (create/cancel: admin) | Active/expired/cancelled invitations, QR code and share link |
| Vehicles | all staff (edit: admin) | Resident vehicles used by LPR auto-open |
| Residents | all staff | Who lives in which unit and who receives intercom calls |
| Devices | admin | Relay errors, camera last event, kiosk online status |

Staff sign in with their Django username and password; residents are refused (they use the app).
Users with several condominiums get a site switcher. Times are shown and entered in SGT.

Development with hot reload (proxies the API to the dev web service):

```bash
docker compose --profile frontend up -d frontend   # http://127.0.0.1:3000
```

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

## Video intercom (LiveKit)

Primary visitor flow: the visitor picks a unit on the kiosk, the residents' phones ring, a resident
answers (video) and **swipes to unlock**, which opens the kiosk's gate.

| Who | Call | Purpose |
|---|---|---|
| Kiosk | `GET /v1/kiosk/me/` | Config + heartbeat |
| Kiosk | `GET /v1/kiosk/directory/?q=05-12` | Units that take calls (no resident names) |
| Kiosk | `POST /v1/kiosk/calls/` (`unit`, `visitor_name`, `snapshot` image) | Ring; returns LiveKit `url/room/token` |
| Kiosk | `GET /v1/kiosk/calls/{id}/`, `POST …/hangup/` | Poll state / cancel |
| Resident | `POST /v1/intercom-calls/{id}/answer/` | First answer wins; returns LiveKit connection |
| Resident | `POST /v1/intercom-calls/{id}/unlock/` | Swipe to unlock (also allowed straight from the preview) |
| Resident | `POST …/reject/`, `POST …/hangup/`, `GET …/snapshot/` | Decline / end / visitor photo |
| Resident | `POST /v1/push-devices/` (`platform`, `token`) | Register the phone's FCM token |

Kiosks authenticate with `Authorization: Kiosk <token>`; the token is shown once when the kiosk is
created in Admin (action *Regenerate device token* issues a new one). Calls ring for the condo's
*intercom ring timeout* (default 45 s), then become **missed**; a kiosk starting a new call cancels its
previous one. Rejected, missed and approved calls are all in the access log. Security staff of the
condo can also answer and unlock.

Enter the LiveKit URL, API key and secret in **Admin → System settings** and press
*Save & test LiveKit* (or run `docker compose exec web python manage.py livekit_check`). Without them the
kiosk gets HTTP 503 and nobody is rung. For push, paste the Firebase service-account JSON on the same
page and press *Save & test Firebase*; without it only open apps (WebSocket) ring.

## System settings

**Admin → System settings** is a single page for server-wide integrations: LiveKit (URL, key, secret,
token lifetime, unlock window), the Firebase service-account JSON, the relay HTTP timeout and the LPR
debounce. Secrets are stored encrypted and never shown again. Changes apply immediately to the web,
worker and beat processes (no restart). Any blank field falls back to the matching `.env` variable
(`LIVEKIT_*`, `INTERCOM_UNLOCK_WINDOW_SECONDS`, `FCM_SERVICE_ACCOUNT_FILE`, `RELAY_HTTP_TIMEOUT`,
`LPR_DEBOUNCE_SECONDS`); the page shows which source is live. Infrastructure values (database, Redis,
`DJANGO_SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, hosts) stay in `.env` because the server needs them to start.
Per-condo settings (LPR on/off, ring timeout, invitation limits) are on each Condominium, and relay /
camera credentials on their own admin pages.

## Production

Production runs on the same server as a separate stack and is published through **Cloudflare Tunnel**,
so no inbound ports are opened (the Lighthouse firewall can stay closed except SSH):

```bash
cp .env.example .env.prod     # DJANGO_DEBUG=false, real hostname, new DJANGO_SECRET_KEY
ENV_FILE=.env.prod docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
ENV_FILE=.env.prod docker compose -f docker-compose.yml -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

- The gateway (dashboard + proxy to daphne) listens on `127.0.0.1:8000` only; `web` is not published.
- In Cloudflare Zero Trust → Networks → Tunnels → *Public hostname*, set the service to
  `HTTP` / `localhost:8000`. HTTPS and WebSockets are handled by Cloudflare.
- In `.env.prod`, set `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS=https://<host>`,
  `PUBLIC_BASE_URL=https://<host>` and `CORS_ALLOWED_ORIGINS`.
- Keep `FIELD_ENCRYPTION_KEY` safe: losing it makes every stored secret unreadable.
- Recommended: protect `/v1/admin/` with a Cloudflare Access policy. If Bot Fight Mode is on, add a
  skip rule for `/v1/lpr-webhook/` so cameras are not challenged.
- Without Cloudflare, put any TLS reverse proxy (Caddy, nginx + certbot) in front of
  `127.0.0.1:8000` and have it set `X-Forwarded-Proto: https`.

Dev and prod use separate Compose project names (`elix-vms-dev`, `elix-vms-prod`), so their
databases and volumes never mix.

## Access model

| Role | Sees | Writes |
|---|---|---|
| Superuser | everything | everything |
| Condo admin | own condominium | own condominium, incl. device credentials |
| Security | own condominium, except relays/cameras/kiosks/credentials | visitors, manual gate opening, intercom answers |
| Resident | own units, condo gates/blocks | own vehicles and invitations |

Third-party secrets (eWeLink, Shelly, camera, relay LAN passwords) are encrypted at rest with
`FIELD_ENCRYPTION_KEY` and are write-only in the API and admin. Back the key up: without it the
stored credentials cannot be read.
