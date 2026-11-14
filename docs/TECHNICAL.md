# Elix-PMS · Technical guide

Visitor Management & Access Control System for Singapore condominiums: multi-site, LPR (Dahua),
gate relays (Sonoff eWeLink / Shelly), LiveKit video intercom and a staff dashboard.
Panduan berbahasa Indonesia: [PANDUAN.md](PANDUAN.md). Overview and screenshots: [README](../README.md).

## Quick start (development)

```bash
cp .env.example .env          # fill in DJANGO_SECRET_KEY, FIELD_ENCRYPTION_KEY, DB password
docker compose up -d --build  # db, redis, web (runserver), worker (with the beat schedule)
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py test core
```

| URL | |
|---|---|
| http://127.0.0.1:8001/v1/admin/ | Django admin (advanced fallback; daily setup is in the dashboard) |
| http://127.0.0.1:8001/v1/docs/ | Swagger API docs (platform admins: sign in to `/v1/admin/` first) |
| http://127.0.0.1:8001/v1/auth/token/ | JWT login (`/refresh/` to renew, `/v1/auth/logout/` revokes the refresh token) |
| `POST /v1/lpr-webhook/` | Dahua LPR events (Basic Auth per camera) |
| `POST /v1/gates/{id}/open/` | Manual gate opening (any site staff) |
| `ws://…/ws/events/?token=<JWT>` (the token is blanked in server logs, `myproject/logfilter.py`) | Live events (access logs, intercom calls, visits, bookings; feedback for staff) for the user's condos and units |
| `ws://…/ws/events/?kiosk_token=<token>` | Live state of the kiosk's own calls |

The dev API listens on `127.0.0.1:8001` (`DEV_PORT`); port 8000 belongs to production. Set `DEV_BIND`
in `.env` to the server's Tailscale IP to reach the dev API remotely.

## Landing page

The site root (`/`, `frontend/src/app/page.tsx` → `components/landing/`) is the public product page:
hero (with *Four languages* and *Designed to WCAG 2.1 AA*), twelve feature cards (incl. guardhouse dashboard,
vehicle passes and season parking, facility check-in and no-shows, report insights, Elixa, accessibility), *How it works* (an interactive Three.js scene per journey: visitor calls a resident,
invited guest, facility booking, car at the barrier; drag to turn, tap a step, auto-plays unless the visitor prefers reduced
motion, and falls back to the step list without WebGL), plans (modules per plan, *Contact for quote*, no
prices), PDPA, technology and security, with links to the privacy and cybersecurity policies. *Request a
demo* and the quote buttons open an email to services@ with a pre-filled template. Three.js is loaded only
on this page (its own chunk). A band after the features shows the resident app as *Coming soon* on Google Play
and the App Store (`components/landing/StoreBadges.tsx`: own buttons with the store logos, not the official badges,
which the stores allow only for a live app; swap them for the official badges and links at launch). The page is indexable; the rest of the app stays `noindex`. The top bar shows
*Open dashboard* instead of *Sign in* when this browser is already signed in.

## Dashboard (staff)

The dashboard home is `/dashboard/`; signing in lands there (a `?next=` path is kept, but never `/`), and
the Django admin's *View site* opens it.

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
Table rows keep one visible action and put the rest behind a "⋯" menu (`RowMenu` in
`components/ui.tsx`; destructive items last, in red, after a divider). On phones every `Table`
turns into a list of cards: each `Td` given a `label` shows it beside the value (CSS in `globals.css`).
Timestamps use one format everywhere (`formatDateTime` in `lib/format.ts`: "09 Nov, 17:23", with the year
only when it is not the current year; `formatRange` for bookings: "12 Nov, 18:00–20:00"). The traffic chart
shows an empty state until the first gate decision of the day, and a gate's *Open* button is disabled while
no relay is wired to it.
The top bar carries a quiet breadcrumb ("Operations › Invitations"), the page heading is the only title.
Empty lists use `Empty` with an icon, a title, a one-line hint and, where the viewer may add the first
record, the matching button. Report types on Reports are one row of tabs; below them only the period, the smart search and a *Filters* button (the panel with sites, dates and the report's filters is closed by default, remembered per browser as `elix.reportFilters`; active filters show as removable chips).
Selects are drawn like the inputs beside them (own chevron, no browser chrome); the sidebar shows a fade with a
chevron while more menu lies below the fold (short tablet screens); a long site name wraps to two lines in
the picker; on Gates & devices the "N need attention" count opens the kind of device concerned; the login page
says where to turn for a forgotten password.
Sidebar groups (Operations, Community, Site setup, Platform) fold open and closed like dropdowns,
remembered per browser; the group of the current page always opens. The **bell** in
the top bar lists live activity for the selected condo as it happens: visitors in and out, intercom
calls and their outcome, gate openings and denials, bookings and new feedback. The last 50 are kept
in the browser; opening the bell marks them read.

**All day-to-day setup is done here; Django admin is only an advanced fallback for the platform admin.**
On first sign-in with no condominium, the platform admin is guided through creating one.

| Section | Page | Who | What |
|---|---|---|---|
| Operations | Dashboard | all staff | Visitors first: on site now (by purpose), arrived today vs yesterday at this time, left today, overstaying; the visitors on site (overstaying first, live time inside, check out); visitors in and out per hour; live activity; gates with one-click opening. Site admins also get *Gates & devices* (gate decisions, devices, traffic, entry methods) |
| | Access log | all staff | Filter by gate, method, result, plate and period (Today / 7 days / 30 days / custom dates, SGT); camera snapshots; live updates |
| | Intercom | all staff | Ringing kiosk calls (ringtone + a pop-up on every page to answer, reject or swipe to open without leaving the page; *Later* folds it into a banner, a call answered there stays in the pop-up until it ends; browsers keep sound off until the page gets a click or key press, so the dashboard switches its AudioContext on at every gesture and the pop-up shows *Turn on sound* while it is still blocked; an amber bar says so as soon as a page opens
muted, before any call comes in), including *Call to the guardhouse* from visitors who need help; answer with video, swipe to open, reject; history |
| | Visitor list | all staff | Every visitor on site and past visits (kiosk / guardhouse walk-ins, invitations, intercom) with check-in and check-out time, photo, notes; *Register visitor* at the guardhouse (webcam photo, slip printed), *Print slip*, *Edit* notes, *Check out* one or many; a toast on every page when a kiosk walk-in registers |
| | Open gates | all staff | Manual opening with reason (logged under the user) |
| | Invitations | all staff (create/cancel: admin, staff) | QR code and share link, status filters |
| | Bookings | all staff (cancel, record refunds: admin, staff) | Facility bookings from the resident app with payment status; upcoming / all, filters |
| | Reports | all staff (several sites: superusers) | Report Center: consolidated summary, visitor, access, vehicle, intercom and invitation reports with period presets, filters and smart search; *Print / PDF* (A4) and *Excel* / *CSV* export |
| Community | Residents | all staff (manage: admin, staff) | Add residents with their app login, unit role, intercom on/off, password reset, move out, documents (ownership, tenancy; admin and staff only) |
| | Vehicles | all staff (edit: admin, staff) | Plates used by LPR auto-open: *Resident*, *Season parking* or *Temporary*, with holder name and valid from / until dates (season and temporary need an end date); tabs for each type, *Ending in 7 days* and *Expired* |
| | Feedback | all staff (reply: admin, staff) | Residents' 1–5 star ratings by category, average and distribution, reply and status shown in the app |
| | Staff | admin | Create officer / staff / site-admin accounts, change role, reset password, remove |
| Site setup | Site settings | admin | One card per section (Condominium, Access policy, Visitor kiosk, PDPA) with a save bar that stays in view and shows unsaved changes; the plan is a one-line strip that opens the full summary |
| | Blocks & units | admin | Blocks, units, and *Generate units* (e.g. floors 2–15 × units 01–08) |
| | Gates & devices | admin | A health line (how many devices need attention) and one card per kind of device with its status: Gates, Relays (*Test open*, *Check*), Plate cameras (*Setup info*: upload URL, last payload), Kiosks (*New sign-in code*, shown once), Cloud accounts, and the coming-soon Face terminals and On-site link; *Open* lists that kind (`?view=relays` etc.) |
| Platform | Condominiums | platform admin | Add, edit, activate sites; each site's plan, subscription status and site admins, with *Add site admin* (creates the account at that site without switching to it) and *Subscription* |
| | System settings | platform admin | LiveKit, Firebase (with connection tests), relay / LPR tuning |

Secrets (relay passwords, cloud keys, camera passwords, LiveKit secret, Firebase key) are write-only:
the dashboard shows "saved" and a blank field keeps the stored value. Site admins can manage only
people who belong solely to their own condominium; staff only residents. Times are shown and entered in SGT.

Development with hot reload (proxies the API to the dev web service):

```bash
docker compose --profile frontend up -d frontend   # http://127.0.0.1:3000
```

### Vehicle passes

A vehicle opens LPR gates only from `valid_from` to `valid_until` (local dates, both days included;
empty means no bound). Outside its dates the camera read is denied with the reason (*Vehicle pass ended
on 13 Nov 2026* / *starts on …*) unless an invitation for the plate lets it in. Residents add their own
cars from the app as *Resident*; the type, holder and dates are set only by site admins and staff (the
API ignores them from residents). The unit's residents see *ends soon* (7 days before) and *has ended*
in the app's notifications and on their vehicle list; the dashboard shows managers a bar when passes
end within 7 days, and counts the visitors on site who came by car (plate typed by the officer or read
by a camera).

**Season parking bought in the app** (Site settings → *Season parking*: on/off, price per month, lots;
payments through the site's HitPay account under Facilities & payments). A resident picks a plate, a
driver name and 1, 3, 6 or 12 months and pays on HitPay (`/v1/parking-permits/`, `…/offer/`,
`…/{id}/pay|refresh/`; reference `parking-<id>`, the same webhook and return page as bookings). Only
HitPay's API confirms a payment; then `core.parking` creates the plate's *Season parking* pass or
extends it (a renewal starts the day after the current pass ends, so no day is paid twice). The lots
count passes valid now plus purchases being paid; renewals never need a new lot. A plate that is a
resident's car or belongs to another unit cannot be bought. Unpaid purchases close with the bookings'
payment window (`expire_unpaid_bookings`). Staff see every purchase on Vehicles → *Season parking
payments*; refunds go through the HitPay dashboard.

### Overstay alerts

Site settings → *Overstay alerts*: deliveries (parcel, food, pick-up) after **30 min**, guests and others
after **240 min**, contractors after **18:00** local time (a contractor arriving later gets the guests'
limit); 0 or empty turns a limit off. `core.visits.overstay_at()` gives the moment for a visit; visits
carry `overstay_at` and `overstaying`. Celery beat runs `notify_overstays` every 5 minutes: each visit
past its limit is broadcast once as `visit_overstay` (`Visit.overstay_notified_at`), which the dashboard
shows as a red toast and a bell notification. `notify_still_on_site` at 22:00 sends each site's count of
visitors still inside (`visitors_on_site`) for the night shift.

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
   only stored (Gates & devices → the camera → *Setup info* shows the last payload) so you can inspect
   the real payload first.
2. Gates & devices → Plate cameras → *Add plate camera*: set Dahua device ID, webhook username/password, and optionally **Plate field**
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
| Kiosk | `GET /v1/kiosk/weather/` | Temperature and 2-hour outlook shown under the date |
| Kiosk | `GET /v1/kiosk/directory/?q=05-12` | Units that take calls (no resident names) |
| Kiosk | `POST /v1/kiosk/calls/` (`unit`, `visitor_name`, `snapshot` image; or `guardhouse=true` alone) | Ring the unit, or the guardhouse (call without a unit, staff only); returns LiveKit `url/room/token` |
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
  Gates & devices → Kiosks → *Add kiosk*, open `/kiosk/` on the tablet and enter the one-time device token. Visitors
  either **call a resident** (unit directory, then their details and photo, LiveKit video both ways; the
  gate opens when the resident or guard swipes) or **scan their invitation QR** with the tablet camera.
  The unit is chosen with an on-screen number pad (block chips first when the site has several blocks;
  matching units appear as the digits are typed; "Use keyboard" for units with letters), so the tablet
  keyboard never covers the screen. Every screen after the welcome carries a coloured pill naming the
  journey and the step ("Walk in · Step 2 of 3"); on portrait tablets content starts near the top.
- **Layout:** header with the logo (left) and the language button (right). The welcome screen leads with
  *Welcome to* and the site name, then the date, time and temperature, then *How would you like to enter?*;
  other screens show the site name, date and weather small in the header centre. The welcome screen shows the journeys (Call a resident, Walk in, Scan QR code, Check out),
  and a one-line *Ask {assistant name}* button (default name *Elixa AI Assistant*). The journey cards are
  compact and sit in one row on a landscape tablet (up to five), two per row in portrait; their icons line
  up at the top whatever the length of their text.
- **Languages:** the globe button (EN / 中文 / BM / தமிழ்) in every screen's header opens English, 中文,
  Melayu and தமிழ். The choice applies to every
  kiosk screen (strings in `frontend/src/app/kiosk/i18n.tsx`, keyed by their English text, so anything
  missing, a message from the server or the site's privacy notice shows in English) and the AI
  concierge greets in it. The kiosk goes back to English when a visitor's journey ends or after
  90 seconds idle; the last 20 seconds ask "Do you need more time?" and any tap keeps the visitor's place
  (WCAG 2.2.1). The translations are a first draft: have a native speaker check them before launch.
- **Ringback**: while a kiosk call rings, the kiosk plays Singapore's ringing tone (400 Hz, 0.4 s on,
  0.2 s off, 0.4 s on, 2 s off) as a looping audio element (a generated WAV), not Web Audio, which some
  tablets pause once the call's camera and microphone start. The element is primed at the first taps, so a
  call Elixa places seconds later still rings. It stops when someone answers or the call ends.
- **Call the guardhouse** (per site, Site settings → *Offer Call the guardhouse at the kiosk*, on by
  default, needs the Intercom module): through the AI assistant (the visitor asks for security), and a button on any result that did not
  let the visitor in (declined, missed, unknown pass…). It rings the dashboard straight away: no unit,
  no form and no photo, so nothing personal is kept. Staff see it in the incoming-call pop-up and on
  Intercom as *Call to the guardhouse*, answer with video and swipe to open the kiosk's gate (logged as
  an intercom entry, no visit or pass is created: register the visitor at the guardhouse if needed).
  Residents' phones never ring for it. Turn it off at sites where nobody watches the dashboard.
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
  prints a **58 mm slip** with the pass number, a **4-digit PIN**, details, validity and a check-out QR. Pass numbers
  restart daily per site, one series per purpose: **V**001 visitor, **D** parcel, **F** food, **C**
  contractor, **P** pick-up, **O** other. The gate does **not** open: the visitor shows the slip to
  security, and checks out under *Check out* when leaving (or a guard checks them out on the Visitor
  list). A visitor counts as on site until they check out, overnight too (the dashboard shows the date
  of arrival and they overstay as usual); a pass nobody closed lapses 24 hours after arrival (`PASS_HOURS`).
- **Facilities** (sites with the Facilities module and an active facility): today's remaining slots of
  every facility, booked or free, never with a name or unit (`/v1/kiosk/facilities/`). *Check in to my
  booking* scans the booking's QR from the app (`ELIX-BOOKING:<token>`, also accepted at *Scan QR code*;
  `/v1/kiosk/facilities/checkin/`): a confirmed booking checks in from 15 minutes before its start until it
  ends (`Booking.checked_in_at`, shown on Bookings), and the facility's door opens when one is set
  (Facilities → *Door to open at check-in*), logged as a *Facility booking* access. **No-show** (per
  facility, off by default: *No-show after (minutes)*): every 5 minutes `mark_no_shows` flags confirmed
  bookings nobody checked in to that long after the start (`Booking.no_show_at`; the resident gets a
  *Missed booking* notification); with *Release no-shows* the booking is cancelled so the rest of the slot
  can be booked (no automatic refund). A late check-in clears the flag. Bookings → status *No-show* lists them. Booking for
  non-residents is left out on purpose: most condo by-laws keep facilities for residents and their guests.
- **Check out** (per site, Site settings → *Offer self check-out at the kiosk*, on by default): the
  kiosk's fourth button. The visitor scans the QR on their slip or screenshot, or types the PIN on the
  keypad. Every visit gets a PIN unique among the visitors on site; a PIN only works while the visitor
  is on site, and after 5 wrong PINs the kiosk refuses PINs for a minute. An invitation QR also checks
  that invited visitor out. PINs are meant for unit access control later too.
- **Check out by face** (per site, Site settings → *Allow check-out by face*, **off** by default): when
  the kiosk takes a visitor's photo (walk-in, call, or an invitation that requires a face check), the
  kiosk PC turns it into a face template with face-api.js (SSD MobileNet + 68-point landmarks +
  128-d recognition net, models served from `/models/face`, loaded in the background). The visitor is
  told before the photo, and sees whether face check-out is ready. At *Check out → Check out with my
  face* the kiosk averages a few frames and the server compares the template only with visitors on
  site at that site: the best match must be closer than 0.45 and clearly better (by 0.06) than the
  runner-up, otherwise the visitor is asked to use the QR or PIN. Templates are deleted at check-out
  and by the daily purge once the pass ends; photos are never sent for matching. Match distances
  (no personal data) are logged by `core.visits` to tune the thresholds on real cameras. There is no
  liveness check: a printed photo of a visitor could check them out (it never opens a gate).
- **After a resident opens the gate** (Call a resident), the kiosk shows the visitor's pass: pass
  number, QR and the PIN under it, with a reminder to photograph or screenshot it for check-out, and a
  *Print slip* button when the kiosk has a printer. Pass screens return to the start after 25 seconds
  so the next visitor cannot read them.
- **Visitor list:** every way in records a *visit* with the same daily pass number series: kiosk
  walk-ins, walk-ins registered by security, invitation check-ins (QR at the kiosk or plate at an LPR
  camera; re-entries the same day reuse the visit, and an exit camera checks the vehicle out) and
  gates opened over the intercom. Security can print any visit's slip from the dashboard (the
  guardhouse PC's default printer), add notes and check visitors out one by one or in bulk. The PIN of
  visitors on site is shown under the pass number (and is searchable). From the same row security can
  block or unblock the visitor, and admins can erase their data for a PDPA deletion request.
- **Slip printer:** connect the receipt printer to the kiosk PC, make it the default printer with a
  58 mm roll paper size, and start Chrome with `--kiosk --kiosk-printing` so slips print without a
  dialog. A kiosk without a printer (Gates & devices → the kiosk → *Edit* → untick *Receipt printer connected*)
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
| Kiosk | `POST /v1/kiosk/checkout/` (`code` = pass or invitation QR, or `pin`, or `face` = 128 numbers) | Check out (`/v1/kiosk/walk-ins/checkout/` still works); 429 after 5 wrong PINs; face misses answer 404 with `reason` |
| Kiosk | `GET /v1/kiosk/calls/{id}/pass/` | The visitor pass (QR, PIN) after the resident opened the gate |
| Staff | `GET /v1/visits/?state=on_site&source=&date_from=&date_to=&visitor=` | Visitor list (`source`: kiosk, staff, invitation, intercom); `visitor` = one person's history |
| Staff | `POST /v1/visits/` (`unit`, `visitor_name`, `purpose`, optional `company`, `visitor_phone`, `visitor_id_partial`, `vehicle_plate`, `notes`, `snapshot`; `consent`) | Register a walk-in at the guardhouse |
| Staff | `PATCH /v1/visits/{id}/` (`visitor_name`, `company`, `notes`), `GET …/slip/`, `GET …/snapshot/` | Edit, slip data to print, photo |
| Staff | `POST /v1/visits/{id}/check_out/`, `POST /v1/visits/bulk_check_out/` (`ids`) | Check out one or many |
| Public | `GET /v1/public/invitations/<token>/`, `…/qr/` | Visitor pass data and QR PNG (rate-limited) |

### Kiosk AI assistant (OpenAI)

An **Ask <name>** button on the kiosk opens a voice concierge: directions (it can put a site map or
floor plan on screen), facilities and hours, rules, deliveries, and help registering. It asks the unit,
name and purpose by voice, then opens the walk-in form with them filled in (photo, consent and the
unit are still confirmed on screen). It can also open the call, invitation-scan and check-out screens, and when the visitor asks for
security or needs help it cannot give, it rings the guardhouse (`call_guardhouse`, offered only when the
site has Call the guardhouse on). The default name is *Elixa AI Assistant*.
It only talks about the site and never reveals or confirms anything about residents.

- **Platform admin** (System settings → Kiosk AI assistant): the OpenAI API key (encrypted; `.env`
  fallback `OPENAI_API_KEY`), the voice, the models, the longest conversation (180 s) and the
  conversations per kiosk per day (100).
- **Mode**: *Speech to text* (default) records what the visitor says, transcribes it
  (`gpt-4o-mini-transcribe`), answers with a chat model (`gpt-4.1-mini`) and speaks the answer
  (`gpt-4o-mini-tts`): lower cost, a short pause per answer. The answer's text shows as soon as it is ready and its speech streams, so playback starts before it is fully made. *Realtime* talks to OpenAI over WebRTC
  (`gpt-realtime-mini`): live two-way voice that can be interrupted, at a higher cost. The server mints a
  one-minute client secret per conversation; the API key never reaches the kiosk.
- **Site admin** (Site setup → AI Assistant: a status line and four cards, *Assistant* opening its
  settings, *Knowledge*, *Maps & floor plans* and *Try it* opening their views): on/off, name, greeting, languages (it answers in the
  visitor's language), extra guidance, an optional own OpenAI key for the site, **knowledge** modules
  (plain text: directions, facilities, rules, contacts, getting here) and **maps** (images with what they
  show). *Try it* asks typed questions with the saved knowledge.
- **Privacy**: nothing said is stored. The kiosk keeps the conversation in memory and sends the recent
  turns with each request; the server only counts conversations and turns for the limits. The kiosk
  tells visitors their voice is processed by OpenAI to answer them.

| Who | Endpoint | Purpose |
|---|---|---|
| Kiosk | `GET /v1/kiosk/assistant/` | Whether it is on, name, greeting, mode, maps |
| Kiosk | `POST /v1/kiosk/assistant/sessions/` | Start: link to the spoken greeting (speech to text) or a client secret (realtime) |
| Kiosk | `POST /v1/kiosk/assistant/sessions/{id}/turns/` (`audio` or `text`, `history`) | One exchange: what was heard, the answer and screen actions, at once, plus a `speech` link |
| Kiosk | `GET /v1/kiosk/assistant/speech/{key}/` | The spoken answer, streamed as it is made (the random link, valid 2 minutes, is the key; the words wait in the cache, not in the link) |
| Kiosk | `POST …/sessions/{id}/end/`, `GET /v1/kiosk/assistant/maps/{id}/` | End; a map image |
| Site admin | `GET/PATCH /v1/assistant-settings/?condominium=`, `POST /v1/assistant-settings/test/` | Settings; typed test |
| Site admin | `/v1/assistant-modules/`, `/v1/assistant-maps/` (`…/{id}/image/`) | Knowledge and maps |

## Report Center

*Operations → Reports*, for every staff member. Officers report on their own site; superusers can
pick several sites or *All sites* for one consolidated report (a *Site* column and a *Visits by site*
breakdown appear).

The **Visitor report** adds insights for the management: *Busiest times* (arrivals by weekday and hour,
Monday first, local time: for planning shifts), *Visits per day by category* (guests, deliveries,
contractors: the same groups as the dashboard) and *Average stay by category* (visitors who checked
out). They come with the summary as `summary.insights` (`heatmap`, `purpose_trend`, `stay_by_purpose`).

| Report | Rows | Key figures |
|---|---|---|
| Consolidated summary | one per site and day | visits, walk-ins, not checked out, entries granted / denied / errors, intercom calls, missed calls, invitations |
| Visitor report | every visit | total, checked out, still on site, not checked out, average stay, identified visitors |
| Access report | every gate decision | granted, denied, errors, grant rate, distinct plates; top denial reasons |
| Vehicle report | every plate read | resident / invited / unknown vehicles, distinct plates, most frequent and unknown plates |
| Intercom report | every kiosk call | opened, declined, missed, answer rate, average time to answer |
| Invitation report | every invitation | used, use rate, active, expired, cancelled |

- **Period:** Today, Yesterday, Last 7 / 30 days, This / last month, This year or a custom range
  (at most 366 days), in Singapore time. Each report also has its own filters (category, status,
  method, vehicle type…) and a daily trend chart.
- **Smart search:** free words match any text column (name, company, plate, notes, unit…), and
  `key:value` tokens target one field, e.g. `unit:05-12 plate:SGX1234 status:denied "Ace Aircon"`.
  The chips under the search box list each report's tokens.
- **Print / PDF:** an A4 layout (landscape) with letterhead, period, sites and filters, key figures,
  trend, breakdowns, every row (up to 5,000; export Excel for more), page numbers and a
  prepared / reviewed / approved sign-off. Choose *Save as PDF* in the print dialog for a file.
- **Excel / CSV:** every row (up to 50,000). The Excel file has a *Summary* sheet (period, filters,
  key figures, breakdowns, daily trend) and a *Details* sheet with frozen headers and filters.

| Who | Endpoint | Purpose |
|---|---|---|
| Staff | `GET /v1/reports/` | Reports, their filters and search tokens, and the sites the user can report on |
| Staff | `GET /v1/reports/<key>/?condominium=<id \| ids \| all>&date_from=&date_to=&q=&<filter>=&page=` | Summary and rows; `page_size=print` for every row (≤5,000); `export=xlsx\|csv` downloads |

## Resident app (Flutter, Android)

`mobile/resident/` is the residents' app: sign in with the login created under **Residents**, answer
gate calls (native full-screen ringing when the app is closed, in-app screen with the visitor's photo
when open), video with the kiosk, **swipe to open**, invite visitors and share the QR pass, register
vehicles, and see the unit's recent entries. Staff use the web dashboard instead.

**Sites without the app:** a site whose plan lacks the *Resident app* module (or where the platform
admin switched it off under Subscription, see *Plans & subscriptions*) runs on the kiosk and the
dashboard only: residents there get no API access (the app shows *Your condominium does not use the
Elix app*), the kiosk hides *Call a resident* and refuses calls (409), the kiosk assistant loses its
`call_resident` tool, and the Residents page hides the APK button. Walk-ins, invitation QRs and
check-out keep working. The app hides *Facility* when the plan has no Facilities module.

The sign-in screen has a slowly drifting blue glow behind it (still when the phone's *Remove
animations* setting is on). The home header shows the **weather** at the condo next to the resident's
name and a **bell** with the number of new notifications. Every list in the app (activity, visitors,
facilities, bookings, feedback, invitations, vehicles, notifications) is paged: 9 per page with
*‹ Page 2 of 5 ›* underneath. The app opens on a splash (the ELIX logo with a breathing glow on navy); the home
header shows the condo's name from its site settings. The theme (Auto follows the phone, Light or Dark) is chosen in
Profile → Theme and remembered on the phone.

- **Notifications** (`GET /v1/notifications/`): the last 30 days at the resident's units, one entry
  per event: a visitor arrived or left, a gate opened or refused entry (the resident's own plate, app
  or security; openings that belong to a call or an invitation are told by the visit), a missed visitor
  call, a booking confirmed, cancelled or expired, and the management's reply to their feedback.
  Opening the bell marks them read on that phone.
- **Weather** (`GET /v1/weather/?condominium=`, kiosk: `GET /v1/kiosk/weather/`): NEA's realtime
  readings on data.gov.sg (collection 1459): air temperature and humidity from the station nearest
  the condo, and the 2-hour outlook of the nearest area. The condo is located from its postal code
  with OneMap (cached for 30 days; no postal code means the centre of Singapore). Readings are cached
  for 5 minutes on the server, so phones and kiosks never call data.gov.sg themselves; set
  `DATA_GOV_SG_API_KEY` for a higher rate limit. When NEA is unreachable the weather is simply hidden.

The home screen has four menu cards above the unit's recent activity (the latest 5; *See all* opens
the full history):

- **Documents** (Profile): the resident's own documents kept by the management (proof of ownership,
  tenancy agreement), uploaded under *Residents → Documents*, usually before the account is made.
  PDFs open in the phone's viewer, photos in the app. Files are stored under random names and only
  served through the API, never as public media.
- **Access:** open gates remotely with *swipe to open*. Only gates with *Residents can open this gate
  from the app* (Gates & devices) are listed; each opening is logged as *App* with the resident and unit
  (rate-limited, `RESIDENT_OPEN_RATE`, default 10/min).
- **Facility:** book facilities the site admin set up under **Setup → Facilities & payments** (hours,
  open days, slot length, slots per booking, bookings per slot, people, price per slot, refundable
  deposit, how far ahead, upcoming bookings per unit, cancellation cut-off, rules, photo). Residents pick
  a day and consecutive slots; free facilities are confirmed at once. Paid ones open the condominium's
  **HitPay** checkout (PayNow, cards…) inside the app: the slots are held while paying (*Hold slots while
  paying*, default 15 min) and the booking is confirmed only when HitPay's API reports the payment
  completed (the return page and the signed webhook just trigger that check). Unpaid bookings are
  released by `core.tasks.expire_unpaid_bookings` (every 5 min). Residents cancel up to the cut-off;
  refunds are made in the HitPay dashboard and recorded under **Bookings**. *My bookings* shows status,
  *Pay now* and *Cancel*.
- **Visitor:** visitors to the unit, *On going* (on site) and *History*, with check-in and check-out times.
- **Feedback:** rate a service 1–5 stars (security, cleanliness, facilities, maintenance, management,
  app, other) with a comment, and read the management's reply.

HitPay setup: in **Facilities & payments → Online payments**, paste the HitPay API key and salt
(encrypted at rest), keep *Sandbox* ticked to test with HitPay's sandbox account, then untick it to go
live. The webhook URL shown there (`/v1/payments/hitpay/webhook/`) is also sent with every payment request.

| Who | Endpoint | Purpose |
|---|---|---|
| Resident | `GET /v1/gates/?resident_remote_open=true`, `POST /v1/gates/{id}/remote_open/` | Gates the resident may open; open one |
| Admin / resident | `/v1/facilities/` (CRUD: admin), `GET …/{id}/availability/?date=`, `GET …/{id}/photo/` | Facilities, a day's slots, photo |
| Resident / staff | `POST /v1/bookings/` (`facility`, `starts_at`, `slots`, `guests`, `notes`, `unit`), `GET /v1/bookings/?upcoming=1` | Book (returns `payment_url` for paid facilities); list |
| Resident / admin | `POST /v1/bookings/{id}/pay/`, `…/refresh/`, `…/cancel/`, `…/refunded/` (admin) | Resume payment, re-check with HitPay, cancel, record refund |
| Admin | `GET/PATCH /v1/payment-settings/?condominium=` | HitPay account (key and salt write-only; the salt is required, as unsigned webhooks are rejected) |
| HitPay | `POST /v1/payments/hitpay/webhook/`, `GET /v1/payments/hitpay/return/?booking=` | Payment notification; page after paying |
| Resident / staff | `POST /v1/feedback/` (`rating`, `category`, `comment`), `GET /v1/feedback/`, `POST …/{id}/reply/` (admin), `GET …/summary/` | Feedback |
| Admin, staff / resident | `GET/POST /v1/resident-documents/` (`residency`, `kind`, `title`, `file`: PDF/JPG/PNG ≤ 8 MB), `DELETE …/{id}/`, `GET …/{id}/download/` | Residents' documents; residents read only their own, officers none |

**Builds run on GitHub Actions, not on the server** (Gradle needs more RAM than the 4 GB production
box has; a local build there hangs it). `.github/workflows/resident-apk.yml` builds on every push that
touches `mobile/resident/` (or manually: Actions → Resident APK → Run workflow) and publishes
`elix-resident.apk` to the `resident-latest` GitHub release. Then on the server:

```bash
scripts/fetch-resident-apk.sh   # downloads the latest APK into downloads/ (served at /downloads/)
```

The APK is then downloadable at `https://<your-host>/downloads/elix-resident.apk?v=<version>` (button on
the Residents page; the script prints the link). The version is the APK's short SHA-256, written to
`downloads/elix-resident.json`, so each build gets a new link and no phone or Cloudflare cache hands
out an older copy. Application ID: `com.sct.elixpms`. Repository secrets the workflow needs:
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

### Google Play

The same workflow also builds `elix-resident.aab` (artifact *elix-resident-aab* on the run), the
format Google Play takes, and checks that native libraries are aligned for 16 KB memory pages (a
warning on the run if one is not). Before the first upload:

- **Signing:** choose *Use existing app signing key* in Play Console and upload `elix-release.jks`
  (Play's PEPK tool). If Google generates a new key instead, phones with the sideloaded APK cannot
  update to the Play build without uninstalling first.
- **Store listing and policy links:** privacy policy at `https://<your-host>/privacy/`, account
  deletion at `https://<your-host>/account-deletion/` (both public pages of the web app, also linked
  from the app's login and Profile; the contact address is `PRIVACY_EMAIL` in
  `frontend/src/lib/legal.ts`). A short cybersecurity policy is at `/security/`; the dashboard login
  page links to it and to the privacy policy (useful for vendor security questionnaires).
- **Declarations:** `USE_FULL_SCREEN_INTENT` (calling app: the video intercom), the foreground service
  types `phoneCall`, `camera` and `microphone` that the call plugin declares (with a short video of an
  intercom call), Data safety (name, phone, photos/video during calls, documents, plates, payments via
  HitPay), and a demo resident account on a demo site for *App access*.
- The manifest removes the shared-storage and photo/video/audio library permissions plugins add: the app only
  opens PDFs from its own cache, and Play rejects those permissions without a core need.
- A new *personal* developer account must run a closed test (12 testers, 14 days) before production;
  an *organisation* account (D-U-N-S number) does not.

## Privacy (PDPA)

- **Notification and consent:** the kiosk shows the site's privacy notice before taking any details or
  photo, and the visitor must tap *Agree & call* (or *Agree & get my pass* for a walk-in); the same notice is on visitor passes. Each site can
  write its own notice (Site settings → Privacy notice); the standard text states the purpose, who sees
  the data, the retention period and the management office contact.
- **Data minimisation:** only the last 4 characters of the NRIC/FIN are stored; without consent the
  kiosk keeps no photo; visitor records hold no face photo, only the call does. Face templates for
  face check-out exist only while the visitor is on site.
- **Retention:** a daily job (`core.tasks.purge_visitor_data`, 03:30 SGT) removes visitor names,
  contact details, photos (calls and visits), visit notes, camera payloads and visitor plates older than the site's *Keep visitor data
  for (days)*, and deletes visitor records not seen since. Blocked visitors are kept for security.
  The same job removes face templates as soon as the pass has ended.
  Check with `docker compose exec web python manage.py purge_visitor_data --dry-run`.
- **Access / erasure requests:** Visitor list → *Erase visitor data* (site admins) removes the person
  and their photos and details from calls, visits and invitations.

## System settings

**Platform → System settings** in the dashboard (also available in Django admin) shows one card per server-wide service with its status (*Set up / Not set up*); *Set up / Change* opens that service's fields with its own *Save* and *Test*. Services: LiveKit (URL, key, secret,
token lifetime, unlock window), the Firebase service-account JSON, the relay HTTP timeout and the LPR
debounce. Secrets are stored encrypted and never shown again; a saved one shows *Saved* with *Remove*. Changes apply immediately to the web,
worker processes (no restart). Any blank field falls back to the matching `.env` variable
(`LIVEKIT_*`, `INTERCOM_UNLOCK_WINDOW_SECONDS`, `FCM_SERVICE_ACCOUNT_FILE`, `RELAY_HTTP_TIMEOUT`,
`LPR_DEBOUNCE_SECONDS`); the page shows which source is live. Infrastructure values (database, Redis,
`DJANGO_SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, hosts) stay in `.env` because the server needs them to start.
Per-condo settings (LPR on/off, ring timeout, invitation limits) are on each Condominium, and relay /
camera credentials on their own admin pages.

### Email (SMTP)

*System settings → Email* (card → *Set up / Change*) holds the outgoing mail server: host, port, security (STARTTLS, SSL/TLS
or none), username, password (encrypted), from address and name, reply-to; `.env` fallbacks
`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_SECURITY`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
`EMAIL_FROM_ADDRESS`, `EMAIL_FROM_NAME`, `EMAIL_REPLY_TO`. *Save & send test email* sends a test at once
(to the address typed next to it, or the admin's own). Other emails are queued: `core.mail.queue()`
renders `templates/email/<name>.{subject.txt,txt,html}` (branded `base.html`) into an `EmailLog` row per
recipient and the worker sends it, retrying network errors and temporary (4xx) server answers up to 3
times; rejected logins or recipients fail at once with the reason on the log. The **Email log** button on
the Email card (`GET /v1/email-logs/`, platform admin) lists the last 30 days; older rows are pruned daily
(`core.tasks.prune_email_log`, 04:45).

## Plans & subscriptions

Elix is sold per site as **modules** (`core/entitlements.py` holds the catalogue): `core` (always),
`resident_app`, `intercom` and `facilities` (both need the resident app), `lpr`, `face_kiosk`,
`ai_concierge`, `advanced_reports` (export and print / PDF), and, coming, `local_devices`,
`lpr_camera_list`, `face_terminal`. Coming modules do nothing yet: the dashboard shows them as *Coming
soon* (the *Face terminals* and *On-site link* cards on Gates & devices,
*Your plan*), and Plans / Subscription do not let them be added until they are available. A **Plan** (*Platform → Plans*) bundles modules with **limits**
(units, kiosks, gates, LPR cameras and staff accounts are enforced; video minutes, AI conversations,
face terminals and storage are shown and enforced later); empty means unlimited. Migration 0018 made
Basic, Standard and Premium plus an internal **Full** plan, and put every existing site on Full.

Each site has a **Subscription** (*Platform → Condominiums → Subscription*): plan, add-ons, modules
switched off, limit overrides, status (trial, active, grace, suspended, cancelled), trial and paid-until
dates, billing contact and internal notes, with a history of every change. A new site starts a 30-day
trial on the plan chosen when adding it (default Standard). The effective modules (plan + add-ons −
switched off, minus modules whose requirements are gone; while suspended or cancelled only `core`, `lpr`
and the on-site access modules) are stored on `Condominium.modules` and checked on the server:
viewsets with `module = "…"` refuse a locked site with 403 `{"code": "module_locked", "module": …}`,
`limit_key` refuses additions past a limit with 403 `{"code": "limit_reached"}`, and the kiosk
(`/v1/kiosk/me/` → `modules`, `call_resident`, `face_checkout`), the assistant, face verification of
invitations, the LPR webhook (records only) and report export / print follow the same modules. The
dashboard keeps locked menus visible with a padlock and shows what the feature does and which plan
includes it (`GET /v1/modules/`); site admins see their plan, modules and usage under *Site settings →
Your plan* (`GET /v1/subscriptions/<site>/`, without internal notes).

What each module covers today: **core**: visitor dashboard and overstay alerts, vehicle passes with dates,
the kiosk in four languages, on-screen reports; **intercom**: calls to a unit and to the guardhouse;
**facilities**: bookings, season parking (Site settings shows it only with this module; `core.parking`
refuses without it), kiosk Facilities check-in and no-shows; **ai_concierge**: Elixa, which can also ring the
guardhouse when intercom is on; **advanced_reports**: report insights (without it the Visitor report answers
`insights_locked` and the page offers the module), export and print / PDF.

**Lifecycle** (`core/subscriptions.py`, daily at 08:05 SGT, `core.tasks.subscription_lifecycle`): a trial
that ends goes to *active* if a paid-until date is still ahead, otherwise to *grace* for 14 days; an
active site whose paid-until date has passed goes to *grace*; when the grace end date passes the site is
*suspended*. While suspended, premium modules are off, site setup (site settings, units, gates and
devices, facilities, assistant) refuses changes with 403 `site_suspended` (platform admin excepted), and
reports can still be exported; gates, plates and the basic kiosk keep working. A *cancelled* site is
closed to its staff. Emails (via SMTP, to the site admins, the billing email and the platform admins):
trial ends in 7 days and 1 day, grace started, suspended, active again; each is sent once per date
(`Subscription.notices_sent`), whether the change was scheduled or made by hand. Setting *grace* by hand
without a date starts 14 days from today. Site admins see a banner for a trial ending within 7 days, a
grace period or a suspension.

**Usage** (`core/usage.py`, `UsageCounter` per site, month and metric): answered video intercom time
(counted when a call ends), AI conversations (on the platform key, and separately on a site's own key),
and AI tokens from OpenAI's answers (speech-to-text mode; realtime conversations are counted, not their
tokens). The plan's monthly allowances `intercom_minutes` and `ai_conversations` never stop a feature:
use above them is overage, priced per plan (`Plan.overage_rates`, `Plan.currency`), and the site
admins, billing contact and platform admins get an email at 80% and at 100% (once per month each).
*Platform → Usage* (`GET /v1/usage/?month=YYYY-MM`, `&export=csv`) lists every site's use, allowance,
overage and its amount, plus an AI cost estimate when *System settings → Cost per 1M input / output
tokens* are set. Site admins see this month's use against their allowance under *Your plan*. To stop a
feature for a site, switch its module off under Subscription.

## Accessibility (WCAG 2.1/2.2 AA)

Designed to follow WCAG 2.1 AA (Singapore's Digital Service Standards use the same level). Checked with
axe-core 4.10 (tags wcag2a/aa, wcag21a/aa, wcag22aa) on the landing page, login, dashboard, visits,
intercom, residents, access, settings, bookings, reports and the Register visitor form, light and dark:
0 violations (Nov 2026). The kiosk's only finding is zoom switched off, on purpose for a fixed lobby tablet.

- **Contrast**: `--c-muted` #5f6b80 (5.4:1 on white) and `primary-500` #2563eb (5.2:1 with white text);
  blue text in dark mode uses `dark:text-primary-300`. Keep new colours at 4.5:1 or more.
- **Larger text** (user menu, per browser, `elix.textSize`): the root font size goes to 118.75% and every
  size is in rem, so the whole dashboard grows. Browser zoom to 200% also works without sideways scrolling.
- **Keyboard**: browser focus rings are kept; wide tables (`Table`) are focusable so they scroll with the
  arrow keys; chart bars are focusable `role="img"` with their numbers as the label.
- **Kiosk**: dark high-contrast theme, large touch targets, four languages, a voice assistant, Call the
  guardhouse for anyone who cannot finish on screen, and a "more time?" warning before an idle reset.
- **Resident app**: follows the phone's font size; rating stars, booking dates, images (QR, visitor photo,
  facility photo) and the swipe-to-open slider have TalkBack/VoiceOver labels; the primary blue is
  #2563eb (light) and #8fb8ff with navy text (dark).
- Automated checks find about a third of issues: before claiming conformance in a tender, test with a
  screen reader (NVDA on the dashboard, TalkBack on the app) and the phone font at its largest.

## Production

Production runs on the same server as a separate stack and is published through **Cloudflare Tunnel**,
so no inbound ports are opened (the Lighthouse firewall can stay closed except SSH):

```bash
cp .env.example .env.prod     # DJANGO_DEBUG=false, real hostname, new DJANGO_SECRET_KEY
ENV_FILE=.env.prod docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
ENV_FILE=.env.prod docker compose -f docker-compose.yml -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

- The gateway (dashboard + proxy to the `web` service: Uvicorn, two processes) listens on
  `127.0.0.1:8000` only; `web` is not published. A visitor who typed `http://` is redirected to `https://`.
- In Cloudflare Zero Trust → Networks → Tunnels → *Public hostname*, set the service to
  `HTTP` / `localhost:8000`. HTTPS and WebSockets are handled by Cloudflare.
- In `.env.prod`, set `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS=https://<host>`,
  `PUBLIC_BASE_URL=https://<host>` and `CORS_ALLOWED_ORIGINS`.
- Keep `FIELD_ENCRYPTION_KEY` safe: losing it makes every stored secret unreadable.
- Recommended: protect `/v1/admin/` with a Cloudflare Access policy. If Bot Fight Mode is on, add a
  skip rule for `/v1/lpr-webhook/` so cameras are not challenged.
- Without Cloudflare, put any TLS reverse proxy (Caddy, nginx + certbot) in front of
  `127.0.0.1:8000` and have it set `X-Forwarded-Proto: https`.

### Backups

**Platform → Backups** (platform admins only) has two kinds of archive, made by the Celery worker:

- **Platform backup**: `platform-<date>.tar.gz` with `database.dump` (`pg_dump -Fc` of the whole
  database) and `media/` (every uploaded file). Made nightly at 02:45 and on *Backup now*; kept
  `BACKUP_KEEP_DAYS` (14). This is the one to restore from.
- **Site export**: `site-<code>-<date>.zip` with one site's records as JSON and CSV (`data/`) and the
  documents and photos they point to (`files/`), for handover, audit or a PDPA request. Kept
  `SITE_EXPORT_KEEP_DAYS` (7). Not for restoring: sites share the database and people can belong to
  several sites.

Passwords, device and payment credentials, pass tokens and face templates are never exported. Archives
live in the `backups` volume (`BACKUP_ROOT`, outside `MEDIA_ROOT`), readable by the app user only, and
every download is recorded (who, when, IP). The volume is on the server's disk: download a platform
backup now and then and keep a copy elsewhere. The image ships `pg_dump` 16 to match the `postgres:16`
server (`PG_MAJOR` build argument; change both together).

Restore a platform backup (replaces the whole database and copies the files back):

```bash
P="docker compose -p elix-vms-prod -f docker-compose.yml -f docker-compose.prod.yml"
docker cp elix-vms-prod-web-1:/data/backups/platform-<date>.tar.gz .    # or the downloaded file
mkdir restore && tar -xzf platform-<date>.tar.gz -C restore
ENV_FILE=.env.prod $P stop web worker
ENV_FILE=.env.prod $P run --rm --no-deps -v "$PWD/restore:/restore" worker sh -c \
  'pg_restore --clean --if-exists --no-owner --no-privileges -d "$DATABASE_URL" /restore/database.dump && cp -a /restore/media/. /data/media/'
ENV_FILE=.env.prod $P up -d
```

### Server resources (4 GB, 2 vCPU)

- **Swap** 2 GB (`/swapfile`, `vm.swappiness=10` in `/etc/sysctl.d/90-elix-memory.conf`): a cushion so
  a peak (a dashboard build, the nightly backup) slows down instead of the kernel killing a process.
- **One Celery worker runs the schedule too** (`worker -B`), instead of a separate beat container;
  a worker process past ~300 MB is replaced after its task (`--max-memory-per-child`).
- **Memory caps** in `docker-compose.prod.yml` (web 512 MB, worker 768 MB, db 512 MB, redis 256 MB with
  `maxmemory 200mb` / `volatile-lru`, gateway 128 MB): a misbehaving part restarts on its own instead of
  stalling the server.
- **Container logs** are capped at 3 x 10 MB each.
- **Web server**: Uvicorn with two processes (`WEB_WORKERS`), one per vCPU; WebSockets work across them
  through the Redis channel layer. **Database connections** are pooled (`DB_POOL=1`, up to `DB_POOL_SIZE`
  10 per process): without it, every thread of the ASGI server kept its own connection and Postgres ran
  out at about 50 simultaneous users.
- **Measured capacity** (load test on this server, Nov 2026, one 300-unit site): about 45 requests per
  second; up to ~50 people acting at the same moment answers in under half a second, ~100–300 slows to
  2–5 s without errors, errors start past ~400. 1,000 open app connections (WebSockets) cost almost
  nothing. The limit is the 2 vCPUs: go to 4 vCPUs when several busy sites share the server.
- **OS**: Debian security updates install themselves daily (`unattended-upgrades`, no automatic reboot);
  reboot after a kernel update at a quiet hour.
- The **dev stack** is stopped when not in use (`docker compose up -d` to work on it, `docker compose
  stop` after) and never builds the APK: that runs on GitHub Actions.

Dev and prod use separate Compose project names (`elix-vms-dev`, `elix-vms-prod`), so their
databases and volumes never mix.

## Access model

| Role | Sees | Writes |
|---|---|---|
| Superuser (platform admin) | everything | everything |
| Site admin | own condominium | own condominium, incl. setup, device credentials and staff accounts |
| Staff (management office) | own condominium, except setup, devices and staff accounts | residents and their logins, vehicles, invitations, bookings, feedback replies, plus everything an officer does |
| Officer | own condominium, except setup, devices and staff accounts | visitors, manual gate opening, intercom answers |
| Resident | own units, condo gates/blocks | own vehicles and invitations |

Third-party secrets (eWeLink, Shelly, camera, relay LAN passwords) are encrypted at rest with
`FIELD_ENCRYPTION_KEY` and are write-only in the API and admin (send `null` to remove one; blank keeps it). Back the key up: without it the
stored credentials cannot be read.

Hardening:
- Sign-in (`/v1/auth/token/`, `/refresh/` and the Django admin) is limited per address (`LOGIN_RATE`,
  default 20/min) and per username (`LOGIN_USER_RATE`, 10/min); the LPR webhook to 600 requests a minute
  per address, and 20 wrong camera passwords lock that address out for 5 minutes.
- Refresh tokens are single-use (rotated and blacklisted). Signing out, a password change or disabling
  the account revokes all of a person's refresh tokens; access tokens expire within `JWT_ACCESS_MINUTES`.
  Expired entries are flushed nightly.
- Staff can link only people already at their site to a unit or a staff role; new people are created
  through `/v1/users/`.
- Report exports never contain live formulas (text starting with `= + - @` is kept as text).
- HSTS (`SECURE_HSTS_SECONDS`, one year) is sent by Django and the gateway; the gateway logs paths
  without query strings, because the WebSocket carries the token in `?token=`.
- The API schema and Swagger docs are only for platform admins.
