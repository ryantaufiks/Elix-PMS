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

Set `DEV_BIND` in `.env` to the server's Tailscale IP to reach the dev API remotely.

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
