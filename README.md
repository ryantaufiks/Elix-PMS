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
| http://127.0.0.1:8001/v1/admin/ | Django admin (advanced fallback; daily setup is in the dashboard) |
| http://127.0.0.1:8001/v1/docs/ | Swagger API docs |
| http://127.0.0.1:8001/v1/auth/token/ | JWT login |
| `POST /v1/lpr-webhook/` | Dahua LPR events (Basic Auth per camera) |
| `POST /v1/gates/{id}/open/` | Manual gate opening (security / condo admin) |
| `ws://…/ws/events/?token=<JWT>` | Live events (access logs, intercom calls) for the user's condos and units |
| `ws://…/ws/events/?kiosk_token=<token>` | Live state of the kiosk's own calls |

The dev API listens on `127.0.0.1:8001` (`DEV_PORT`); port 8000 belongs to production. Set `DEV_BIND`
in `.env` to the server's Tailscale IP to reach the dev API remotely.

## Dashboard (staff)

`frontend/` is a Next.js + TypeScript + Tailwind app, exported as static files and served by the
**gateway** (nginx), which also proxies `/v1`, `/ws` and `/static` to Django. Everything runs on one
origin, so there is no CORS and the browser keeps one JWT session.

Look: a "command center" theme built around the Elix logo - navy sidebar with the chrome logo,
electric-blue accents, light content area - plus a **dark mode** toggle in the top bar (remembered per
browser, defaults to the OS setting). Colours are semantic tokens in `frontend/src/app/globals.css`;
chart colours were checked with a colour-blind-safety validator for both themes. Brand files live in
`frontend/public/brand/` and `frontend/src/app/icon.png` / `apple-icon.png` (cropped from the source
artwork `elix-logo.zip`, which is kept out of git). The dashboard home shows today's KPIs, an hourly
traffic chart (with table view), live activity, gate health and entry methods.

**All day-to-day setup is done here; Django admin is only an advanced fallback for the platform admin.**
On first sign-in with no condominium, the platform admin is guided through creating one.

| Section | Page | Who | What |
|---|---|---|---|
| Operations | Dashboard | all staff | Today's KPIs, hourly traffic chart, live activity, gate health with one-click opening, entry methods |
| | Access log | all staff | Filter by gate, method, result, plate, date; camera snapshots; live updates |
| | Intercom | all staff | Ringing kiosk calls (ringtone + banner on every page), answer with video, swipe to open, reject; history |
| | Walk-ins | all staff | Walk-in registrations with pass number and photo, *On site* / *Today* tabs, manual check-out; a toast on every page when one registers |
| | Open gates | all staff | Manual opening with reason (logged under the user) |
| | Invitations | all staff (create/cancel: admin) | QR code and share link, status filters |
| Community | Residents | all staff (manage: admin) | Add residents with their app login, unit role, intercom on/off, password reset, move out |
| | Vehicles | all staff (edit: admin) | Resident plates used by LPR auto-open |
| | Staff | admin | Create guard / condo-admin accounts, change role, reset password, remove |
| Site setup | Site settings | admin | Name, address, LPR on/off, ring timeout, invitation limit, face check, PDPA retention |
| | Blocks & units | admin | Blocks, units, and *Generate units* (e.g. floors 2–15 × units 01–08) |
| | Gates & devices | admin | Gates; relays (cloud / LAN / LAN→cloud, *Test* and *Status*); LPR cameras (webhook URL, last payload); kiosks (device token shown once); Shelly / eWeLink cloud accounts |
| Platform | Condominiums | platform admin | Add, edit, activate sites |
| | System settings | platform admin | LiveKit, Firebase (with connection tests), relay / LPR tuning |

Secrets (relay passwords, cloud keys, camera passwords, LiveKit secret, Firebase key) are write-only:
the dashboard shows "saved" and a blank field keeps the stored value. Condo admins can manage only
people who belong solely to their own condominium. Times are shown and entered in SGT.

Development with hot reload (proxies the API to the dev web service):

```bash
docker compose --profile frontend up -d frontend   # http://127.0.0.1:3000
```

## Gate relays

Configure in the dashboard under **Site setup → Gates & devices**: *Cloud accounts* (credentials, per
site) and *Relays* (per gate). Use **Test** (pulses the relay) or **Status** to verify.

| Provider | Local LAN | Cloud |
|---|---|---|
| Shelly Gen2/Gen3 | JSON-RPC `Switch.Set` + `toggle_after`, Digest SHA-256 (user `admin`); Gen1 `/relay/N?turn=on&timer=` fallback | Cloud Control API v2 (`/v2/devices/api/set/switch`), server URI + auth key |
| Sonoff (eWeLink) | DIY mode `:8081/zeroconf/switch` | CoolKit API v2, auto token refresh (not yet verified on a real device) |

Shelly pulses for `pulse_seconds` via `toggle_after`; Sonoff relies on the device's Inching / Auto-Off.
**Local LAN only works if this server can reach the site network** (e.g. a Tailscale subnet router at
the site plus `tailscale set --accept-routes` here). Otherwise use cloud, or "local, fall back to cloud".

## LPR cameras

1. Site settings: **Licence-plate recognition enabled** is off by default. While off, camera posts are
   only stored (Gates & devices → LPR cameras → *Setup info* shows the last payload) so you can inspect
   the real payload first.
2. Gates & devices → LPR cameras: set Dahua device ID, webhook username/password, and optionally **Plate field**
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

Enter the LiveKit URL, API key and secret in the dashboard under **Platform → System settings** and
press *Save & test connection* (or run `docker compose exec web python manage.py livekit_check`). Without them the
kiosk gets HTTP 503 and nobody is rung. For push, paste the Firebase service-account JSON on the same
page and press *Save & test Firebase*; without it only open apps (WebSocket) ring.

## Web kiosk & visitor pass

- **Kiosk** (`/kiosk/` on the dashboard site, full-screen on any tablet browser): add a kiosk under
  Gates & devices → Kiosks, open `/kiosk/` on the tablet and enter the one-time device token. Visitors
  either **call a resident** (unit directory, then their details and photo, LiveKit video both ways; the
  gate opens when the resident or guard swipes) or **scan their invitation QR** with the tablet camera.
- **Visitor details before a call** (per site, Site settings → Visitor kiosk; both on by default):
  *Ask visitors for their details* (name, purpose such as parcel/food delivery with the company, and
  optionally mobile and last 4 of NRIC/FIN) and *Take the visitor's photo* (explicit photo with preview
  and retake). The resident sees all of it on the incoming call and in the push notification. Returning
  visitors type their mobile or NRIC last 4 and only see a masked name ("B\*\*\* S\*\*\*") before
  continuing, so the kiosk cannot be used to look people up. Blocked visitors (Community → Visitors) are
  sent to the guardhouse and the attempt is logged. Invitations that
  require a face check make the kiosk take a photo, stored with the access-log entry for review (it is
  not matched automatically). Tap the empty area under the buttons five times to sign the kiosk out.
- **Walk in** (per site, Site settings → *Offer walk-in registration*, on by default): for visitors who
  are not calling anyone. They pick the unit (any active unit), enter the same details as for a call,
  take a photo (*Take the walk-in visitor's photo*, can be turned off) and accept the notice. The kiosk
  prints a **58 mm slip** with the pass number, details, validity and a check-out QR. Pass numbers
  restart daily per site, one series per purpose: **V**001 visitor, **D** parcel, **F** food, **C**
  contractor, **P** pick-up, **O** other. The gate does **not** open: the visitor shows the slip to
  security, and scans its QR under *I have an invitation* when leaving (or a guard checks them out on
  the Walk-ins page). Passes are valid until the end of the day.
- **Slip printer:** connect the receipt printer to the kiosk PC, make it the default printer with a
  58 mm roll paper size, and start Chrome with `--kiosk --kiosk-printing` so slips print without a
  dialog. A kiosk without a printer (Gates & devices → Kiosks → untick *Receipt printer connected*)
  shows the pass number and QR on screen instead.
- **Visitor pass** (`/i/<token>`, the invitation's share link): shows the QR code, validity, the unit and
  the host's first name only. Anyone with the link can use it, so the page sends no referrer.

| Who | Endpoint | Purpose |
|---|---|---|
| Kiosk | `POST /v1/kiosk/visitors/lookup/` (`phone` or `id_partial`) | Returning visitor: masked name, last purpose and a short-lived reference |
| Kiosk | `POST /v1/kiosk/checkin/lookup/` (`code`) | Who the QR belongs to and whether a face photo is needed (no logging) |
| Kiosk | `POST /v1/kiosk/checkin/` (`code`, optional `plate`, `face_photo`) | Check in; opens the kiosk's gate when granted |
| Kiosk | `GET /v1/kiosk/directory/?walk_in=1` | Every active unit (walk-ins ring nobody) |
| Kiosk | `POST /v1/kiosk/walk-ins/` (`unit`, `purpose`, visitor details, `consent`, `snapshot`) | Register a walk-in; returns the slip (pass number, QR as a data URI) |
| Kiosk | `POST /v1/kiosk/walk-ins/checkout/` (`code` = slip QR, `ELIX-WALKIN:<token>`) | Check out |
| Staff | `GET /v1/walk-ins/?state=on_site`, `POST …/{id}/check_out/`, `GET …/{id}/snapshot/` | Walk-in list, manual check-out, photo |
| Public | `GET /v1/public/invitations/<token>/`, `…/qr/` | Visitor pass data and QR PNG (rate-limited) |

## Resident app (Flutter, Android)

`mobile/resident/` is the residents' app: sign in with the login created under **Residents**, answer
gate calls (native full-screen ringing when the app is closed, in-app screen with the visitor's photo
when open), video with the kiosk, **swipe to open**, invite visitors and share the QR pass, register
vehicles, and see the unit's recent entries. Staff use the web dashboard instead.

**Builds run on GitHub Actions, not on the server** (Gradle needs more RAM than the 4 GB production
box has; a local build there hangs it). `.github/workflows/resident-apk.yml` builds on every push that
touches `mobile/resident/` (or manually: Actions → Resident APK → Run workflow) and publishes
`elix-resident.apk` to the `resident-latest` GitHub release. Then on the server:

```bash
scripts/fetch-resident-apk.sh   # downloads the latest APK into downloads/ (served at /downloads/)
```

The APK is then downloadable at `https://<your-host>/downloads/elix-resident.apk` (button on the
Residents page). Application ID: `com.sct.elixpms`. Repository secrets the workflow needs:
`ANDROID_KEYSTORE_BASE64` and `ANDROID_KEYSTORE_PASSWORD` (the release key, see Signing below), and
optionally `GOOGLE_SERVICES_JSON_BASE64`; optional variable `API_BASE`.

- **Push (calls ring while the app is closed)** needs Firebase: register an Android app with package
  `com.sct.elixpms` in your Firebase project, store its `google-services.json` (base64) as the
  `GOOGLE_SERVICES_JSON_BASE64` secret and rebuild; and paste the
  project's service-account key in **Platform → System settings → Firebase**. Without these the app
  still works but rings only while it is open.
- **Signing:** the release key is `mobile/resident/android/elix-release.jks` with its password in
  `android/key.properties` (both git-ignored, on the server). Back them up: Android only installs
  updates signed with the same key.

## Privacy (PDPA)

- **Notification and consent:** the kiosk shows the site's privacy notice before taking any details or
  photo, and the visitor must tap *Agree & call* (or *Agree & get my pass* for a walk-in); the same notice is on visitor passes. Each site can
  write its own notice (Site settings → Privacy notice); the standard text states the purpose, who sees
  the data, the retention period and the management office contact.
- **Data minimisation:** only the last 4 characters of the NRIC/FIN are stored; without consent the
  kiosk keeps no photo; visitor records hold no face photo, only the call does.
- **Retention:** a daily job (`core.tasks.purge_visitor_data`, 03:30 SGT) removes visitor names,
  contact details, photos (calls and walk-in passes), camera payloads and visitor plates older than the site's *Keep visitor data
  for (days)*, and deletes visitor records not seen since. Blocked visitors are kept for security.
  Check with `docker compose exec web python manage.py purge_visitor_data --dry-run`.
- **Access / erasure requests:** Community → Visitors → *Erase data* (condo admins) removes the person
  and their photos and details from calls, walk-in passes and invitations.

## System settings

**Platform → System settings** in the dashboard (also available in Django admin) is a single page for server-wide integrations: LiveKit (URL, key, secret,
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
